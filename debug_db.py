from database import Database
from data_manager import DataManager

db = Database('bot.db')
dm = DataManager(db)

# Test the check_new_offers function with some sample URL IDs
conn = db.get_connection()

# Get sample URLs
urls = conn.execute('SELECT DISTINCT url_id FROM Tracking LIMIT 5').fetchall()
url_ids = [u[0] for u in urls]

print(f'Testing check_new_offers() with URL IDs: {url_ids}')
result = dm.check_new_offers(filter_url_ids=url_ids)
print(f'Found {len(result)} ads to send')

for ad in result:
    print(f'  - {ad["content_id"]}: {ad.get("ime_avta", "Unknown")}')

# Now check the actual query and what's in databases
print('\n=== DETAILED ANALYSIS ===')
scraped = conn.execute(f'SELECT COUNT(*) FROM ScrapedData WHERE url_id IN ({",".join(map(str, url_ids))})').fetchone()[0]
print(f'ScrapedData records in these URLs: {scraped}')

# Check for first-scan ads
print('\n=== FIRST SCAN STATUS ===')
for url_id in url_ids:
    is_first = db.is_first_scan(url_id)
    log_count = conn.execute('SELECT COUNT(*) FROM ScraperLogs WHERE url_id = ?', (url_id,)).fetchone()[0]
    print(f'  URL {url_id}: is_first={is_first}, log_count={log_count}')

conn.close()

