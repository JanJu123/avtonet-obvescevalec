import re
import time
import random
import json
from bs4 import BeautifulSoup
from curl_cffi import requests
from ai_handler import AIHandler
import config
from database import Database
from scraper.base_scraper import get_latest_offers

class Scraper:
    def __init__(self, DataBase: Database):
        self.db = DataBase
        self.ai = AIHandler()

    def get_latest_offers(self, url: str):
        """Pridobi oglase, očisti URL in vrne (HTML, bytes, status_code)."""
        # Delegate to base scraper function
        return get_latest_offers(url)
    
    def extract_all_ads(self, html_content: str):
        """Extract all ads from Bolha search page (regular listings, not featured stores)."""
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Find the regular listings section (EntityList--Regular)
        regular_section = soup.find('section', class_='EntityList--Regular')
        if not regular_section:
            return []
        
        # Get the list items from the section
        items_ul = regular_section.find('ul', class_='EntityList-items')
        if not items_ul:
            return []
        
        # Extract all li.EntityList-item--Regular elements
        list_items = items_ul.find_all('li', class_='EntityList-item--Regular')
        
        ads = []
        for li_item in list_items:
            # 1. Title, Link and AD ID
            title_tag = li_item.find('h3', class_='entity-title')
            if not title_tag:
                continue
            
            link_tag = title_tag.find('a')
            if not link_tag:
                continue
            
            title = link_tag.text.strip()
            link = "https://www.bolha.com" + link_tag.get('href', '')
            content_id = link_tag.get('name', '')
            
            if not content_id:
                continue

            # 2. Price
            price_tag = li_item.find('strong', class_='price')
            price = price_tag.text.strip() if price_tag else "Po dogovoru"

            # 3. Image (Bolha uses lazy loading with data-src)
            img_tag = li_item.find('img', class_='entity-thumbnail-img')
            image_url = None
            if img_tag:
                # Try data-src first (lazy loading), then src
                image_url = img_tag.get('data-src') or img_tag.get('src')
                # Convert protocol-relative URLs to absolute HTTPS
                if image_url:
                    if image_url.startswith('//'):
                        image_url = 'https:' + image_url
                    elif not image_url.startswith('http'):
                        image_url = 'https://www.bolha.com' + image_url

            # 4. Location
            description_div = li_item.find('div', class_='entity-description')
            location = ""
            if description_div:
                location = description_div.get_text(strip=True).replace("Lokacija:", "").strip()

            # 5. Published date
            time_tag = li_item.find('time')
            published_date = time_tag.get('datetime') if time_tag else None

            ad_data = {
                'content_id': content_id,
                'title': title,
                'price': price,
                'image_url': image_url,
                'link': link,
                'location': location,
                'published_date': published_date
            }
            ads.append(ad_data)
        
        return ads

    @staticmethod
    def _with_page(url: str, page: int) -> str:
        """Add or modify page parameter for Bolha URLs."""
        # Bolha uses 'page=' parameter (or similar pagination mechanism)
        # If URL already has 'page=', replace it; otherwise add it
        if "page=" in url:
            return re.sub(r"page=\d+", f"page={page}", url)
        # Add page parameter
        sep = '&' if '?' in url else '?'
        return f"{url}{sep}page={page}"
    
    def run_with_pagination(self, base_url: str, max_pages: int = None):
        """Scrape Bolha results - stop after finding first page with real ads.
        
        Strategy:
        1. Keep trying pages until we find one with REAL ads (EntityList--Regular section)
        2. Once found, STOP - don't continue paginating
        3. This saves bandwidth and respects rate limits
        """
        if max_pages is None:
            max_pages = config.SCRAPER_MAX_PAGINATION_PAGES
        
        all_ads = []
        current_page = 1
        seen_ids = set()
        
        while current_page <= max_pages:
            page_url = self._with_page(base_url, current_page)
            print(f"[BOLHA] Fetching page {current_page}: {page_url}")
            
            html, bytes_used, status_code = self.get_latest_offers(page_url)
            if not html:
                print(f"[BOLHA] Fetch failed (HTTP {status_code}) for page {current_page}")
                break
            
            # Extract ads from this page
            page_ads = self.extract_all_ads(html)
            
            # If no ads found yet, keep trying next page
            if not page_ads:
                print(f"[BOLHA] Page {current_page}: no ads found, trying next page...")
                time.sleep(random.uniform(config.FETCH_SLEEP_MIN, config.FETCH_SLEEP_MAX))
                current_page += 1
                continue
            
            # Found real ads! Add them and STOP
            for ad in page_ads:
                ad_id = ad['content_id']
                if ad_id not in seen_ids:
                    all_ads.append(ad)
                    seen_ids.add(ad_id)
            
            print(f"[BOLHA] Page {current_page}: +{len(page_ads)} ads - STOPPING (first page with real ads found)")
            break  # STOP after first page with real ads
        
        return all_ads

    def save_ads_to_scraped_data(self, ads, url_id):
        """Save extracted Bolha ads to ScrapedData (url_id + content_id tracking)."""
        saved = 0
        for ad in ads:
            try:
                # Add bo_ prefix to content_id for uniqueness
                content_id = f"bo_{ad['content_id']}"
                
                # Check if already exists in MarketData (was seen before)
                if self.db.get_market_data_by_id(content_id):
                    continue  # Skip if already in archive
                
                # Check if already exists in ScrapedData (by url_id + content_id)
                if self.db.get_scraped_data_by_url_and_content(url_id, content_id):
                    continue  # Skip duplicates
                
                # Insert into ScrapedData (with url_id for query filtering)
                # For Bolha: location and published_date are in snippet, no enrichment needed
                data = {
                    'content_id': content_id,
                    'ime_avta': ad.get('title'),
                    'cena': ad.get('price'),
                    'slika_url': ad.get('image_url'),
                    'link': ad.get('link'),
                    'lokacija': ad.get('location'),  # Location from Bolha
                    'published_date': ad.get('published_date'),  # Publish time from Bolha
                    'leto_1_reg': None,
                    'prevozenih': None,
                    'gorivo': None,
                    'menjalnik': None,
                    'motor': None
                }
                self.db.insert_scraped_data(url_id, data)
                
                # Also save to MarketData as archive
                market_data = {
                    'content_id': content_id,
                    'source': 'bolha',
                    'category': 'item',
                    'title': ad.get('title'),
                    'price': ad.get('price'),
                    'link': ad.get('link'),
                    'snippet_data': {
                        'image_url': ad.get('image_url'),
                        'location': ad.get('location'),
                        'published_date': ad.get('published_date')
                    }
                }
                self.db.insert_market_data(market_data)
                
                saved += 1
            except Exception as e:
                print(f"[BOLHA] Error saving ad {ad.get('content_id')}: {e}")
                continue
        
        return saved


