#!/usr/bin/env python3
"""
Backfill Bolha ads in MarketData with ime_avta in snippet_data.

Problem: Old Bolha ads don't have 'ime_avta' in snippet_data JSON.
When format_telegram_message tries to read from MarketData, it gets "Neznano".

Solution: Extract title from Bolha link URL pattern:
https://www.bolha.com/category/title-text-here-oglas-IDNUM
         The title is between category and '-oglas-'
"""

import sqlite3
import json
import sys
import re
from urllib.parse import unquote

def extract_title_from_bolha_link(link):
    """Extract title from Bolha link.
    
    Example: https://www.bolha.com/avtodeli-motor-in-deli/volvo-pumpa-2.5t-bencin-oglas-12227330
    Should return: "volvo-pumpa-2.5t-bencin" → "Volvo pumpa 2.5t bencin"
    """
    try:
        # Remove protocol and domain
        # Pattern: /category/title-oglas-ID
        match = re.search(r'/([^/]+)/(.+?)-oglas-\d+/?$', link)
        if match:
            title_slug = match.group(2)
            # Convert slug to readable: replace - with space, capitalize
            title = unquote(title_slug).replace('-', ' ').replace('+', ' ')
            # Title case first word
            return title.title() if title else None
        return None
    except Exception as e:
        print(f"Error extracting title from {link}: {e}")
        return None

def backfill_bolha_titles(db_path="bot.db"):
    """Update Bolha ads in MarketData with ime_avta from link text."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    
    print("=" * 80)
    print("BACKFILL: Bolha ads with ime_avta extracted from links")
    print("=" * 80)
    
    # Find Bolha ads in MarketData that lack ime_avta in snippet_data
    c.execute("""
        SELECT m.content_id, m.link, m.snippet_data
        FROM MarketData m
        WHERE m.content_id LIKE 'bo_%'
        AND (m.snippet_data IS NULL 
             OR m.snippet_data NOT LIKE '%ime_avta%')
    """)
    
    bolha_ads_to_fix = c.fetchall()
    print(f"\nFound {len(bolha_ads_to_fix)} Bolha ads needing backfill\n")
    
    updated = 0
    skipped = 0
    for row in bolha_ads_to_fix:
        content_id = row['content_id']
        link = row['link']
        snippet_data_raw = row['snippet_data']
        
        # Parse existing snippet_data
        try:
            snippet_data = json.loads(snippet_data_raw) if snippet_data_raw else {}
        except:
            snippet_data = {}
        
        # If ime_avta already there, skip
        if 'ime_avta' in snippet_data:
            continue
        
        # Extract title from link
        ime_avta = extract_title_from_bolha_link(link)
        if ime_avta:
            # Add to snippet_data
            snippet_data['ime_avta'] = ime_avta
            snippet_data_json = json.dumps(snippet_data, ensure_ascii=False)
            
            # Update MarketData
            c.execute("""
                UPDATE MarketData 
                SET snippet_data = ?
                WHERE content_id = ?
            """, (snippet_data_json, content_id))
            
            updated += 1
            print(f"[OK] {content_id}: {ime_avta}")
        else:
            print(f"[SKIP] {content_id}: could not extract title from link")
            skipped += 1
    
    conn.commit()
    conn.close()
    
    print(f"\n{'=' * 80}")
    print(f"[DONE] Updated {updated} Bolha ads with ime_avta")
    if skipped:
        print(f"[WARN] Skipped {skipped} ads (could not extract title)")
    print(f"{'=' * 80}")
    return updated
if __name__ == "__main__":
    db_path = sys.argv[1] if len(sys.argv) > 1 else "bot.db"
    backfill_bolha_titles(db_path)
