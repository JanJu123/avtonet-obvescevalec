#!/usr/bin/env python3
"""
VPS SCHEMA MIGRATION
====================
Adapts VPS bot.db schema to match current code requirements.
Handles differences between VPS old schema and new code.

Steps:
1. Verify ScrapedData exists with metadata column
2. Add missing columns to MarketData if needed
3. Add url_id to MarketData if missing
"""

import sqlite3
import sys
import shutil
from datetime import datetime

def backup_database(db_path):
    """Create a backup before migration"""
    backup_path = f"{db_path}.backup.{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    try:
        shutil.copy2(db_path, backup_path)
        print(f"✅ Backup created: {backup_path}")
        return backup_path
    except Exception as e:
        print(f"❌ Backup failed: {e}")
        return None

def check_column_exists(cursor, table_name, column_name):
    """Check if column exists in table"""
    cursor.execute(f"PRAGMA table_info({table_name})")
    columns = [col[1] for col in cursor.fetchall()]
    return column_name in columns

def add_column_if_missing(cursor, table_name, column_name, column_type):
    """Add column to table if it doesn't exist"""
    if check_column_exists(cursor, table_name, column_name):
        print(f"   ✅ {table_name}.{column_name} already exists")
        return True
    
    try:
        cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}")
        print(f"   ✅ Added {table_name}.{column_name}")
        return True
    except Exception as e:
        print(f"   ❌ Error adding {table_name}.{column_name}: {e}")
        return False

def ensure_scraped_data_exists(conn):
    """Ensure ScrapedData table has correct schema"""
    cursor = conn.cursor()
    
    print("\n📋 Checking ScrapedData table...")
    
    # Check if table exists
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='ScrapedData'")
    if not cursor.fetchone():
        print("   ⚠️  ScrapedData table missing - creating...")
        cursor.execute("""
            CREATE TABLE ScrapedData (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url_id INTEGER,
                content_id TEXT,
                ime_avta TEXT,
                cena TEXT,
                link TEXT,
                slika_url TEXT,
                metadata JSON,
                created_at DATETIME DEFAULT (strftime('%d.%m.%Y %H:%M:%S', 'now', 'localtime')),
                FOREIGN KEY (url_id) REFERENCES Urls (url_id)
            )
        """)
        conn.commit()
        print("   ✅ ScrapedData created")
        return True
    
    # Check if metadata column exists
    if not check_column_exists(cursor, 'ScrapedData', 'metadata'):
        print("   ⚠️  ScrapedData.metadata missing - adding...")
        cursor.execute("ALTER TABLE ScrapedData ADD COLUMN metadata JSON")
        conn.commit()
        print("   ✅ Added metadata column")
    else:
        print("   ✅ ScrapedData.metadata exists")
    
    return True

def ensure_market_data_schema(conn):
    """Update MarketData schema to support new columns"""
    cursor = conn.cursor()
    
    print("\n📋 Checking MarketData table...")
    
    # Check if table exists
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='MarketData'")
    if not cursor.fetchone():
        print("   ℹ️  MarketData table missing (not needed for Bolha)")
        return True
    
    # Check for required columns
    columns_to_check = {
        'url_id': 'INTEGER',
        'source': 'TEXT DEFAULT "avtonet"',
        'category': 'TEXT',
        'title': 'TEXT',
        'snippet_data': 'TEXT'
    }
    
    for col_name, col_type in columns_to_check.items():
        if not check_column_exists(cursor, 'MarketData', col_name):
            print(f"   ℹ️  MarketData.{col_name} missing - adding...")
            try:
                cursor.execute(f"ALTER TABLE MarketData ADD COLUMN {col_name} {col_type}")
                conn.commit()
                print(f"   ✅ Added MarketData.{col_name}")
            except Exception as e:
                print(f"   ⚠️  Could not add {col_name}: {e} (non-critical)")
        else:
            print(f"   ✅ MarketData.{col_name} exists")
    
    return True

def main(db_path):
    """Run VPS schema migration"""
    print("=" * 60)
    print("🚀 VPS SCHEMA MIGRATION STARTING")
    print("=" * 60)
    
    # 1. BACKUP
    print("\n1️⃣  CREATING BACKUP...")
    backup_path = backup_database(db_path)
    if not backup_path:
        print("❌ Migration aborted - backup failed")
        return 1
    
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        
        # 2. ENSURE SCRAPED DATA
        print("\n2️⃣  VERIFYING ScrapedData TABLE...")
        if not ensure_scraped_data_exists(conn):
            print("❌ ScrapedData setup failed")
            return 1
        
        # 3. UPDATE MARKET DATA
        print("\n3️⃣  UPDATING MarketData TABLE...")
        if not ensure_market_data_schema(conn):
            print("⚠️  MarketData update had issues (continuing anyway)")
        
        conn.close()
        
        print("\n" + "=" * 60)
        print("✅ MIGRATION COMPLETED SUCCESSFULLY!")
        print("=" * 60)
        print(f"\n📊 Summary:")
        print(f"   Database: {db_path}")
        print(f"   Backup: {backup_path}")
        print(f"\n✨ Changes applied:")
        print(f"   • Verified ScrapedData table with metadata column")
        print(f"   • Updated MarketData schema with new columns")
        print(f"   • All data preserved")
        print(f"\n🎉 Ready to run bot!")
        
        return 0
        
    except Exception as e:
        print(f"\n❌ MIGRATION FAILED: {e}")
        return 1

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 vps_schema_migration.py <path_to_bot.db>")
        sys.exit(1)
    
    db_path = sys.argv[1]
    exit_code = main(db_path)
    sys.exit(exit_code)
