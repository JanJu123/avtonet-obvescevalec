# 📚 Adding a New Website Scraper

This guide explains how to add a new website scraper (e.g., Nepremičnine, Enaiga, etc.) to the system. The architecture is designed to be modular - you just need to create a scraper and integrate it!

---

## 🎯 Quick Overview

The system is organized by source:
```
scraper/
├── avtonet/
│   ├── __init__.py
│   ├── scraper.py (car listings)
│   └── master_crawler.py
├── bolha/
│   ├── __init__.py
│   └── scraper.py (items/parts)
├── nepremicnine/  ← YOUR NEW SCRAPER HERE
│   ├── __init__.py
│   └── scraper.py (properties)
└── base_scraper.py
```

---

## 📋 Step-by-Step: Add Nepremičnine Scraper

### Step 1: Create Directory Structure

```bash
mkdir scraper/nepremicnine
touch scraper/nepremicnine/__init__.py
touch scraper/nepremicnine/scraper.py
```

### Step 2: Implement the Scraper Class

Create `scraper/nepremicnine/scraper.py`:

```python
import re
import json
from bs4 import BeautifulSoup
from curl_cffi import requests
from database import Database

class Scraper:
    """Nepremičnine property listings scraper."""
    
    def __init__(self, DataBase: Database):
        self.db = DataBase
    
    def get_latest_offers(self, url: str):
        """Fetch and return (HTML, bytes, status_code)."""
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            resp = requests.get(url, headers=headers, timeout=10)
            return (resp.text, len(resp.content), resp.status_code)
        except Exception as e:
            print(f"[NEPREMICNINE] Error fetching {url}: {e}")
            return ("", 0, 500)
    
    def extract_all_ads(self, html_content: str):
        """Extract all properties from search results page."""
        soup = BeautifulSoup(html_content, 'html.parser')
        ads = []
        
        # ⚠️ IMPORTANT: Inspect the website's HTML to find correct selectors!
        # Example structure (adjust for real website):
        # <div class="property-card">
        #   <h2 class="property-title">...</h2>
        #   <span class="price">...</span>
        #   <img src="..." />
        #   <span class="location">...</span>
        #   <span class="size">...</span>
        
        for property_item in soup.find_all('div', class_='property-card'):
            try:
                # 1. Extract ID and title
                title_tag = property_item.find('h2', class_='property-title')
                title = title_tag.text.strip() if title_tag else "Neznano"
                
                # Extract ID from data attribute or URL
                link_tag = property_item.find('a', class_='property-link')
                link = link_tag.get('href', '') if link_tag else ''
                content_id = link.split('/')[-1] if link else None
                
                if not content_id:
                    continue
                
                # 2. Extract price
                price_tag = property_item.find('span', class_='price')
                price = price_tag.text.strip() if price_tag else "Po dogovoru"
                
                # 3. Extract image
                img_tag = property_item.find('img')
                image_url = None
                if img_tag:
                    image_url = img_tag.get('data-src') or img_tag.get('src')
                    # Convert relative URLs to absolute
                    if image_url:
                        if image_url.startswith('//'):
                            image_url = 'https:' + image_url
                        elif not image_url.startswith('http'):
                            image_url = 'https://www.nepremicnine.si' + image_url
                
                # 4. Extract location
                location_tag = property_item.find('span', class_='location')
                location = location_tag.text.strip() if location_tag else ""
                
                # 5. Extract size (m²)
                size_tag = property_item.find('span', class_='size')
                size = size_tag.text.strip() if size_tag else None
                
                # 6. Extract room count
                rooms_tag = property_item.find('span', class_='rooms')
                rooms = rooms_tag.text.strip() if rooms_tag else None
                
                # 7. Extract type (apartment, house, etc.)
                type_tag = property_item.find('span', class_='property-type')
                prop_type = type_tag.text.strip() if type_tag else None
                
                ad_data = {
                    'content_id': content_id,
                    'title': title,
                    'price': price,
                    'image_url': image_url,
                    'link': link if link.startswith('http') else 'https://www.nepremicnine.si' + link,
                    'location': location,
                    'm2': size,        # Goes to JSON metadata
                    'rooms': rooms,    # Goes to JSON metadata
                    'type': prop_type  # Goes to JSON metadata
                }
                ads.append(ad_data)
            
            except Exception as e:
                print(f"[NEPREMICNINE] Error parsing property: {e}")
                continue
        
        return ads
    
    def save_ads_to_scraped_data(self, ads, url_id):
        """Save properties to database."""
        saved = 0
        for ad in ads:
            try:
                # Add prefix to distinguish from other sources
                content_id = f"np_{ad['content_id']}"
                
                # Check if already exists in MarketData (seen before)
                if self.db.get_market_data_by_id(content_id):
                    continue  # Skip if already in archive
                
                # Check if already exists in ScrapedData for this URL
                if self.db.get_scraped_data_by_url_and_content(url_id, content_id):
                    continue  # Skip duplicates
                
                # Save to ScrapedData (with url_id for filtering)
                data = {
                    'content_id': content_id,
                    'ime_avta': ad.get('title'),
                    'cena': ad.get('price'),
                    'slika_url': ad.get('image_url'),
                    'link': ad.get('link'),
                    'lokacija': ad.get('location'),
                    'm2': ad.get('m2'),
                    'rooms': ad.get('rooms'),
                    'type': ad.get('type')
                }
                self.db.insert_scraped_data(url_id, data)
                
                # Also save to MarketData as archive
                market_data = {
                    'content_id': content_id,
                    'source': 'nepremicnine',
                    'category': 'property',
                    'title': ad.get('title'),
                    'price': ad.get('price'),
                    'link': ad.get('link'),
                    'snippet_data': {
                        'image_url': ad.get('image_url'),
                        'location': ad.get('location'),
                        'm2': ad.get('m2'),
                        'rooms': ad.get('rooms'),
                        'type': ad.get('type')
                    }
                }
                self.db.insert_market_data(market_data)
                
                saved += 1
            except Exception as e:
                print(f"[NEPREMICNINE] Error saving property {ad.get('content_id')}: {e}")
                continue
        
        return saved
```

