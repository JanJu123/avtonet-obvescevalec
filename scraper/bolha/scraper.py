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
    
    def parse_bolha_ad(self, article_html: str):
        """Parse single Bolha article and extract key data for MarketData."""
        soup = BeautifulSoup(article_html, 'html.parser')
        
        # 1. Title, Link and AD ID
        title_tag = soup.find('h3', class_='entity-title')
        if not title_tag:
            return None
        
        link_tag = title_tag.find('a')
        if not link_tag:
            return None
        
        title = link_tag.text.strip()
        link = "https://www.bolha.com" + link_tag.get('href', '')
        ad_id = link_tag.get('name', '')

        # 2. Price
        price_tag = soup.find('strong', class_='price')
        price = price_tag.text.strip() if price_tag else "Po dogovoru"

        # 3. Image
        img_tag = soup.find('img', class_='entity-thumbnail-img')
        image_url = img_tag.get('src') if img_tag else None

        # 4. Location
        description_div = soup.find('div', class_='entity-description')
        location = ""
        if description_div:
            location = description_div.get_text(strip=True).replace("Lokacija:", "").strip()

        # 5. Published date (ISO format)
        time_tag = soup.find('time')
        published_date = time_tag.get('datetime') if time_tag else None

        # Map to new unified MarketData schema
        return {
            'content_id': ad_id,
            'source': 'bolha',
            'category': 'bolha',
            'title': title,
            'price': price,
            'link': link,
            'snippet_data': json.dumps({
                'image_url': image_url,
                'lokacija': location,
                'published_date': published_date
            }),
            'enriched': 0,
            'enriched_json': None
        }
    
    
    def extract_all_ads(self, html_content: str):
        """Extract all ads from Bolha search page."""
        soup = BeautifulSoup(html_content, 'html.parser')
        articles = soup.find_all('article', class_='entity-body')
        
        ads = []
        for article in articles:
            # Convert article to string to pass to parser
            article_html = str(article)
            ad_data = self.parse_bolha_ad(article_html)
            if ad_data:
                ads.append(ad_data)
        
        return ads

    def save_ads_to_market_data(self, ads):
        """Save extracted Bolha ads to MarketData with bo_ prefix."""
        saved = 0
        for ad in ads:
            try:
                # Add bo_ prefix to content_id for uniqueness across sources
                ad['content_id'] = f"bo_{ad['content_id']}"
                
                # Insert into MarketData
                # Note: insert_market_data handles the universal schema
                self.db.insert_market_data(ad)
                saved += 1
            except Exception as e:
                print(f"❌ [BOLHA] Error saving ad {ad.get('content_id')}: {e}")
                continue
        
        return saved


# --- TEST ---
if __name__ == "__main__":
    print("="*70)
    print("🚀 BOLHA SCRAPER TEST - Extract & Save Ads to MarketData")
    print("="*70)

    # Use actual bot.db with migrated schema
    test_db = Database("bot.db")

    url = "https://www.bolha.com/search/?keywords=gorsko+elektri%C4%8Dno+kolo&condition[new]=1&sort=new"

    scraper = Scraper(test_db)

    print(f"\n📥 Fetching: {url}\n")
    html, bytes_used, status = scraper.get_latest_offers(url)
    
    if status != 200:
        print(f"❌ Failed! Status: {status}")
        exit(1)
    
    print(f"✅ Success! ({bytes_used} bytes)\n")
    
    print("🔍 Parsing ads...")
    ads = scraper.extract_all_ads(html)
    
    print(f"✅ Found {len(ads)} ads!\n")
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
