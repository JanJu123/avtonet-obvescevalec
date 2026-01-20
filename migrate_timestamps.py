#!/usr/bin/env python3
"""
Migration script to convert timestamps from DD.MM.YYYY HH:MM:SS to YYYY-MM-DD HH:MM:SS
This allows proper sorting by created_at and updated_at in SQLite.
"""

import sqlite3
import sys
from datetime import datetime

def convert_timestamp(old_format):
    """Convert DD.MM.YYYY HH:MM:SS to YYYY-MM-DD HH:MM:SS"""
    if not old_format or old_format == '0':
        return None
    try:
        # Parse DD.MM.YYYY HH:MM:SS
        dt = datetime.strptime(old_format, "%d.%m.%Y %H:%M:%S")
        # Return YYYY-MM-DD HH:MM:SS
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except:
        return None

def migrate_table(conn, table_name, date_columns):
    """Migrate date columns in a table from DD.MM.YYYY to YYYY-MM-DD format"""
    cursor = conn.cursor()
    
    print(f"\n📋 Migrating {table_name}...")
    
    # Get all rows with the date column
    for col in date_columns:
        try:
            # Get all existing values
            cursor.execute(f"SELECT rowid, {col} FROM {table_name}")
            rows = cursor.fetchall()
            
            converted = 0
            for rowid, old_value in rows:
                if old_value:
                    new_value = convert_timestamp(old_value)
                    if new_value:
                        cursor.execute(f"UPDATE {table_name} SET {col} = ? WHERE rowid = ?", (new_value, rowid))
                        converted += 1
            
            conn.commit()
            print(f"   ✅ {col}: Converted {converted} timestamps")
        except Exception as e:
            print(f"   ❌ Error converting {col}: {e}")
            conn.rollback()

def main(db_path):
    """Run migration on specified database"""
    print(f"🚀 Starting timestamp migration for: {db_path}")
    
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        
        # Tables and their date columns
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
            # Check if table exists
            cursor = conn.cursor()
            cursor.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,))
            if cursor.fetchone():
                migrate_table(conn, table, columns)
            else:
                print(f"⏭️  Table {table} does not exist, skipping...")
        
        conn.close()
        print("\n✅ Migration completed successfully!")
        return 0
        
    except Exception as e:
        print(f"\n❌ Migration failed: {e}")
        return 1

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python migrate_timestamps.py <database_path>")
        print("Example: python migrate_timestamps.py bot.db")
        sys.exit(1)
    
    db_path = sys.argv[1]
    sys.exit(main(db_path))
