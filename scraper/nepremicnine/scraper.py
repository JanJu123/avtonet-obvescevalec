import re
import json
from bs4 import BeautifulSoup
from database import Database
from scraper.base_scraper import get_latest_offers

class Scraper:
    """Nepremičnine.net property listings scraper."""
    
    def __init__(self, DataBase: Database):
        self.db = DataBase
    
    def get_latest_offers(self, url: str):
        """Fetch and return (HTML, bytes, status_code)."""
        # Delegate to base scraper (handles curl-cffi with Chrome impersonation)
        return get_latest_offers(url)
    
    def extract_all_ads(self, html_content: str):
        """Extract all properties from search results page."""
        soup = BeautifulSoup(html_content, 'html.parser')
        ads = []
        
        # Find all property cards
        # Main selector: property-section with property-list-thumbnail or similar variants
        property_cards = soup.find_all('div', class_='property-section')
        
        for card in property_cards:
            try:
                # 1. Extract title/location
                title_tag = card.find('h2', class_='url-title-m') or card.find('h3', class_='url-title-m')
                if not title_tag:
                    title_tag = card.find('a', class_='url-title-m')
                
                if not title_tag:
                    continue  # Skip if no title found
                
                title = title_tag.get_text(strip=True) if hasattr(title_tag, 'get_text') else title_tag.text.strip()
                
                # 2. Extract link and ID
                link_tag = card.find('a', class_='url-title-m')
                if not link_tag:
                    link_tag = card.find('a', href=re.compile(r'/oglasi-'))
                
                if not link_tag:
                    continue  # Skip if no link
                
                link = link_tag.get('href', '')
                
                # Make absolute URL if relative
                if link and not link.startswith('http'):
                    link = 'https://www.nepremicnine.net' + link
                
                # Extract ID from URL (e.g., /oglasi-prodaja/latkova-vas-hisa_7244147/)
                content_id = self._extract_id_from_link(link)
                if not content_id:
                    continue  # Skip if no ID found
                
                # 3. Extract price
                price_tag = card.find('h6')
                price = price_tag.get_text(strip=True) if price_tag else "Po dogovoru"
                
                # 4. Extract image
                img_tag = card.find('img')
                image_url = None
                if img_tag:
                    image_url = img_tag.get('data-src') or img_tag.get('src')
                    image_url = self._process_image_url(image_url)
                
                # 5. Extract description (contains metadata: m2, type, year, etc.)
                desc_tag = card.find('p', class_='font-roboto')
                description = desc_tag.get_text(strip=True) if desc_tag else ""
                
                # 6. Parse metadata from description
                metadata = self._parse_description(description)
                
                # 7. Extract property type from description or labels
                prop_type = metadata.get('type', 'Hiša')  # Default to Hiša
                
                # Build ad data structure
                ad_data = {
                    'content_id': content_id,
                    'title': title,
                    'price': price,
                    'image_url': image_url,
                    'link': link,
                    'location': title,  # Location is often in the title
                    'm2': metadata.get('m2'),
                    'land_m2': metadata.get('land_m2'),
                    'type': prop_type,
                    'year': metadata.get('year'),
                    'description': description[:200]  # First 200 chars
                }
                
                ads.append(ad_data)
            
            except Exception as e:
                print(f"[NEPREMICNINE] Error parsing property card: {e}")
                continue
        
        return ads
    
    def _extract_id_from_link(self, link: str) -> str:
        """Extract property ID from URL.
        Example: /oglasi-prodaja/latkova-vas-hisa_7244147/ -> 7244147
        """
        # Pattern: look for underscore followed by digits before trailing slash
        match = re.search(r'_(\d+)/?$', link)
        if match:
            return match.group(1)
        
        # Fallback: try to find any sequence of digits at the end
        match = re.search(r'(\d+)/?$', link)
        if match:
            return match.group(1)
        
        return None
    
    def _process_image_url(self, img_url: str) -> str:
        """Convert image URL to absolute HTTPS URL."""
        if not img_url:
            return None
        
        img_url = img_url.strip()
        
        # Convert protocol-relative URLs
        if img_url.startswith('//'):
            return 'https:' + img_url
        
        # Convert relative URLs
        if not img_url.startswith('http'):
            return 'https://www.nepremicnine.net' + img_url
        
        return img_url
    
    def _parse_description(self, description: str) -> dict:
        """Parse metadata from description string.
        Example: "117,5 m2, dvostanovanjska, novogradnja - zgr. l. 2026, 376 m2 zemljišča..."
        """
        metadata = {}
        
        if not description:
            return metadata
        
        # Extract living area (m2)
        m2_match = re.search(r'(\d+(?:[.,]\d+)?)\s*m2', description)
        if m2_match:
            metadata['m2'] = m2_match.group(1).replace(',', '.') + ' m²'
        
        # Extract land area (zemljišča)
        land_match = re.search(r'(\d+(?:[.,]\d+)?)\s*m2\s+zemljišča', description)
        if land_match:
            metadata['land_m2'] = land_match.group(1).replace(',', '.') + ' m²'
        
        # Extract year
        year_match = re.search(r'zgr\.\s*l\.\s*(\d{4})|zgrajena\s*l\.\s*(\d{4})', description)
        if year_match:
            metadata['year'] = year_match.group(1) or year_match.group(2)
        
        # Extract property type
        types = ['samostojna', 'dvostanovanjska', 'tri stanovanjska', 'večstanovanjska', 'vrstna']
        for prop_type in types:
            if prop_type in description.lower():
                metadata['type'] = prop_type.capitalize()
                break
        
        return metadata
    
    def save_ads_to_scraped_data(self, ads, url_id):
        """Save properties to database with deduplication."""
        saved = 0
        
        for ad in ads:
            try:
                # Add np_ prefix to distinguish from other sources
                content_id = f"np_{ad['content_id']}"
                
                # Check if already exists in MarketData (global archive)
                if self.db.get_market_data_by_id(content_id):
                    continue  # Skip if already in archive
                
                # Check if already exists in ScrapedData for this URL
                if self.db.get_scraped_data_by_url_and_content(url_id, content_id):
                    continue  # Skip duplicates
                
                # Prepare data for ScrapedData (with url_id tracking)
                scraped_data = {
                    'content_id': content_id,
                    'ime_avta': ad.get('title'),  # Using ime_avta for title (legacy field name)
                    'cena': ad.get('price'),
                    'slika_url': ad.get('image_url'),
                    'link': ad.get('link'),
                    'lokacija': ad.get('location'),
                    'm2': ad.get('m2'),
                    'land_m2': ad.get('land_m2'),
                    'type': ad.get('type'),
                    'year': ad.get('year'),
                    'description': ad.get('description')
                }
                
                # Insert into ScrapedData
                self.db.insert_scraped_data(url_id, scraped_data)
                
                # Also save to MarketData (permanent archive)
                market_data = {
                    'content_id': content_id,
                    'source': 'nepremicnine',
                    'category': 'property',
                    'title': ad.get('title'),
                    'price': ad.get('price'),
                    'link': ad.get('link'),
                    'snippet_data': json.dumps({
                        'image_url': ad.get('image_url'),
                        'location': ad.get('location'),
                        'm2': ad.get('m2'),
                        'land_m2': ad.get('land_m2'),
                        'type': ad.get('type'),
                        'year': ad.get('year'),
                        'description': ad.get('description')
                    }, ensure_ascii=False),
                    'url_id': url_id
                }
                
                try:
                    self.db.insert_market_data(market_data)
                except Exception as market_error:
                    print(f"[NEPREMICNINE] Warning: Could not save to MarketData: {market_error}")
                
                saved += 1
            
            except Exception as e:
                print(f"[NEPREMICNINE] Error saving property {ad.get('content_id')}: {e}")
                continue
        
        return saved


