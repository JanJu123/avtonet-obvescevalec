import concurrent.futures
import time
import asyncio
import threading
from scraper import Scraper
from database import Database
from ai_handler import AIHandler
import config
import telegram

class MasterCrawler:
    def __init__(self, db_path=None, max_workers=6):
        self.db = Database(db_path or config.DB_PATH)
        self.scraper = Scraper(self.db)
        self.ai = AIHandler()
        # use config default if not provided
        self.max_workers = max_workers or getattr(config, 'MASTER_CRAWL_MAX_WORKERS', 3)
        # semaphore to limit concurrent AI processing
        self.ai_semaphore = threading.Semaphore(getattr(config, 'MASTER_PROCESSING_CONCURRENCY', 3))

    def _process_url(self, url_entry):
        """Fetch a URL, extract new ads and ensure MarketData + AI processing."""
        u_id = url_entry.get('url_id', 0)
        # obtain final_url
        if 'url_bin' in url_entry and url_entry['url_bin']:
            try:
                final_url = url_entry['url_bin'].decode('latin-1')
            except:
                final_url = url_entry.get('url')
        else:
            final_url = url_entry.get('url')

        html, bytes_used, status_code = self.scraper.get_latest_offers(final_url)
        if not html:
            # log and exit
            self.db.log_scraper_run(u_id, status_code, 0, 0, bytes_used, f"Master fetch error {status_code}")
            return []

        # Extract raw new ads (reuses scraper logic)
        new_ads = self.scraper._get_new_ads_raw(html)
        processed = []

        # Batch the new_ads according to config.MASTER_AI_BATCH_SIZE
        batch_size = getattr(config, 'MASTER_AI_BATCH_SIZE', 5)
        for i in range(0, len(new_ads), batch_size):
            batch = new_ads[i:i+batch_size]

            # For each ad in batch: insert placeholder and attempt to claim processing
            to_process = []
            for ad in batch:
                cid = ad['id']
                existing = self.db.get_market_data_by_id(cid)
                if existing and existing.get('processed'):
                    continue
                try:
                    self.db.insert_market_placeholder(cid, ad.get('link'), ad.get('text'))
                except Exception:
                    pass

                # Try to atomically mark processing; if successful, add to to_process
                try:
                    acquired = self.db.mark_market_processing(cid)
                except Exception:
                    acquired = False
                if acquired:
                    to_process.append(ad)

            if not to_process:
                continue

            # Acquire semaphore (limit concurrent batch processing)
            acquired_sem = self.ai_semaphore.acquire(timeout=10)
            if not acquired_sem:
                # couldn't get slot; release processing flags we set (so others can pick later)
                for ad in to_process:
                    self.db.update_market_data(ad['id'], {'ime_avta': None, 'cena': None, 'leto_1_reg': None, 'prevozenih': None, 'gorivo': None, 'menjalnik': None, 'motor': None, 'link': ad.get('link')}, raw_snippet=ad.get('text'))
                continue

            try:
                # Attempt AI with retries and exponential backoff
                attempts = getattr(config, 'AI_RETRY_COUNT', 3)
                success_results = None
                for attempt in range(1, attempts + 1):
                    try:
                        success_results = self.ai.extract_ads_batch(to_process)
                        # If we got a non-empty list, break
                        if success_results:
                            break
                    except Exception as e:
                        print(f"[MasterCrawler] AI batch error attempt {attempt}: {e}")
                        try:
                            for ad in to_process:
                                self.db.log_ai_error(ad.get('id'), f"AI exception attempt {attempt}: {e}")
                        except Exception:
                            pass
                    # backoff
                    time.sleep(1 * (2 ** (attempt - 1)))

                if not success_results:
                    try:
                        for ad in to_process:
                            self.db.log_ai_error(ad.get('id'), 'AI returned no result after retries')
                    except Exception:
                        pass
                    # mark as unprocessed (clear processing flag) so others can retry later
                    for ad in to_process:
                        self.db.update_market_data(ad['id'], {'ime_avta': None, 'cena': None, 'leto_1_reg': None, 'prevozenih': None, 'gorivo': None, 'menjalnik': None, 'motor': None, 'link': ad.get('link')}, raw_snippet=ad.get('text'))
                    continue

                # Process AI results
                for r in success_results:
                    r_id = str(r.get('content_id') or r.get('id') or r.get('ID'))
                    r['content_id'] = r_id
                    # find matching original ad
                    orig = next((x for x in to_process if str(x['id']) == r_id), None)
                    if orig:
                        r['link'] = orig.get('link')
                        img_tag = orig.get('row_soup').find('img') if orig.get('row_soup') else None
                        r['slika_url'] = img_tag.get('data-src') or img_tag.get('src') if img_tag else orig.get('slika_url')
                        # Update market data
                        self.db.update_market_data(r_id, r, raw_snippet=orig.get('text'))
                        # Also insert into ScrapedData for this url (so notification pipeline picks it up)
                        try:
                            self.db.insert_scraped_data(u_id, r)
                        except Exception:
                            pass
                        processed.append(r_id)
            finally:
                try:
                    self.ai_semaphore.release()
                except Exception:
                    pass

        # log run
        self.db.log_scraper_run(u_id, 200, len(new_ads), round(0,2), len(html.encode('utf-8')), 'Master scan')
        return processed

    def run(self, urls_list=None):
        """Main blocking run: fetch provided URLs (or config.MASTER_URLS) in parallel."""
        if urls_list is None:
            # Build url entries from config.MASTER_URLS
            urls_list = []
            for u in getattr(config, 'MASTER_URLS', []):
                urls_list.append({'url_id': 0, 'url': u, 'url_bin': None, 'telegram_name': 'MASTER'})

        results = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as ex:
            futures = [ex.submit(self._process_url, u) for u in urls_list]
            for fut in concurrent.futures.as_completed(futures):
                try:
                    res = fut.result()
                    results.extend(res)
                except Exception as e:
                    print(f"[MasterCrawler] Worker error: {e}")
        return results


