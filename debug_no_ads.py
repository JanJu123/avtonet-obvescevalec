"""
Check why check_new_offers returns 0 despite ScrapedData having records
"""

import sqlite3
from database import Database
from data_manager import DataManager

db = Database('bot.db')
dm = DataManager(db)
conn = db.get_connection()

print("=== DIAGNOSTIC: Why no ads are being sent ===\n")

# Get current ScrapedData count
scraped_count = conn.execute("SELECT COUNT(*) FROM ScrapedData").fetchone()[0]
print(f"Total ScrapedData records: {scraped_count}")

if scraped_count == 0:
    print("\n❌ ScrapedData is empty! Bot hasn't run scraper yet or cleared it.")
    exit()

# Get sample ads from ScrapedData
print("\nSample ads in ScrapedData:")
samples = conn.execute("""
    SELECT sd.url_id, sd.content_id, sd.ime_avta, sd.cena
    FROM ScrapedData sd
    LIMIT 5
""").fetchall()

for url_id, cid, name, price in samples:
    print(f"  URL {url_id}: {cid} - {name} - {price}")

# Check how many are in MarketData
in_market = conn.execute("""
    SELECT COUNT(*) 
    FROM ScrapedData sd
    WHERE EXISTS (SELECT 1 FROM MarketData md WHERE md.content_id = sd.content_id)
""").fetchone()[0]

print(f"\nAds in MarketData: {in_market}/{scraped_count}")

if in_market == 0:
    print("❌ PROBLEM: No ads in MarketData! The EXISTS check in check_new_offers will fail.")
    print("   This means ads are in ScrapedData but not processed into MarketData yet.")
    exit()

# Check which URLs have active users tracking them
print("\nChecking users...")
url_ids = [row[0] for row in conn.execute("SELECT DISTINCT url_id FROM ScrapedData").fetchall()]
print(f"URLs in ScrapedData: {url_ids}")

for url_id in url_ids:
    users = conn.execute("""
        SELECT COUNT(*) 
        FROM Tracking t
        JOIN Users u ON t.telegram_id = u.telegram_id
        WHERE t.url_id = ? AND u.is_active = 1
    """, (url_id,)).fetchone()[0]
    print(f"  URL {url_id}: {users} active users")

# Run the actual check_new_offers query manually
print("\nRunning check_new_offers logic...")

query = f"""
    SELECT sd.content_id, sd.url_id, t.telegram_id as target_user_id
    FROM ScrapedData sd
    JOIN Tracking t ON sd.url_id = t.url_id
    JOIN Users us ON t.telegram_id = us.telegram_id
    WHERE us.is_active = 1
"""

all_combinations = conn.execute(query).fetchall()
print(f"Total ad-user combinations (active users): {len(all_combinations)}")

# Now add the filters one by one
query_with_sentads = f"""
    SELECT sd.content_id, sd.url_id, t.telegram_id
    FROM ScrapedData sd
    JOIN Tracking t ON sd.url_id = t.url_id
    JOIN Users us ON t.telegram_id = us.telegram_id
    WHERE us.is_active = 1
    AND NOT EXISTS (
        SELECT 1 FROM SentAds sa 
        WHERE sa.telegram_id = t.telegram_id 
        AND sa.content_id = sd.content_id
    )
"""

after_sentads = conn.execute(query_with_sentads).fetchall()
print(f"After filtering SentAds: {len(after_sentads)}")

# Add MarketData filter
query_with_market = f"""
    SELECT sd.content_id, sd.url_id, t.telegram_id
    FROM ScrapedData sd
    JOIN Tracking t ON sd.url_id = t.url_id
    JOIN Users us ON t.telegram_id = us.telegram_id
    WHERE us.is_active = 1
    AND NOT EXISTS (
        SELECT 1 FROM SentAds sa 
        WHERE sa.telegram_id = t.telegram_id 
        AND sa.content_id = sd.content_id
    )
    AND EXISTS (
        SELECT 1 FROM MarketData md
        WHERE md.content_id = sd.content_id
    )
"""

after_market = conn.execute(query_with_market).fetchall()
print(f"After filtering MarketData: {len(after_market)}")

# Add interval filter
query_full = f"""
    SELECT sd.content_id, sd.url_id, t.telegram_id, t.last_notified_at, us.scan_interval
    FROM ScrapedData sd
    JOIN Tracking t ON sd.url_id = t.url_id
    JOIN Users us ON t.telegram_id = us.telegram_id
    WHERE us.is_active = 1
    AND NOT EXISTS (
        SELECT 1 FROM SentAds sa 
        WHERE sa.telegram_id = t.telegram_id 
        AND sa.content_id = sd.content_id
    )
    AND EXISTS (
        SELECT 1 FROM MarketData md
        WHERE md.content_id = sd.content_id
    )
    AND (
        t.last_notified_at IS NULL
        OR ( (strftime('%s','now','localtime') - strftime('%s', t.last_notified_at)) / 60.0 ) >= (us.scan_interval - 0.1)
    )
"""

final_results = conn.execute(query_full).fetchall()
print(f"After interval check: {len(final_results)}")

if len(final_results) > 0:
    print("\n✅ Should have ads to send!")
    for cid, url_id, uid, last_notified, interval in final_results[:3]:
        print(f"  - User {uid}, URL {url_id}, Ad {cid}, Last: {last_notified}, Interval: {interval}min")
else:
    print("\n❌ No ads to send after all filters.")
    
    # Debug: which filter is blocking?
    if len(all_combinations) == 0:
        print("   Problem: No active users tracking these URLs")
    elif len(after_sentads) == 0:
        print("   Problem: All ads already in SentAds for these users")
    elif len(after_market) == 0:
        print("   Problem: Ads in ScrapedData but not in MarketData")
    else:
        print("   Problem: Interval check failing (users notified too recently)")
        # Show some examples
        examples = conn.execute(query_with_market + " LIMIT 3").fetchall()
        for cid, url_id, uid in examples:
            tracking = conn.execute("""
                SELECT last_notified_at, 
                       (strftime('%s','now','localtime') - strftime('%s', last_notified_at)) / 60.0 as mins_since
                FROM Tracking t
                JOIN Users u ON t.telegram_id = u.telegram_id
                WHERE t.telegram_id = ? AND t.url_id = ?
            """, (uid, url_id)).fetchone()
            if tracking:
                print(f"     User {uid}, URL {url_id}: Last notified {tracking[0]}, {tracking[1]:.1f} mins ago")
