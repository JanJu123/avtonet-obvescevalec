"""
Check why ads 21711909 and 21855039 aren't being sent despite AI processing
"""

from database import Database
import sqlite3

db = Database('bot.db')
conn = db.get_connection()

ads = ['21711909', '21855039']

for ad_id in ads:
    print(f"\n{'='*80}")
    print(f"Checking ad {ad_id}")
    print('='*80)
    
    # 1. In MarketData?
    market = conn.execute("SELECT * FROM MarketData WHERE content_id = ?", (ad_id,)).fetchone()
    print(f"MarketData: {'✅ YES' if market else '❌ NO'}")
    
    # 2. In ScrapedData?
    scraped = conn.execute("SELECT * FROM ScrapedData WHERE content_id = ?", (ad_id,)).fetchone()
    print(f"ScrapedData: {'✅ YES' if scraped else '❌ NO'}")
    if scraped:
        print(f"  - url_id: {scraped[1]}")
    
    # 3. In SentAds?
    sent = conn.execute("SELECT * FROM SentAds WHERE content_id = ?", (ad_id,)).fetchall()
    print(f"SentAds: {'❌ YES (already sent)' if sent else '✅ NO (can be sent)'}")
    if sent:
        for s in sent:
            print(f"  - To user {s[1]} at {s[3]}")

# 4. Check Tracking table for user 8004323652 (Jan)
print(f"\n{'='*80}")
print("User 8004323652 (Jan) tracking status")
print('='*80)
tracking = conn.execute("""
    SELECT url_id, last_notified_at, notification_interval
    FROM Tracking WHERE telegram_id = 8004323652
""").fetchall()
for t in tracking:
    print(f"URL {t[0]}: last_notified={t[1]}, interval={t[2]} min")

# 5. Run check_new_offers query for URL 60
print(f"\n{'='*80}")
print("Running check_new_offers() for URL 60")
print('='*80)

try:
    query = """
        SELECT sd.content_id, sd.link, t.telegram_id as target_user_id, t.last_notified_at
        FROM ScrapedData sd
        JOIN Tracking t ON sd.url_id = t.url_id
        JOIN Users us ON t.telegram_id = us.telegram_id
        WHERE sd.url_id IN (60)
        AND us.is_active = 1
        AND NOT EXISTS (
            SELECT 1 FROM SentAds sa 
            WHERE sa.content_id = sd.content_id 
            AND sa.telegram_id = t.telegram_id
        )
        AND EXISTS (
            SELECT 1 FROM MarketData md 
            WHERE md.content_id = sd.content_id
        )
    """
    results = conn.execute(query).fetchall()
    print(f"Found {len(results)} ads (before interval check)")
    for r in results:
        print(f"  - Ad {r[0]} for user {r[2]}, last_notified={r[3]}")
except Exception as e:
    print(f"Query error: {e}")

conn.close()