### Step 3: Update `data_manager.py` Message Formatting

Add handling for Nepremičnine ads in `format_telegram_message()`:

```python
def format_telegram_message(self, oglas):
    from datetime import datetime
    
    # ... existing code ...
    
    # For Nepremičnine: location, size, rooms
    lokacija = oglas.get('lokacija', '').strip() if oglas.get('lokacija') else None
    m2 = oglas.get('m2', '').strip() if oglas.get('m2') else None
    rooms = oglas.get('rooms', '').strip() if oglas.get('rooms') else None
    prop_type = oglas.get('type', '').strip() if oglas.get('type') else None
    
    # ... existing message building ...
    
    # Add Nepremičnine-specific fields
    if lokacija or m2 or rooms:
        if lokacija:
            msg += f"Lokacija: <b>{html.escape(lokacija)}</b>\n"
        if prop_type:
            msg += f"Tip: <b>{html.escape(prop_type)}</b>\n"
        if rooms:
            msg += f"Sobe: <b>{rooms}</b>\n"
        if m2:
            msg += f"Velikost: <b>{m2}</b>\n"
        msg += "\n"
    
    msg += f"🔗 <a href='{link}'>KLIKNI ZA OGLED OGLASA</a>"
    return msg
```

### Step 4: Update `main.py` to Include New Scraper

```python
# At the top, add import:
from scraper.nepremicnine.scraper import Scraper as NepremicnineScraper

# In check_for_new_ads(), find the Bolha scraper section and add:

# --- NEPREMIČNINE SCRAPER ---
print(f"[{get_time()}] NEPREMICNINE - {len(nepremicnine_urls)} URL(s) pending")

nepremicnine_scraper = NepremicnineScraper(db)

async def process_nepremicnine_url(url_id, url):
    """Process single Nepremičnine URL."""
    try:
        html, bytes_used, status = nepremicnine_scraper.get_latest_offers(url)
        if status == 200:
            ads = nepremicnine_scraper.extract_all_ads(html)
            nepremicnine_scraper.save_ads_to_scraped_data(ads, url_id)
            print(f"[NEPREMICNINE] Najdeno {len(ads)} oglasov")
    except Exception as e:
        print(f"[NEPREMICNINE] Error processing URL {url_id}: {e}")

# Run in parallel with other scrapers
await asyncio.gather(
    asyncio.gather(
        *[process_avtonet_url(u_id, url) for u_id, url in avtonet_urls.items()]
    ),
    asyncio.gather(
        *[process_bolha_url(u_id, url) for u_id, url in bolha_urls.items()]
    ),
    asyncio.gather(
        *[process_nepremicnine_url(u_id, url) for u_id, url in nepremicnine_urls.items()]
    )
)
```

### Step 5: Test the Scraper

```bash
# Test that imports work
python -c "from scraper.nepremicnine.scraper import Scraper; print('OK')"

# Add a test URL to your Urls table
sqlite3 test_bot.db "INSERT INTO Urls (source, url) VALUES ('nepremicnine', 'https://www.nepremicnine.si/search/...');"

# Run the bot
python main.py

# Check if Nepremičnine ads appear in notifications
```

---

## 🔍 Key Implementation Details

### Content ID Prefix
Use a unique prefix for each source to avoid ID collisions:
- `av_` for Avtonet
- `bo_` for Bolha
- `np_` for Nepremičnine
- `en_` for Enaiga
- etc.

### JSON Metadata
Fields that aren't core (not in main columns) go to JSON:
```
Core columns: id, url_id, content_id, ime_avta, cena, link, slika_url
Metadata (JSON): m2, rooms, type, leto, km, gorivo, lokacija, etc.
```

