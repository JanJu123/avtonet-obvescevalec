import re
import time
from bs4 import BeautifulSoup

import config
from ai_handler import AIHandler
from database import Database
from scraper import Scraper
from utils import get_time

# Magenta for master logs (distinct but calm)
M_CLR = "\033[35m"
M_END = "\033[0m"


class MasterCrawler:
    """Caches ads into MarketData only (no ScrapedData/SentAds, no Telegram sends)."""

    def __init__(self, db: Database):
        self.db = db
        self.scraper = Scraper(db)
        self.ai = AIHandler()

    def crawl_once(self, urls=None):
        target_urls = urls or config.MASTER_URLS
        if not target_urls:
            print("[MASTER] No master URLs configured.")
            return

        total_new = 0
        print(f"{M_CLR}[{get_time()}] [MASTER] Start crawl: {len(target_urls)} URL(s), max pages {config.MASTER_MAX_PAGES}.{M_END}")

        for url in target_urls:
            try:
                total_new += self._crawl_single(url)
            except Exception as exc:
                print(f"{M_CLR}[MASTER] Error on URL: {exc}{M_END}")
                continue

            print(f"{M_CLR}[{get_time()}] [MASTER] Done. New ads cached this run: {total_new}.{M_END}")

    def _crawl_single(self, base_url: str) -> int:
        current_page = 1
        all_candidates = []
        seen_ids = set()

        while current_page <= config.MASTER_MAX_PAGES:
            page_url = self._with_page(base_url, current_page)
            html, _, status_code = self.scraper.get_latest_offers(page_url)
            if not html:
                print(f"{M_CLR}[MASTER] Fetch failed (HTTP {status_code}) for page {current_page}.{M_END}")
                break

            soup = BeautifulSoup(html, 'html.parser')
            rows = soup.find_all('div', class_='GO-Results-Row')

            page_candidates = []
            all_new_on_page = True

            for row in rows:
                if self.scraper._is_top_ponudba(row):
                    continue

                link_tag = row.find('a', class_='stretched-link')
                if not link_tag:
                    continue

                href = link_tag.get('href', '')
                match = re.search(r'id=(\d+)', href)
                if not match:
                    continue

                content_id = str(match.group(1))
                if content_id in seen_ids:
                    continue
                seen_ids.add(content_id)

                if self.db.get_market_data_by_id(content_id):
                    all_new_on_page = False
                    continue  # already cached

                img_tag = row.find('img')
                img_url = img_tag.get('data-src') or img_tag.get('src') if img_tag else None
                if img_url:
                    img_url = img_url.strip()
                    if img_url.startswith('//'):
                        img_url = 'https:' + img_url
                    elif img_url.startswith('/'):
                        img_url = 'https://www.avto.net' + img_url

                page_candidates.append({
                    "id": content_id,
                    "row_soup": row,
                    "text": self.scraper._clean_row_for_ai(row),
                    "link": "https://www.avto.net" + href.replace("..", ""),
                    "slika_url": img_url,
                })

            all_candidates.extend(page_candidates)

            if not all_new_on_page:
                break  # hit a known ad, stop going deeper

            current_page += 1

        if not all_candidates:
            print(f"{M_CLR}[{get_time()}] [MASTER] Nothing new for MarketData on this URL.{M_END}")
            return 0

        inserted = self._process_candidates(all_candidates)
        print(f"{M_CLR}[{get_time()}] [MASTER] URL done: pages={current_page-1 if not all_new_on_page else current_page}, new_ads={inserted}.{M_END}")
        return inserted

    def _process_candidates(self, items):
        # AI pass (batched)
        processed_ids = set()
        if config.USE_AI:
            for batch in self._chunk(items, config.MASTER_AI_BATCH_SIZE):
                print(f"{M_CLR}[MASTER] AI processing {len(batch)} ads...{M_END}")
                ai_results = self.ai.extract_ads_batch(batch)
                print(f"{M_CLR}[MASTER] AI returned: {ai_results}{M_END}")  # DEBUG
                if not ai_results:
                    print(f"{M_CLR}[MASTER] AI returned nothing, falling back to manual parse{M_END}")
                    continue

                for ad_data in ai_results:
                    ad_id = str(ad_data.get('content_id') or ad_data.get('id') or ad_data.get('ID'))
                    orig = next((x for x in batch if str(x['id']) == ad_id), None)
                    if not orig:
                        continue

                    ad_data['content_id'] = ad_id
                    ad_data['link'] = orig['link']
                    img_tag = orig['row_soup'].find('img')
                    ad_data['slika_url'] = img_tag.get('data-src') or img_tag.get('src') if img_tag else None

                    self.db.insert_market_data(ad_data, orig['text'])
                    processed_ids.add(ad_id)

        # Manual fallback for any unprocessed IDs
        for orig in items:
            if str(orig['id']) in processed_ids:
                continue
            img_tag = orig['row_soup'].find('img')
            img_url = img_tag.get('data-src') or img_tag.get('src') if img_tag else None
            manual_data = self.scraper._manual_parse_row(orig['row_soup'], orig['id'], orig['link'], img_url)
            self.db.insert_market_data(manual_data, orig['text'])

        return len(processed_ids) + sum(1 for orig in items if str(orig['id']) not in processed_ids)

    @staticmethod
    def _chunk(seq, size):
        for i in range(0, len(seq), size):
            yield seq[i:i+size]

    @staticmethod
    def _with_page(url: str, page: int) -> str:
        # If URL already ends with 'stran=' style, append page; else add param
        if "stran=" in url:
            if url.endswith("stran="):
                return f"{url}{page}"
            # replace existing stran value
            return re.sub(r"stran=\d+", f"stran={page}", url)
        sep = '&' if '?' in url else '?'
        return f"{url}{sep}stran={page}"


def run_master_crawler_once():
    db = Database(config.DB_PATH)
    crawler = MasterCrawler(db)
    crawler.crawl_once()


if __name__ == "__main__":
    start = time.time()
    run_master_crawler_once()
    print(f"[{get_time()}] [MASTER] Done in {round(time.time() - start, 2)}s")
