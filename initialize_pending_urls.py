#!/usr/bin/env python3
"""
Initialize ScraperLogs for newly added URLs
This fixes the issue where new URLs are never detected as "pending" because they have no ScraperLogs entry.
"""

import sqlite3
from datetime import datetime

def initialize_new_urls(db_path):
    """Add ScraperLogs entry for URLs that don't have one"""
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    
    print("🔧 Initializing ScraperLogs for new URLs...")
    
    # Find URLs in Tracking but not in ScraperLogs
    c.execute("""
        SELECT DISTINCT t.url_id, u.url
        FROM Tracking t
        JOIN Urls u ON t.url_id = u.url_id
        WHERE t.url_id NOT IN (SELECT DISTINCT url_id FROM ScraperLogs)
    """)
    
    new_urls = c.fetchall()
    
    if not new_urls:
        print("✅ All URLs already have ScraperLogs entries")
        conn.close()
        return
    
    print(f"\n📝 Found {len(new_urls)} URLs without ScraperLogs:")
    
    for url_id, url in new_urls:
        # Add initial ScraperLog entry (like it was just scanned)
        c.execute("""
            INSERT INTO ScraperLogs (url_id, status_code, found_count, duration, bytes_used, timestamp, timestamp_utc)
            VALUES (?, 200, 0, 0, 0, ?, CURRENT_TIMESTAMP)
        """, (url_id, datetime.now().strftime('%d.%m.%Y %H:%M:%S')))
        
        print(f"   ✅ URL {url_id}: {url[:40]}...")
    
    conn.commit()
    conn.close()
    
    print(f"\n🎉 Initialized {len(new_urls)} URLs - they'll be pending on next cycle!")

if __name__ == "__main__":
    import sys
    db_path = sys.argv[1] if len(sys.argv) > 1 else "test_bot.db"
    initialize_new_urls(db_path)