### Image Handling
Always convert to absolute HTTPS URLs:
```python
if image_url:
    if image_url.startswith('//'):
        image_url = 'https:' + image_url
    elif not image_url.startswith('http'):
        image_url = 'https://example.com' + image_url
```

### Error Handling
Use try-catch in `save_ads_to_scraped_data()`:
```python
try:
    # extraction code
except Exception as e:
    print(f"[SOURCE] Error parsing item: {e}")
    continue  # Skip problem items, continue with rest
```

### Deduplication
Always check both tables:
```python
# Check if seen before (in archive)
if self.db.get_market_data_by_id(content_id):
    continue

# Check if already scraped for this URL
if self.db.get_scraped_data_by_url_and_content(url_id, content_id):
    continue
```

---

## 🧪 Testing Checklist

- [ ] Scraper imports without errors
- [ ] `extract_all_ads()` returns correct structure
- [ ] Image URLs are absolute (start with https://)
- [ ] Price format is consistent
- [ ] Deduplication works (run twice, check no duplicates)
- [ ] Message formatting displays correctly
- [ ] Images load in Telegram
- [ ] Handles missing fields gracefully (shows "Neznano")
- [ ] No spam (SentAds tracking prevents respam)
- [ ] Console shows [SOURCE] labels for clarity

---

## 🚨 Common Pitfalls

### 1. Wrong HTML Selectors
**Problem:** No ads extracted  
**Solution:** Use browser DevTools (F12) to inspect the website's actual structure

### 2. Relative URLs Not Converted
**Problem:** Images don't load in Telegram  
**Solution:** Always convert to absolute HTTPS URLs

### 3. Missing Content ID
**Problem:** Ads can't be tracked/deduplicated  
**Solution:** Extract from URL slug, data attribute, or generate from other fields

### 4. Not Checking MarketData
**Problem:** Same ads scraped repeatedly  
**Solution:** Always check `get_market_data_by_id()` first

### 5. Forgetting URL Prefix
**Problem:** ID collisions between sources  
**Solution:** Use unique prefix (bo_, np_, etc.)

---

## 📊 Database Schema Notes

All scrapers use the same `ScrapedData` and `MarketData` tables:

### ScrapedData (Working table)
```sql
id              -- Auto increment
url_id          -- Links to Urls table
content_id      -- Source-prefixed ID
ime_avta        -- Title/name
cena            -- Price
link            -- Direct URL to listing
slika_url       -- Image URL
metadata        -- JSON (flexible fields)
created_at      -- Timestamp
```

### MarketData (Archive)
```sql
content_id      -- Source-prefixed ID
source          -- 'avtonet', 'bolha', 'nepremicnine'
category        -- Type of listing
title           -- Title/name
price           -- Price
link            -- Direct URL
raw_snippet     -- Original HTML (optional)
snippet_data    -- JSON with extracted fields
created_at      -- Timestamp
enriched        -- Whether AI enrichment done
enriched_json   -- AI enrichment results
```

---

## 💡 Best Practices

### 1. Handle Missing Fields
```python
title = title_tag.text.strip() if title_tag else "Neznano"
```

### 2. Clean Up Whitespace
```python
text = text.replace('\xa0', ' ').strip()
```

### 3. Convert Prices to Standard Format
```python
if '€' not in price and any(c.isdigit() for c in price):
    price += " €"
```

### 4. Use Consistent Delays
```python
import time, random
time.sleep(random.uniform(1.5, 3))  # Between requests
await asyncio.sleep(0.5)  # Between messages
```

### 5. Add Console Labels
```python
print(f"[NEPREMICNINE] Found {len(ads)} properties")
print(f"[NEPREMICNINE] Saved {saved} new listings")
```

---

## 🎯 Example: Full Integration Checklist

- [ ] `scraper/nepremicnine/scraper.py` created with Scraper class
- [ ] `scraper/nepremicnine/__init__.py` created (can be empty)
- [ ] `extract_all_ads()` tested and working
- [ ] `save_ads_to_scraped_data()` tested and working
- [ ] `data_manager.py` updated with message formatting
- [ ] `main.py` imports NepremicnineScraper
- [ ] `main.py` has process_nepremicnine_url() function
- [ ] `main.py` calls asyncio.gather() with nepremicnine_urls
- [ ] Test URLs added to Urls table
- [ ] Bot restarted and tested
- [ ] First ads received in Telegram ✅

---

## 📞 Troubleshooting

| Problem | Check |
|---------|-------|
| No ads extracted | Browser DevTools - verify selectors exist |
| Duplicate ads | Is `get_market_data_by_id()` being called? |
| Images not loading | Are URLs HTTPS? Check in database |
| Wrong field data | Print HTML to console, check what's there |
| Bot crashes | Check error logs, add try-catch blocks |
| Messages malformed | Test `format_telegram_message()` separately |

---

## 🚀 You're Ready!

The system is designed for exactly this - adding new scrapers with minimal changes. Just follow the pattern, use the same database structure, and you're good to go!

Questions? Check existing scrapers (Avtonet, Bolha) for reference implementations.
