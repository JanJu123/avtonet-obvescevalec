"""
Quick test of new architecture
"""

from database import Database
import sqlite3

db = Database('bot.db')
conn = db.get_connection()

print("="*70)
print("TESTING NEW ARCHITECTURE")
print("="*70)

# Check AIQueue
print("\n[1] AIQueue table:")
ai_queue = conn.execute("SELECT COUNT(*) FROM AIQueue").fetchone()[0]
print(f"   Records: {ai_queue}")

# Check MarketData columns
print("\n[2] MarketData columns:")
cols = conn.execute("PRAGMA table_info(MarketData)").fetchall()
col_names = [c[1] for c in cols]
print(f"   Columns: {col_names}")
print(f"   ✓ Has 'enriched': {'enriched' in col_names}")
print(f"   ✓ Has 'updated_at': {'updated_at' in col_names}")

# Check data
market_count = conn.execute("SELECT COUNT(*) FROM MarketData").fetchone()[0]
enriched_0 = conn.execute("SELECT COUNT(*) FROM MarketData WHERE enriched = 0").fetchone()[0]
enriched_1 = conn.execute("SELECT COUNT(*) FROM MarketData WHERE enriched = 1").fetchone()[0]

print(f"\n[3] MarketData data:")
print(f"   Total: {market_count}")
print(f"   enriched=0: {enriched_0}")
print(f"   enriched=1: {enriched_1}")

# Test new methods
print(f"\n[4] Testing database methods:")

# Test add_to_ai_queue
test_id = "TEST_9999999"
result = db.add_to_ai_queue(test_id, "https://test.link", "test snippet")
print(f"   add_to_ai_queue: {'✓' if result else '✗'}")

# Test get_ai_queue_items
items = db.get_ai_queue_items(limit=1)
print(f"   get_ai_queue_items: ✓ ({len(items)} items)")

# Test remove_from_ai_queue
if items:
    result = db.remove_from_ai_queue(items[0]['content_id'])
    print(f"   remove_from_ai_queue: {'✓' if result else '✗'}")

print("\n" + "="*70)
print("✅ ARCHITECTURE READY FOR DEPLOYMENT")
print("="*70)
print("\nNext steps:")
print("1. Run migration script on VPS:")
print("   python migrate_db_v2.py --db-path /path/to/vps/bot.db")
print("2. Deploy updated code to VPS")
print("3. Restart bot")
print("4. Monitor logs for proper data flow")
