"""
Analyze why check_new_offers() returns no ads
"""
from database import Database

db = Database('bot.db')
conn = db.get_connection()

# Get one example URL that has been scanned
url_data = conn.execute("""
    SELECT url_id, telegram_name 
    FROM Tracking t
    JOIN Users u ON t.telegram_id = u.telegram_id
    LIMIT 1
""").fetchone()

if not url_data:
    print("No tracking data found!")
    exit(1)

url_id, user_name = url_data[0], url_data[1]
print(f"Analyzing URL {url_id} tracked by user {user_name}")
print("="*60)

# 1. Check if this URL has been scanned
scans = conn.execute("""
    SELECT COUNT(*) 
    FROM ScraperLogs 
    WHERE url_id = ? AND status_code = 200
""", (url_id,)).fetchone()[0]
print(f"\n1. Scans completed: {scans}")

# 2. Check what's in SentAds for all users on this URL
users_tracking = conn.execute("""
    SELECT DISTINCT telegram_id 
    FROM Tracking 
    WHERE url_id = ?
""", (url_id,)).fetchall()
print(f"2. Users tracking this URL: {len(users_tracking)}")

for user_row in users_tracking:
    user_id = user_row[0]
    user_name = conn.execute("SELECT telegram_name FROM Users WHERE telegram_id = ?", (user_id,)).fetchone()[0]
    sent_count = conn.execute("""
        SELECT COUNT(*) 
        FROM SentAds 
        WHERE telegram_id = ?
    """, (user_id,)).fetchone()[0]
    print(f"   - User {user_name} ({user_id}): {sent_count} ads marked as sent")

# 3. Check what's in MarketData
market_count = conn.execute("SELECT COUNT(*) FROM MarketData").fetchone()[0]
print(f"\n3. Total ads in MarketData: {market_count}")

# 4. Check what's in ScrapedData for this URL
scraped = conn.execute("""
    SELECT COUNT(*) 
    FROM ScrapedData 
    WHERE url_id = ?
""", (url_id,)).fetchone()[0]
print(f"4. Ads in ScrapedData for this URL: {scraped}")

# 5. Simulate check_new_offers() query
print(f"\n5. Running check_new_offers() logic for URL {url_id}:")
query = """
    SELECT sd.content_id, sd.ime_avta, t.telegram_id
    FROM ScrapedData sd
    JOIN Tracking t ON sd.url_id = t.url_id
    WHERE sd.url_id = ?
    AND NOT EXISTS (
        SELECT 1 FROM SentAds sa 
        WHERE sa.telegram_id = t.telegram_id 
        AND sa.content_id = sd.content_id
    )
"""
results = conn.execute(query, (url_id,)).fetchall()
print(f"   Query returned {len(results)} ads to send")
if results:
    for content_id, car, user_id in results[:3]:
        print(f"     - {content_id}: {car}")

# 6. Why is ScrapedData empty?
print(f"\n6. Why is ScrapedData empty for this URL?")
print(f"   ScrapedData gets populated by insert_scraped_data() in scraper.py")
print(f"   insert_scraped_data() is called for each ad in final_results")
print(f"   final_results contains ads from:")
print(f"     a) AI processing (ads_to_ai_batch)")
print(f"     b) Manual fallback parsing")
print(f"   ads_to_ai_batch contains ads where is_ad_new() returns TRUE")
print(f"   is_ad_new() checks if content_id is NOT in SentAds (for ANY user)")

# 7. Check if SentAds has ALL ads on website
print(f"\n7. Checking if first-scan initialization filled SentAds...")
first_scan_log = conn.execute("""
    SELECT timestamp_utc, bytes_used, error_msg
    FROM ScraperLogs
    WHERE url_id = ?
    ORDER BY timestamp_utc ASC
    LIMIT 1
""", (url_id,)).fetchone()

if first_scan_log:
    print(f"   First scan at: {first_scan_log[0]}")
    print(f"   Bytes used: {first_scan_log[1]}")
    print(f"   Status: {first_scan_log[2]}")
    print(f"\n   On first scan, the scraper:")
    print(f"   - Found all ads on page")
    print(f"   - Marked them ALL as 'sent' via bulk_add_sent_ads()")
    print(f"   - Did NOT add them to ScrapedData")
    print(f"   - Returned immediately (continue statement)")

print(f"\n8. Conclusion:")
print(f"   The system will only send ads IF:")
print(f"   - New ads appear on website (not seen before)")
print(f"   - AND they're not already in SentAds")
print(f"   - AND they're added to ScrapedData during scanning")
print(f"\n   Currently, ScrapedData is EMPTY because no 'new' ads passed")
print(f"   the is_ad_new() check during recent scans.")
print(f"\n   Possible reasons:")
print(f"   A) Website only has old ads (same ones as first scan)")
print(f"   B) All new ads are somehow already in SentAds")
print(f"   C) There's a bug in is_ad_new() logic")

conn.close()
