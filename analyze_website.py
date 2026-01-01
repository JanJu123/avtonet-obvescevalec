#!/usr/bin/env python3
"""
Debug script to check what ads are on the website and compare with SentAds
"""
from scraper import Scraper
from database import Database
import json

db = Database('bot.db')
scraper = Scraper(db)

# Get a sample URL 
urls = db.get_pending_urls()[:2]  # Get first 2 URLs

if not urls:
    print("No pending URLs found!")
    exit(1)

for url_entry in urls:
    u_id = url_entry['url_id']
    u_name = url_entry.get('telegram_name', f'URL {u_id}')
    final_url = url_entry['url_bin'].decode('latin-1') if isinstance(url_entry.get('url_bin'), bytes) else url_entry.get('url', '')
    
    print(f"\n{'='*60}")
    print(f"Analyzing: {u_name} (ID: {u_id})")
    print(f"URL: {final_url[:80]}...")
    print('='*60)
    
    # Get HTML from website
    html, _, status = scraper.get_latest_offers(final_url)
    if not html:
        print(f"❌ Failed to fetch HTML (status: {status})")
        continue
    
    # Parse ads
    from bs4 import BeautifulSoup
    import re
    soup = BeautifulSoup(html, 'html.parser')
    rows = soup.find_all('div', class_='GO-Results-Row')
    print(f"\nFound {len(rows)} ad rows on website")
    
    ads_on_website = []
    ads_in_sentads = []
    ads_new = []
    ads_reuse = []
    
    conn = db.get_connection()
    
    for idx, row in enumerate(rows[:10], 1):  # Check first 10
        # Skip top ponudba (promotional)
        if row.find('a', class_='GO-TopPonudbaSponzor'): 
            continue
        
        link_tag = row.find('a', class_='stretched-link')
        if not link_tag: 
            continue
        href = link_tag.get('href', '')
        match = re.search(r'id=(\d+)', href)
        if not match: 
            continue
        
        content_id = str(match.group(1))
        ads_on_website.append(content_id)
        
        # Check if in SentAds
        in_sent = conn.execute("SELECT 1 FROM SentAds WHERE content_id = ?", (content_id,)).fetchone()
        in_market = conn.execute("SELECT 1 FROM MarketData WHERE content_id = ?", (content_id,)).fetchone()
        
        status_str = ""
        if in_sent:
            ads_in_sentads.append(content_id)
            status_str = "✗ IN_SENTADS"
            ads_reuse.append(content_id)
        elif in_market:
            status_str = "⚠ IN_MARKET (but not sent)"
            ads_reuse.append(content_id)
        else:
            status_str = "✓ NEW!"
            ads_new.append(content_id)
        
        # Try to get car name
        car_div = row.find('div', class_='GO-ResultsAdsSmallerFont')
        car_name = car_div.get_text(strip=True) if car_div else 'Unknown'
        
        print(f"  {idx}. {content_id}: {car_name[:50]:50} {status_str}")
    
    conn.close()
    
    print(f"\nSummary for {u_name}:")
    print(f"  Total on website: {len(ads_on_website)}")
    print(f"  ✗ In SentAds (old): {len(ads_in_sentads)}")
    print(f"  ⚠ In MarketData only: {len(ads_reuse) - len(ads_in_sentads)}")
    print(f"  ✓ New/Not seen: {len(ads_new)}")
    
    if ads_new:
        print(f"\n✓ Good news! Found {len(ads_new)} new ads that should be processed:")
        for cid in ads_new[:5]:
            print(f"    - {cid}")
    else:
        print(f"\n⚠ No new ads found on this URL. Website is showing only previously seen listings.")

print("\n" + "="*60)
print("ANALYSIS COMPLETE")
print("="*60)
