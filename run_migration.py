#!/usr/bin/env python3
"""
Migration script: Convert MarketData from Avtonet-specific to unified multi-source schema.
- Backs up database
- Creates new schema with an_ prefix for content_id
- Migrates all data preserving integrity
- Validates migration success
"""

import sqlite3
import json
import shutil
from datetime import datetime
from pathlib import Path

DB_PATH = Path("bot.db")
BACKUP_PATH = Path(f"bot.db.backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}")

def backup_database():
    """Create timestamped backup of database."""
    print(f"📦 Backing up database to {BACKUP_PATH}...")
    shutil.copy2(DB_PATH, BACKUP_PATH)
    print(f"✅ Backup created: {BACKUP_PATH}")

def get_connection():
    """Get database connection."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn

def count_old_table():
    """Count rows in old MarketData table."""
    conn = get_connection()
    cursor = conn.cursor()
    count = cursor.execute("SELECT COUNT(*) FROM MarketData").fetchone()[0]
    conn.close()
    return count

def rename_old_table():
    """Rename old MarketData to MarketData_old for rollback."""
    print("🔄 Renaming old MarketData table...")
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("ALTER TABLE MarketData RENAME TO MarketData_old")
    conn.commit()
    conn.close()
    print("✅ Old table renamed to MarketData_old")

def create_new_schema():
    """Create new unified MarketData schema."""
    print("📋 Creating new MarketData schema...")
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE MarketData (
            content_id TEXT PRIMARY KEY,
            source TEXT DEFAULT 'avtonet',
            category TEXT DEFAULT 'car',
            title TEXT,
            price TEXT,
            link TEXT,
            snippet_data TEXT,
            enriched INTEGER DEFAULT 0,
            enriched_json TEXT,
            created_at DATETIME DEFAULT (strftime('%d.%m.%Y %H:%M:%S', 'now', 'localtime')),
            updated_at DATETIME DEFAULT (strftime('%d.%m.%Y %H:%M:%S', 'now', 'localtime'))
        )
    """)
    conn.commit()
    conn.close()
    print("✅ New schema created")

def migrate_data():
    """Migrate data from old to new schema."""
    print("🔄 Migrating data...")
    conn = get_connection()
    cursor = conn.cursor()
    
    errors = []
    migrated = 0
    
    try:
        # Fetch all rows from old table
        cursor.execute("SELECT * FROM MarketData_old")
        rows = cursor.fetchall()
        
        for row in rows:
            try:
                old_id = str(row['content_id'])
                new_content_id = f"an_{old_id}"
                
                # Build snippet_data JSON from old car-specific fields
                snippet_data = {
                    'leto_1_reg': row['leto_1_reg'],
                    'prevozenih': row['prevozenih'],
                    'gorivo': row['gorivo'],
                    'menjalnik': row['menjalnik'],
                    'motor': row['motor']
                }
                
                # Map old title from ime_avta
                title = row['ime_avta']
                price = row['cena']
                link = row['link']
                
                # Insert into new schema
                cursor.execute("""
                    INSERT INTO MarketData (
                        content_id, source, category, title, price, link,
                        snippet_data, enriched, enriched_json, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    new_content_id,
                    'avtonet',
                    'car',
                    title,
                    price,
                    link,
                    json.dumps(snippet_data),
                    row['enriched'],
                    row['enriched_json'],
                    row['created_at'],
                    row['created_at']  # Use created_at as updated_at initially
                ))
                migrated += 1
            except Exception as e:
                errors.append(f"Row {old_id}: {str(e)}")
        
        conn.commit()
        print(f"✅ Migrated {migrated} rows")
        
        if errors:
            print(f"⚠️  {len(errors)} errors during migration:")
            for error in errors[:5]:  # Show first 5 errors
                print(f"  - {error}")
            if len(errors) > 5:
                print(f"  ... and {len(errors) - 5} more")
    
    except Exception as e:
        print(f"❌ Migration failed: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()
    
    return migrated, errors

def verify_migration():
    """Verify migration was successful."""
    print("✔️  Verifying migration...")
    conn = get_connection()
    cursor = conn.cursor()
    
    old_count = cursor.execute("SELECT COUNT(*) FROM MarketData_old").fetchone()[0]
    new_count = cursor.execute("SELECT COUNT(*) FROM MarketData").fetchone()[0]
    
    conn.close()
    
    print(f"  Old table rows: {old_count}")
    print(f"  New table rows: {new_count}")
    
    if old_count == new_count:
        print(f"✅ Migration verified! All {old_count} rows migrated successfully")
        return True
    else:
        print(f"❌ Row count mismatch! Expected {old_count}, got {new_count}")
        return False

def check_prefixes():
    """Check that all content_ids have an_ prefix."""
    print("🔍 Checking content_id prefixes...")
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT content_id FROM MarketData WHERE content_id NOT LIKE 'an_%'")
    bad_ids = cursor.fetchall()
    
    conn.close()
    
    if bad_ids:
        print(f"❌ Found {len(bad_ids)} rows without an_ prefix")
        return False
    else:
        print(f"✅ All content_ids properly prefixed with an_")
        return True

def check_snippet_data():
    """Verify snippet_data is valid JSON."""
    print("📊 Validating snippet_data JSON...")
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT content_id, snippet_data FROM MarketData LIMIT 5")
    samples = cursor.fetchall()
    
    invalid = []
    for row in samples:
        try:
            json.loads(row['snippet_data'])
        except (json.JSONDecodeError, TypeError):
            invalid.append(row['content_id'])
    
    conn.close()
    
    if invalid:
        print(f"❌ Found {len(invalid)} rows with invalid JSON")
        return False
    else:
        print(f"✅ snippet_data contains valid JSON")
        return True

def main():
    """Run full migration."""
    print("=" * 60)
    print("🚀 MARKETDATA SCHEMA MIGRATION")
    print("=" * 60)
    
    try:
        # Backup
        backup_database()
        old_count = count_old_table()
        print(f"📊 Found {old_count} rows to migrate\n")
        
        # Rename old table
        rename_old_table()
        
        # Create new schema
        create_new_schema()
        
        # Migrate data
        migrated, errors = migrate_data()
        
        # Verify
        print()
        if verify_migration():
            check_prefixes()
            check_snippet_data()
            print()
            print("=" * 60)
            print("✅ MIGRATION COMPLETE!")
            print("=" * 60)
            print(f"✓ Backup: {BACKUP_PATH}")
            print(f"✓ Rollback table: MarketData_old")
            print(f"✓ New schema active: MarketData")
            print(f"✓ Rows migrated: {migrated}")
            if errors:
                print(f"⚠️  Errors encountered: {len(errors)}")
            return True
        else:
            print("❌ Migration failed verification!")
            return False
    
    except Exception as e:
        print(f"\n❌ MIGRATION FAILED: {e}")
        print(f"Restore from backup: {BACKUP_PATH}")
        return False

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
