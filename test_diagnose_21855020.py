"""
Deep diagnosis: Why ads aren't being sent despite being processed
"""

from database import Database
import sqlite3

db = Database('bot.db')
conn = db.get_connection()

ad_id = '21855020'

print("="*80)
print(f"DIAGNOSIS: Ad {ad_id} (processed by AI but not sent)")
print("="*80)

# 1. Is ad in MarketData?
print("\n1. Checking MarketData...")
market = conn.execute("SELECT * FROM MarketData WHERE content_id = ?", (ad_id,)).fetchone()
if market:
    print(f"   ✅ FOUND in MarketData")
    print(f"      - enriched: {market[10] if len(market) > 10 else 'N/A'}")
    print(f"      - created: {market[8]}")
else:
    print(f"   ❌ NOT in MarketData - THIS IS THE PROBLEM!")

# 2. Is ad in ScrapedData?
print("\n2. Checking ScrapedData...")
scraped = conn.execute("SELECT * FROM ScrapedData WHERE content_id = ?", (ad_id,)).fetchone()
if scraped:
    print(f"   ✅ FOUND in ScrapedData")
    print(f"      - url_id: {scraped[1]}")
    print(f"      - link: {scraped[2]}")
else:
    print(f"   ❌ NOT in ScrapedData - THIS IS THE PROBLEM!")

# 3. Is ad in SentAds for any user?
print("\n3. Checking SentAds...")
sent = conn.execute("SELECT * FROM SentAds WHERE content_id = ?", (ad_id,)).fetchall()
if sent:
    print(f"   ⚠️  FOUND in SentAds ({len(sent)} users) - Already sent!")
    for s in sent:
        print(f"      - User {s[1]}, sent at {s[3]}")
else:
    print(f"   ✅ NOT in SentAds - Good, it's a new ad")

# 4. Check users tracking URL 60
print("\n4. Checking who tracks URL 60...")
users = conn.execute("""
    SELECT t.telegram_id, u.is_active, t.last_notified_at
    FROM Tracking t
    JOIN Users u ON t.telegram_id = u.telegram_id
    WHERE t.url_id = 60
""").fetchall()
print(f"   Found {len(users)} users tracking URL 60:")
for u in users:
    print(f"      - User {u[0]}, active={u[1]}, last_notified={u[2]}")

# 5. Run the actual check_new_offers() query
print("\n5. Running check_new_offers() query for URL 60...")
query = """
    SELECT sd.*, t.telegram_id as target_user_id
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
    AND (
        t.last_notified_at IS NULL 
        OR julianday('now') - julianday(t.last_notified_at) >= t.notification_interval / 1440.0
    )
"""
results = conn.execute(query).fetchall()
print(f"   Results: {len(results)} ads to send")
if results:
    for r in results:
        print(f"      - Ad {r[3]} for user {r[-1]}")
else:
    print("   ❌ Query returned ZERO results - debugging individual filters...")
    
    # Debug each filter
    print("\n6. Debugging individual filters...")
    
    # Base query
    base = conn.execute("SELECT COUNT(*) FROM ScrapedData WHERE url_id = 60").fetchone()[0]
    print(f"   - ScrapedData with url_id=60: {base}")
    
    # After JOIN with Tracking
    after_tracking = conn.execute("""
        SELECT COUNT(*) FROM ScrapedData sd
        JOIN Tracking t ON sd.url_id = t.url_id
        WHERE sd.url_id = 60
    """).fetchone()[0]
    print(f"   - After JOIN Tracking: {after_tracking}")
    
    # After JOIN with Users
    after_users = conn.execute("""
        SELECT COUNT(*) FROM ScrapedData sd
        JOIN Tracking t ON sd.url_id = t.url_id
        JOIN Users us ON t.telegram_id = us.telegram_id
        WHERE sd.url_id = 60 AND us.is_active = 1
    """).fetchone()[0]
    print(f"   - After JOIN Users (is_active=1): {after_users}")
    
    # After SentAds check
    after_sentads = conn.execute("""
        SELECT COUNT(*) FROM ScrapedData sd
        JOIN Tracking t ON sd.url_id = t.url_id
        JOIN Users us ON t.telegram_id = us.telegram_id
        WHERE sd.url_id = 60 AND us.is_active = 1
        AND NOT EXISTS (
            SELECT 1 FROM SentAds sa 
            WHERE sa.content_id = sd.content_id 
            AND sa.telegram_id = t.telegram_id
        )
    """).fetchone()[0]
    print(f"   - After SentAds filter: {after_sentads}")
    
    # After MarketData check
    after_marketdata = conn.execute("""
        SELECT COUNT(*) FROM ScrapedData sd
        JOIN Tracking t ON sd.url_id = t.url_id
        JOIN Users us ON t.telegram_id = us.telegram_id
        WHERE sd.url_id = 60 AND us.is_active = 1
        AND NOT EXISTS (
            SELECT 1 FROM SentAds sa 
            WHERE sa.content_id = sd.content_id 
            AND sa.telegram_id = t.telegram_id
        )
        AND EXISTS (
            SELECT 1 FROM MarketData md 
            WHERE md.content_id = sd.content_id
        )
    """).fetchone()[0]
    print(f"   - After MarketData filter: {after_marketdata}")
    
    # After interval check
    after_interval = conn.execute("""
        SELECT COUNT(*) FROM ScrapedData sd
        JOIN Tracking t ON sd.url_id = t.url_id
        JOIN Users us ON t.telegram_id = us.telegram_id
        WHERE sd.url_id = 60 AND us.is_active = 1
        AND NOT EXISTS (
            SELECT 1 FROM SentAds sa 
            WHERE sa.content_id = sd.content_id 
            AND sa.telegram_id = t.telegram_id
        )
        AND EXISTS (
            SELECT 1 FROM MarketData md 
            WHERE md.content_id = sd.content_id
        )
        AND (
            t.last_notified_at IS NULL 
            OR julianday('now') - julianday(t.last_notified_at) >= t.notification_interval / 1440.0
        )
    """).fetchone()[0]
    print(f"   - After interval filter: {after_interval}")

print("\n" + "="*80)
print("DIAGNOSIS COMPLETE")
print("="*80)

conn.close()
