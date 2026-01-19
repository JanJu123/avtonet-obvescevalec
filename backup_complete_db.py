"""
Complete database backup: bot.db → test_bot.db
Copies ALL tables and data
"""
import sqlite3
import os

def backup_complete_database():
    """Backup entire bot.db to test_bot.db"""
    
    SOURCE_DB = "bot.db"
    TARGET_DB = "test_bot.db"
    
    print("="*70)
    print("🔄 COMPLETE DATABASE BACKUP: bot.db → test_bot.db")
    print("="*70)
    
    # Remove existing test_bot.db
    if os.path.exists(TARGET_DB):
        try:
            os.remove(TARGET_DB)
            print(f"✅ Removed existing {TARGET_DB}")
        except Exception as e:
            print(f"⚠️ Could not remove {TARGET_DB}: {e}")
            print("   Attempting to overwrite...")
    
    # Connect to source
    source_conn = sqlite3.connect(SOURCE_DB)
    
    # Use SQLite backup API
    target_conn = sqlite3.connect(TARGET_DB)
    
    print(f"\n📦 Backing up entire database...")
    source_conn.backup(target_conn)
    
    source_conn.close()
    target_conn.close()
    
    print("✅ Backup complete!")
    
    # Verify backup
    print("\n🔍 Verifying backup...")
    source_conn = sqlite3.connect(SOURCE_DB)
    target_conn = sqlite3.connect(TARGET_DB)
    
    source_cur = source_conn.cursor()
    target_cur = target_conn.cursor()
    
    # Get all tables from source
    source_cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
    source_tables = [row[0] for row in source_cur.fetchall()]
    
    # Get all tables from target
    target_cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
    target_tables = [row[0] for row in target_cur.fetchall()]
    
    print(f"\n📊 Verification Results:")
    print(f"   Source tables: {len(source_tables)}")
    print(f"   Target tables: {len(target_tables)}")
    
    all_match = True
    for table in source_tables:
        source_cur.execute(f"SELECT COUNT(*) FROM {table}")
        source_count = source_cur.fetchone()[0]
        
        target_cur.execute(f"SELECT COUNT(*) FROM {table}")
        target_count = target_cur.fetchone()[0]
        
        status = "✅" if source_count == target_count else "❌"
        print(f"   {status} {table}: {source_count} → {target_count}")
        
        if source_count != target_count:
            all_match = False
    
    source_conn.close()
    target_conn.close()
    
    if all_match:
        print("\n✅ ALL TABLES VERIFIED - Backup successful!")
    else:
        print("\n⚠️ Warning: Some table counts don't match!")
    
    print("\n" + "="*70)
    print(f"✅ Complete backup saved to: {TARGET_DB}")
    print("="*70)

if __name__ == "__main__":
    backup_complete_database()
