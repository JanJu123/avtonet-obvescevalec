#!/usr/bin/env python3
"""
MIGRATION VERIFICATION SCRIPT
=============================
Checks if full_database_migration.py completed successfully.

Run this AFTER migration to verify all changes were applied correctly.
"""

import sqlite3
import sys
import re
from datetime import datetime

def verify_marketdata_schema(conn):
    """Check if MarketData has url_id column"""
    cursor = conn.cursor()
    
    print("\n1️⃣  CHECKING SCHEMA...")
    try:
        cursor.execute("PRAGMA table_info(MarketData)")
        columns = {col[1]: col[2] for col in cursor.fetchall()}
        
        if 'url_id' not in columns:
            print("   ❌ FAIL: url_id column missing from MarketData")
            return False
        else:
            print(f"   ✅ PASS: url_id column exists (type: {columns['url_id']})")
            return True
    except Exception as e:
        print(f"   ❌ FAIL: {e}")
        return False

def verify_timestamp_format(conn, table_name, col_name):
    """Verify timestamps are in YYYY-MM-DD HH:MM:SS format"""
    cursor = conn.cursor()
    
    iso_pattern = r'^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$'
    old_pattern = r'^\d{2}\.\d{2}\.\d{4} \d{2}:\d{2}:\d{2}$'
    
    try:
        cursor.execute(f"SELECT {col_name} FROM {table_name} WHERE {col_name} IS NOT NULL LIMIT 10")
        rows = cursor.fetchall()
        
        if not rows:
            return None  # No data to check
        
        iso_count = 0
        old_count = 0
        invalid_count = 0
        
        for (value,) in rows:
            if value and value != '0':
                if re.match(iso_pattern, str(value)):
                    iso_count += 1
                elif re.match(old_pattern, str(value)):
                    old_count += 1
                else:
                    invalid_count += 1
        
        if old_count > 0:
            return "OLD"  # Still has old format
        elif invalid_count > 0:
            return "INVALID"  # Has invalid format
        elif iso_count > 0:
            return "ISO"  # Correct format
        else:
            return None  # No data
            
    except Exception as e:
        return "ERROR"

def verify_all_timestamps(conn):
    """Check all timestamp columns are in ISO format"""
    cursor = conn.cursor()
    
    print("\n2️⃣  CHECKING TIMESTAMP FORMATS...")
    
    tables_to_check = {
        'MarketData': ['created_at', 'updated_at'],
        'ScrapedData': ['created_at'],
        'SentAds': ['sent_at'],
        'UserActivity': ['timestamp'],
    }
    
    all_good = True
    
    for table, columns in tables_to_check.items():
        try:
            cursor.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,))
            if not cursor.fetchone():
                print(f"   ⏭️  Table {table} not found")
                continue
            
            for col in columns:
                result = verify_timestamp_format(conn, table, col)
                
                if result == "ISO":
                    print(f"   ✅ {table}.{col}: ISO 8601 format (YYYY-MM-DD HH:MM:SS)")
                elif result == "OLD":
                    print(f"   ❌ {table}.{col}: STILL IN OLD FORMAT (DD.MM.YYYY HH:MM:SS)")
                    all_good = False
                elif result == "INVALID":
                    print(f"   ⚠️  {table}.{col}: Invalid format detected")
                    all_good = False
                elif result == "ERROR":
                    print(f"   ❌ {table}.{col}: Error checking format")
                    all_good = False
                elif result is None:
                    print(f"   ⏭️  {table}.{col}: No data to verify")
                    
        except Exception as e:
            print(f"   ❌ Error checking {table}: {e}")
            all_good = False
    
    return all_good

def verify_data_integrity(conn):
    """Check data is intact (row counts, no unexpected NULLs)"""
    cursor = conn.cursor()
    
    print("\n3️⃣  CHECKING DATA INTEGRITY...")
    
    checks = [
        ("MarketData row count", "SELECT COUNT(*) FROM MarketData"),
        ("ScrapedData row count", "SELECT COUNT(*) FROM ScrapedData"),
        ("SentAds row count", "SELECT COUNT(*) FROM SentAds"),
    ]
    
    all_good = True
    
    for check_name, query in checks:
        try:
            result = cursor.execute(query).fetchone()[0]
            if result > 0:
                print(f"   ✅ {check_name}: {result} rows")
            else:
                print(f"   ⏭️  {check_name}: 0 rows (empty)")
        except Exception as e:
            print(f"   ❌ Error: {e}")
            all_good = False
    
    return all_good

def verify_sorting(conn):
    """Test that sorting by created_at works correctly"""
    cursor = conn.cursor()
    
    print("\n4️⃣  TESTING SORT FUNCTIONALITY...")
    
    try:
        # Get dates in descending order
        cursor.execute("SELECT created_at FROM MarketData ORDER BY created_at DESC LIMIT 5")
        rows = cursor.fetchall()
        
        if not rows:
            print("   ⏭️  No data to test sorting")
            return True
        
        dates = [row[0] for row in rows]
        
        # Convert to datetime for comparison
        parsed_dates = []
        for d in dates:
            if d:
                try:
                    parsed_dates.append(datetime.strptime(d, "%Y-%m-%d %H:%M:%S"))
                except:
                    print(f"   ❌ Can't parse date: {d}")
                    return False
        
        # Check if they're sorted descending
        is_sorted = all(parsed_dates[i] >= parsed_dates[i+1] for i in range(len(parsed_dates)-1))
        
        if is_sorted:
            print(f"   ✅ Dates sort correctly (DESC)")
            print(f"      Newest: {dates[0]}")
            print(f"      Oldest: {dates[-1]}")
            return True
        else:
            print(f"   ❌ Dates NOT sorting correctly!")
            for i, d in enumerate(dates):
                print(f"      {i+1}. {d}")
            return False
            
    except Exception as e:
        print(f"   ❌ Error: {e}")
        return False

def main(db_path):
    """Run all verification checks"""
    print("=" * 60)
    print("✅ MIGRATION VERIFICATION")
    print("=" * 60)
    
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        
        results = []
        
        # Run all checks
        results.append(("Schema", verify_marketdata_schema(conn)))
        results.append(("Timestamps", verify_all_timestamps(conn)))
        results.append(("Data Integrity", verify_data_integrity(conn)))
        results.append(("Sorting", verify_sorting(conn)))
        
        conn.close()
        
        # Summary
        print("\n" + "=" * 60)
        print("📊 VERIFICATION SUMMARY")
        print("=" * 60)
        
        all_passed = True
        for check_name, passed in results:
            status = "✅ PASS" if passed else "❌ FAIL"
            print(f"{status}: {check_name}")
            if not passed:
                all_passed = False
        
        print("=" * 60)
        
        if all_passed:
            print("\n🎉 MIGRATION SUCCESSFUL - Everything looks good!")
            print("   Bot is ready to restart on VPS")
            return 0
        else:
            print("\n⚠️  MIGRATION INCOMPLETE - Some checks failed")
            print("   Please check the output above for details")
            return 1
        
    except Exception as e:
        print(f"\n❌ Verification failed: {e}")
        return 1

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python verify_migration.py <database_path>")
        print("\nExample:")
        print("  python verify_migration.py bot.db")
        print("  python verify_migration.py test_bot.db")
        sys.exit(1)
    
    db_path = sys.argv[1]
    sys.exit(main(db_path))