# Async wrapper for job queue
async def master_job(context: "telegram.ext.ContextTypes.DEFAULT_TYPE"):
    mc = MasterCrawler()
    # Notify start (console + optional admin Telegram message) with color
    B_MAGENTA = "\033[95m"
    B_CYAN = "\033[96m"
    B_END = "\033[0m"
    start_msg = f"{B_MAGENTA}MASTER CRAWLER STARTING:{B_END} Scanning {len(getattr(config,'MASTER_URLS',[]))} master URLs."
    print(start_msg)
    try:
        if getattr(config, 'MASTER_NOTIFY_ADMIN', False) and config.ADMIN_ID:
            # send plain-text to telegram (no ANSI)
            await context.bot.send_message(chat_id=int(config.ADMIN_ID), text=f"MASTER CRAWLER: scanning {len(getattr(config,'MASTER_URLS',[]))} URLs")
    except Exception:
        pass

    # Run blocking master scan in a thread
    results = await asyncio.to_thread(mc.run)

    # After run, summarize
    processed_count = len(results) if results else 0
    finish_msg = f"{B_CYAN}MASTER CRAWLER FINISHED:{B_END} processed {processed_count} ads."
    print(finish_msg)
    try:
        if getattr(config, 'MASTER_NOTIFY_ADMIN', False) and config.ADMIN_ID:
            await context.bot.send_message(chat_id=int(config.ADMIN_ID), text=f"MASTER CRAWLER finished: processed {processed_count} ads")
    except Exception:
        pass


if __name__ == '__main__':
    # Quick manual test
    db = Database(config.DB_PATH)
    db.init_db()
    mc = MasterCrawler()
    print('Running master crawler once...')
    res = mc.run()
    print('Done. Processed IDs:', res)
