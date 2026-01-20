#!/usr/bin/env python3
"""
DATABASE MIGRATION SCRIPT
==============================
This script performs schema migration:
- Adds url_id column to MarketData (required for JSON schema migration)

USE THIS ON VPS BEFORE RESTARTING BOT
"""

import sqlite3
import sys
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

def main(db_path):
    """Run migration"""
    print("=" * 60)
    print("🚀 DATABASE MIGRATION STARTING")
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
        
        conn.close()
        
        print("\n" + "=" * 60)
        print("✅ MIGRATION COMPLETED SUCCESSFULLY!")
        print("=" * 60)
        print(f"\n📊 Summary:")
        print(f"   Database: {db_path}")
        print(f"   Backup: {backup_path}")
        print(f"\n✨ Changes applied:")
        print(f"   • Added url_id column to MarketData")
        print(f"   • All existing data preserved")
        print(f"\n🎉 Ready for next step: migrate_to_json_schema.py")
        
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
