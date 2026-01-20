#!/usr/bin/env python3
"""
CLEAN MARKETDATA SCHEMA MIGRATION
==================================
Consolidates MarketData schema to be source-agnostic.

Current problem: MarketData has both old Avtonet columns (ime_avta, cena, leto_1_reg, etc)
AND new multi-source columns (source, category, title, snippet_data). This is messy.

Solution: Move all source-specific fields to snippet_data JSON, keep only:
- content_id (PK)
- link
- price
- source
- category
- created_at
- url_id (for relationships)

All other fields go to snippet_data JSON.
"""

import sqlite3
import json
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

def main(db_path):
    """Run schema cleanup"""
    print("=" * 70)
    print("🧹 CLEANING MARKETDATA SCHEMA")
    print("=" * 70)
    
    # 1. BACKUP
    print("\n1️⃣  CREATING BACKUP...")
    backup_path = backup_database(db_path)
    if not backup_path:
        print("❌ Migration aborted")
        return 1
    
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        print("\n2️⃣  MIGRATING MARKETDATA...")
        
        # Get all data from current MarketData
        cursor.execute("SELECT * FROM MarketData")
        rows = cursor.fetchall()
        print(f"   Found {len(rows)} records in MarketData")
        
        # Create new clean table
        print("   Creating clean schema...")
        cursor.execute("DROP TABLE IF EXISTS MarketData_OLD")
        cursor.execute("ALTER TABLE MarketData RENAME TO MarketData_OLD")
        
        cursor.execute("""
            CREATE TABLE MarketData (
                content_id TEXT PRIMARY KEY,
                link TEXT,
                price TEXT,
                source TEXT DEFAULT 'avtonet',
                category TEXT,
                snippet_data TEXT,
                enriched INTEGER DEFAULT 0,
                enriched_json TEXT,
                created_at DATETIME DEFAULT (strftime('%d.%m.%Y %H:%M:%S', 'now', 'localtime')),
                url_id INTEGER
            )
        """)
        
        # Migrate data with snippet_data consolidation
        print("   Migrating data...")
        migrated = 0
        for row in rows:
            try:
                # Build snippet_data JSON from old columns
                snippet_data = {
                    'ime_avta': row['ime_avta'],
                    'cena': row['cena'],
                    'leto_1_reg': row['leto_1_reg'],
                    'prevozenih': row['prevozenih'],
                    'gorivo': row['gorivo'],
                    'menjalnik': row['menjalnik'],
                    'motor': row['motor'],
                    'raw_snippet': row['raw_snippet']
                }
                
                # Use existing snippet_data if present (preserve Bolha data)
                if row['snippet_data']:
                    try:
                        existing = json.loads(row['snippet_data'])
                        snippet_data.update(existing)
                    except:
                        pass
                
                snippet_data_json = json.dumps(snippet_data)
                
                cursor.execute("""
                    INSERT INTO MarketData (
                        content_id, link, price, source, category,
                        snippet_data, enriched, enriched_json, created_at, url_id
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    row['content_id'],
                    row['link'],
                    row['cena'],  # Use old price column
                    row['source'] or 'avtonet',
                    row['category'],
                    snippet_data_json,
                    row['enriched'],
                    row['enriched_json'],
                    row['created_at'],
                    row['url_id']
                ))
                migrated += 1
            except Exception as e:
                print(f"   ⚠️  Error migrating {row['content_id']}: {e}")
                continue
        
        conn.commit()
        print(f"   ✅ Migrated {migrated}/{len(rows)} records")
        
        # Verify
        cursor.execute("SELECT COUNT(*) FROM MarketData")
        new_count = cursor.fetchone()[0]
        print(f"   Verification: {new_count} records in new table")
        
        # Cleanup old table
        print("   Cleaning up old table...")
        cursor.execute("DROP TABLE MarketData_OLD")
        conn.commit()
        
        conn.close()
        
        print("\n" + "=" * 70)
        print("✅ SCHEMA CLEANUP COMPLETED!")
        print("=" * 70)
        print(f"\n📊 Summary:")
        print(f"   Migrated {migrated} records")
        print(f"   Old Avtonet columns → snippet_data JSON")
        print(f"   Schema is now clean and source-agnostic")
        print(f"\n🎉 Ready to use with Bolha + Avtonet!")
        
        return 0
        
    except Exception as e:
        print(f"\n❌ MIGRATION FAILED: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 clean_marketdata_schema.py <path_to_bot.db>")
        sys.exit(1)
    
    db_path = sys.argv[1]
    exit_code = main(db_path)
    sys.exit(exit_code)
