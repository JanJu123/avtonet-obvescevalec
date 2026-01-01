"""
Migration Script for Database Schema Update
============================================

This script updates the database to the new architecture:
- Creates AIQueue table for pending ads
- Updates MarketData table with enriched flag
- Removes old ingested/processed flags

Usage:
    python migrate_db_v2.py [--db-path path/to/bot.db]

Default: bot.db in current directory

This script is safe to run multiple times - it checks if migrations are already applied.
"""

import sqlite3
import sys
import argparse
from pathlib import Path

def get_db_connection(db_path):
    """Get database connection"""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn

def check_table_exists(conn, table_name):
    """Check if table exists"""
    cursor = conn.cursor()
    result = cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,)
    ).fetchone()
    return result is not None

def check_column_exists(conn, table_name, column_name):
    """Check if column exists in table"""
    cursor = conn.cursor()
    columns = cursor.execute(f"PRAGMA table_info({table_name})").fetchall()
    return any(col[1] == column_name for col in columns)

def migrate_database(db_path):
    """Run all migrations"""
    print(f"Opening database: {db_path}")
    
    if not Path(db_path).exists():
        print(f"❌ Database file not found: {db_path}")
        return False
    
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    
    try:
        print("\n" + "="*70)
        print("MIGRATION STEP 1: Create AIQueue table")
        print("="*70)
        
        if check_table_exists(conn, "AIQueue"):
            print("✅ AIQueue table already exists, skipping...")
        else:
            print("Creating AIQueue table...")
            cursor.execute("""
                CREATE TABLE AIQueue (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    content_id TEXT NOT NULL UNIQUE,
                    link TEXT NOT NULL,
                    raw_snippet TEXT,
                    basic_info TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    attempts INTEGER DEFAULT 0,
                    last_error TEXT
                )
            """)
            conn.commit()
            print("✅ AIQueue table created successfully")
        
        print("\n" + "="*70)
        print("MIGRATION STEP 2: Update MarketData table")
        print("="*70)
        
        # Check current MarketData structure
        columns = cursor.execute("PRAGMA table_info(MarketData)").fetchall()
        col_names = [col[1] for col in columns]
        
        print(f"Current MarketData columns: {col_names}")
        
        # Add enriched column if it doesn't exist
        if "enriched" not in col_names:
            print("Adding 'enriched' column to MarketData...")
            cursor.execute("""
                ALTER TABLE MarketData ADD COLUMN enriched INTEGER DEFAULT 0
            """)
            conn.commit()
            print("✅ 'enriched' column added")
        else:
            print("✅ 'enriched' column already exists")
        
        # Add updated_at column if it doesn't exist
        if "updated_at" not in col_names:
            print("Adding 'updated_at' column to MarketData...")
            cursor.execute("""
                ALTER TABLE MarketData ADD COLUMN updated_at DATETIME
            """)
            conn.commit()
            print("✅ 'updated_at' column added")
        else:
            print("✅ 'updated_at' column already exists")
        
        # Note: We keep 'ingested' and 'processed' for backward compatibility
        # but they are no longer actively used
        print("ℹ️  Old 'ingested' and 'processed' columns kept for backward compatibility")
        
        print("\n" + "="*70)
        print("MIGRATION STEP 3: Migrate existing data")
        print("="*70)
        
        # Migrate processed flag to enriched flag
        # processed=1 → enriched=0 (AI processed but not enriched yet)
        # processed=0 → enriched=0 (not processed, shouldn't happen in MarketData)
        
        # All existing records in MarketData are considered "enriched=0" 
        # (waiting for miner to add more details)
        result = cursor.execute("""
            UPDATE MarketData SET enriched = 0 WHERE enriched IS NULL
        """)
        conn.commit()
        print(f"✅ Updated {result.rowcount} records - set enriched=0 (default state)")
        
        print("\n" + "="*70)
        print("MIGRATION COMPLETED SUCCESSFULLY!")
        print("="*70)
        
        # Summary
        market_count = cursor.execute("SELECT COUNT(*) FROM MarketData").fetchone()[0]
        queue_count = cursor.execute("SELECT COUNT(*) FROM AIQueue").fetchone()[0]
        
        print(f"\nDatabase Statistics:")
        print(f"  - MarketData records: {market_count}")
        print(f"  - AIQueue records: {queue_count}")
        print(f"\nNew schema:")
        print(f"  - AIQueue: For ads pending AI processing")
        print(f"  - MarketData: For processed ads (enriched: 0=waiting, 1=done)")
        
        return True
        
    except Exception as e:
        print(f"\n❌ Migration failed: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()

def main():
    parser = argparse.ArgumentParser(
        description="Migrate database to new schema (AIQueue + MarketData updates)"
    )
    parser.add_argument(
        "--db-path",
        type=str,
        default="bot.db",
        help="Path to bot.db (default: bot.db)"
    )
    
    args = parser.parse_args()
    
    success = migrate_database(args.db_path)
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()
