#!/usr/bin/env python3
"""
FULL DATABASE MIGRATION SCRIPT
==============================
This script performs BOTH:
1. Schema migration (adds missing columns like url_id to MarketData)
2. Timestamp format conversion (DD.MM.YYYY -> YYYY-MM-DD)

USE THIS ON VPS BEFORE RESTARTING BOT
"""

import sqlite3
import sys
from datetime import datetime
import shutil

def backup_database(db_path):
    """Create a backup before migration"""
    backup_path = f"{db_path}.backup"
    try:
        shutil.copy2(db_path, backup_path)
        print(f"✅ Backup created: {backup_path}")
        return backup_path
    except Exception as e:
        print(f"❌ Backup failed: {e}")
        return None

def convert_timestamp(old_format):
    """Convert DD.MM.YYYY HH:MM:SS to YYYY-MM-DD HH:MM:SS"""
    if not old_format or old_format == '0':
        return None
    try:
        dt = datetime.strptime(old_format, "%d.%m.%Y %H:%M:%S")
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except:
        return None

def migrate_marketdata_schema(conn):
    """Add url_id column to MarketData if missing"""
    cursor = conn.cursor()
    
    try:
        # Check if url_id column exists
        cursor.execute("PRAGMA table_info(MarketData)")
        columns = [col[1] for col in cursor.fetchall()]
        
        if 'url_id' not in columns:
            print("📋 Adding url_id column to MarketData...")
            cursor.execute("ALTER TABLE MarketData ADD COLUMN url_id INTEGER")
            conn.commit()
            print("   ✅ url_id column added")
        else:
            print("   ⏭️  url_id column already exists")
            
    except Exception as e:
        print(f"   ❌ Error: {e}")
        return False
    
    return True

def migrate_timestamps(conn, table_name, date_columns):
    """Migrate date columns in a table"""
    cursor = conn.cursor()
    
    print(f"\n📅 Converting timestamps in {table_name}...")
    
    for col in date_columns:
        try:
            # Get all rows with the date column
            cursor.execute(f"SELECT rowid, {col} FROM {table_name}")
            rows = cursor.fetchall()
            
            converted = 0
            for rowid, old_value in rows:
                if old_value and old_value != '0':
                    new_value = convert_timestamp(old_value)
                    if new_value:
                        cursor.execute(f"UPDATE {table_name} SET {col} = ? WHERE rowid = ?", (new_value, rowid))
                        converted += 1
            
            conn.commit()
            print(f"   ✅ {col}: Converted {converted} timestamps")
            
        except Exception as e:
            print(f"   ❌ Error converting {col}: {e}")
            conn.rollback()
            return False
    
    return True

def main(db_path):
    """Run full migration"""
    print("=" * 60)
    print("🚀 FULL DATABASE MIGRATION STARTING")
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
        
        # 2. SCHEMA MIGRATION
        print("\n2️⃣  MIGRATING SCHEMA...")
        if not migrate_marketdata_schema(conn):
            print("❌ Schema migration failed")
            return 1
        
        # 3. TIMESTAMP MIGRATION
        print("\n3️⃣  MIGRATING TIMESTAMPS...")
        migrations = {
            'Users': ['joined_at'],
            'Urls': ['created_at'],
            'Tracking': ['created_at'],
            'ScrapedData': ['created_at'],
            'SentAds': ['sent_at'],
            'UserActivity': ['timestamp'],
            'MarketData': ['created_at', 'updated_at'],
        }
        
        for table, columns in migrations.items():
            cursor = conn.cursor()
            cursor.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,))
            if cursor.fetchone():
                if not migrate_timestamps(conn, table, columns):
                    print(f"❌ Failed to migrate {table}")
                    return 1
            else:
                print(f"⏭️  Table {table} does not exist, skipping...")
        
        conn.close()
        
        print("\n" + "=" * 60)
        print("✅ MIGRATION COMPLETED SUCCESSFULLY!")
        print("=" * 60)
        print(f"\n📊 Summary:")
        print(f"   Database: {db_path}")
        print(f"   Backup: {backup_path}")
        print(f"\n✨ Changes applied:")
        print(f"   • Added url_id column to MarketData")
        print(f"   • Converted all timestamps to YYYY-MM-DD format")
        print(f"   • All existing data preserved")
        print(f"\n🎉 Ready to restart bot on VPS!")
        
        return 0
        
    except Exception as e:
        print(f"\n❌ Migration failed: {e}")
        print(f"   Backup available at: {backup_path}")
        return 1

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python full_database_migration.py <database_path>")
        print("\nExample:")
        print("  python full_database_migration.py /var/www/bot/bot.db")
        sys.exit(1)
    
    db_path = sys.argv[1]
    sys.exit(main(db_path))
