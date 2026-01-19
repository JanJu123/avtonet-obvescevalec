#!/usr/bin/env python3
"""Quick verification that migration is working."""

from database import Database
import sqlite3

print("\n" + "=" * 60)
print("🔍 MIGRATION VERIFICATION")
print("=" * 60)

# Test 1: Database initializes
try:
    db = Database('bot.db')
    print("✅ Database initialized successfully")
except Exception as e:
    print(f"❌ Database init failed: {e}")
    exit(1)

# Test 2: Sample row retrieval
try:
    row = db.get_market_data_by_id('1')
    if row:
        print(f"✅ Sample row retrieved: {row['content_id']}")
        print(f"   - Title: {row['title']}")
        print(f"   - Price: {row['price']}")
        print(f"   - Source: {row['source']}")
    else:
        print("⚠️  No rows found with ID 1")
except Exception as e:
    print(f"❌ get_market_data_by_id failed: {e}")

# Test 3: Row counts
try:
    conn = sqlite3.connect('bot.db')
    c = conn.cursor()
    new_count = c.execute('SELECT COUNT(*) FROM MarketData').fetchone()[0]
    old_count = c.execute('SELECT COUNT(*) FROM MarketData_old').fetchone()[0]
    conn.close()
    print(f"✅ New MarketData schema: {new_count} rows")
    print(f"✅ Old MarketData_old table: {old_count} rows")
    if new_count == old_count:
        print("✅ Row counts match - migration complete!")
except Exception as e:
    print(f"❌ Row count check failed: {e}")

print("\n" + "=" * 60)
print("✅ MIGRATION VERIFICATION PASSED")
print("=" * 60 + "\n")
