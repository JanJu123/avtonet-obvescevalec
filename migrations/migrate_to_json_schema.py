#!/usr/bin/env python3
"""
Migrate ScrapedData from fixed columns to flexible JSON metadata schema.
Converts old columns (leto_1_reg, prevozenih, gorivo, etc.) to JSON metadata.

This allows adding new fields without changing database schema.

Usage:
    python migrate_to_json_schema.py
    
    This will migrate both bot.db and test_bot.db if they exist.
"""
import sqlite3
import json
import os
from datetime import datetime

def migrate_database(db_path):
    """Migrate a single database to JSON schema."""
    if not os.path.exists(db_path):
        print(f"❌ Database not found: {db_path}")
        return False
    
    print(f"\n{'='*70}")
    print(f"Migrating: {db_path}")
    print(f"{'='*70}")
    
    try:
        conn = sqlite3.connect(db_path)
        c = conn.cursor()
        
        # Check if migration already done (new schema has metadata column)
        c.execute("PRAGMA table_info(ScrapedData)")
        columns = [row[1] for row in c.fetchall()]
        
        if 'metadata' in columns:
            print("✅ Already migrated (metadata column exists)")
            conn.close()
            return True
        
        print(f"📊 Current columns: {columns}")
        
        # Count existing data
        c.execute("SELECT COUNT(*) FROM ScrapedData")
        count = c.fetchone()[0]
        print(f"📈 Rows to migrate: {count}")
        
        if count > 0:
            # 1. Backup old table
            print("\n1️⃣ Creating backup...")
            c.execute("ALTER TABLE ScrapedData RENAME TO ScrapedData_OLD")
            print("   ✅ Backed up to ScrapedData_OLD")
            
            # 2. Create new table with JSON schema
            print("\n2️⃣ Creating new table with JSON metadata...")
            c.execute("""
                CREATE TABLE IF NOT EXISTS ScrapedData (
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
            print("   ✅ New table created")
            
            # 3. Migrate data
            print("\n3️⃣ Migrating data...")
            c.execute("SELECT * FROM ScrapedData_OLD")
            rows = c.fetchall()
            
            # Get column names from old table
            c.execute("PRAGMA table_info(ScrapedData_OLD)")
            col_info = c.fetchall()
            col_names = [col[1] for col in col_info]
            
            print(f"   Old columns: {col_names}")
            
            migrated = 0
            for row in rows:
                row_dict = dict(zip(col_names, row))
                
                # Extract core fields
                id_val = row_dict.get('id')
                url_id = row_dict.get('url_id')
                content_id = row_dict.get('content_id')
                ime_avta = row_dict.get('ime_avta')
                cena = row_dict.get('cena')
                link = row_dict.get('link')
                slika_url = row_dict.get('slika_url')
                created_at = row_dict.get('created_at')
                
                # Put everything else in metadata
                metadata = {}
                skip_keys = {'id', 'url_id', 'content_id', 'ime_avta', 'cena', 'link', 'slika_url', 'created_at'}
                for key, val in row_dict.items():
                    if key not in skip_keys and val is not None:
                        metadata[key] = val
                
                metadata_json = json.dumps(metadata, ensure_ascii=False)
                
                c.execute("""
                    INSERT INTO ScrapedData 
                    (id, url_id, content_id, ime_avta, cena, link, slika_url, metadata, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (id_val, url_id, content_id, ime_avta, cena, link, slika_url, metadata_json, created_at))
                
                migrated += 1
            
            conn.commit()
            print(f"   ✅ Migrated {migrated} rows")
            
            # 4. Verify
            print("\n4️⃣ Verifying migration...")
            c.execute("SELECT COUNT(*) FROM ScrapedData")
            new_count = c.fetchone()[0]
            
            if new_count == count:
                print(f"   ✅ Verification passed: {new_count} rows in new table")
                
                # 5. Drop old table
                print("\n5️⃣ Cleaning up...")
                c.execute("DROP TABLE ScrapedData_OLD")
                conn.commit()
                print("   ✅ Old table deleted")
            else:
                print(f"   ❌ Verification FAILED: Expected {count}, got {new_count}")
                conn.close()
                return False
        else:
            # No data, just recreate table
            print("\n📦 No data to migrate, creating new table...")
            c.execute("DROP TABLE ScrapedData")
            c.execute("""
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
            print("✅ New table created")
        
        conn.close()
        print(f"\n✅ Migration complete: {db_path}")
        return True
        
    except Exception as e:
        print(f"\n❌ Migration FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print(f"\n🚀 ScrapedData JSON Schema Migration")
    print(f"Timestamp: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}\n")
    
    results = {}
    
    # Migrate test_bot.db (development)
    if os.path.exists('test_bot.db'):
        results['test_bot.db'] = migrate_database('test_bot.db')
    
    # Migrate bot.db (production)
    if os.path.exists('bot.db'):
        results['bot.db'] = migrate_database('bot.db')
    
    # Summary
    print(f"\n{'='*70}")
    print("MIGRATION SUMMARY")
    print(f"{'='*70}")
    if results:
        for db, success in results.items():
            status = "✅ SUCCESS" if success else "❌ FAILED"
            print(f"{db}: {status}")
        
        if all(results.values()):
            print(f"\n🎉 All migrations completed successfully!")
        else:
            print(f"\n⚠️ Some migrations failed!")
    else:
        print("⚠️ No databases found to migrate!")
