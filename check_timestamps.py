#!/usr/bin/env python3
"""Check what timestamps actually look like in the database"""

import sqlite3
import sys

def check_db(db_path):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    tables_to_check = {
        'MarketData': 'created_at',
        'ScrapedData': 'created_at',
        'SentAds': 'sent_at',
    }
    
    for table, col in tables_to_check.items():
        try:
            cursor.execute(f"SELECT {col}, typeof({col}) FROM {table} LIMIT 5")
            rows = cursor.fetchall()
            
            print(f"\n📋 {table}.{col}:")
            print(f"   Rows: {len(rows)}")
            for val, type_name in rows:
                print(f"   Value: {repr(val)} | Type: {type_name}")
        except Exception as e:
            print(f"\n❌ {table}: {e}")
    
    conn.close()

if __name__ == "__main__":
    db_path = sys.argv[1] if len(sys.argv) > 1 else "test_bot.db"
    check_db(db_path)