# --- TEST ---
if __name__ == "__main__":
    print("="*70)
    print("🏠 NEPREMIČNINE.NET SCRAPER TEST")
    print("="*70)

    # Use production database
    from database import Database
    test_db = Database("bot.db")

    # Test URL (houses for sale in Žalec)
    test_url = "https://www.nepremicnine.net/oglasi-prodaja/savinjska/zalec/hisa/"

    scraper = Scraper(test_db)

    print(f"\n📥 Fetching: {test_url}\n")
    
    html, bytes_used, status_code = scraper.get_latest_offers(test_url)
    
    if status_code != 200:
        print(f"❌ Fetch failed with status {status_code}")
        exit(1)
    
    print(f"✅ Fetch successful ({bytes_used} bytes)")
    
    ads = scraper.extract_all_ads(html)
    
    if not ads:
        print(f"❌ No ads extracted!")
        exit(1)
    
    print(f"\n✅ Found {len(ads)} properties!\n")
    print("="*70)
    
    # Show first 3 ads
    for i, ad in enumerate(ads[:3], 1):
        print(f"\n🏠 PROPERTY #{i}:")
        print(f"   ID: {ad['content_id']}")
        print(f"   Title: {ad['title']}")
        print(f"   Price: {ad['price']}")
        print(f"   Size: {ad.get('m2', 'N/A')}")
        print(f"   Land: {ad.get('land_m2', 'N/A')}")
        print(f"   Type: {ad.get('type', 'N/A')}")
        print(f"   Year: {ad.get('year', 'N/A')}")
        print(f"   Link: {ad['link']}")
    
    print("\n" + "="*70)
    print(f"✅ Scraper test completed successfully!")
    print("="*70)