# --- TEST ---
if __name__ == "__main__":
    print("="*70)
    print("🚀 BOLHA SCRAPER TEST - Extract & Save Ads to ScrapedData")
    print("="*70)

    # Use actual bot.db with migrated schema
    test_db = Database("bot.db")

    url = "https://www.bolha.com/search/?keywords=gorsko+elektri%C4%8Dno+kolo&condition[new]=1&sort=new"

    scraper = Scraper(test_db)

    print(f"\n📥 Fetching with pagination: {url}\n")
    
    # Use pagination support (will fetch up to SCRAPER_MAX_PAGINATION_PAGES pages)
    ads = scraper.run_with_pagination(url)
    
    if not ads:
        print(f"❌ No ads found!")
        exit(1)
    
    print(f"\n✅ Found {len(ads)} total ads!\n")
    print("="*70)
    
    # Show first 5 ads
    for i, ad in enumerate(ads[:5], 1):
        print(f"\n📋 AD #{i}:")
        print(f"   ID: {ad['content_id']}")
        print(f"   Title: {ad['title']}")
        print(f"   Price: {ad['price']}")
        print(f"   Source: {ad['source']}")
        print(f"   Category: {ad['category']}")
    
    print("\n" + "="*70)
    print(f"💾 Saving {len(ads)} ads to MarketData...")
    saved = scraper.save_ads_to_market_data(ads)
    print(f"✅ Saved {saved}/{len(ads)} ads to MarketData")
    print("="*70)
