#!/usr/bin/env python3
"""
NORMALIZE CONTENT_ID PREFIXES
=============================
Adds proper prefixes (an_, bo_) to all content_ids for consistent deduplication.

Problem: Mixed prefix formats cause dedup failures
- MarketData: 6071 Avtonet records WITHOUT prefixes
- SentAds: Old Avtonet WITHOUT prefixes, new Bolha WITH bo_ prefixes

Solution: Normalize all content_ids with proper prefixes
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

def main(db_path):
    """Run prefix normalization"""
    print("=" * 70)
    print("🏷️  NORMALIZING CONTENT_ID PREFIXES")
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
        
        # 2. MARKETDATA PREFIX NORMALIZATION
        print("\n2️⃣  NORMALIZING MarketData...")
        
        # Count records without prefixes
        cursor.execute("""
            SELECT COUNT(*) FROM MarketData 
            WHERE content_id NOT LIKE 'an_%' AND content_id NOT LIKE 'bo_%'
        """)
        to_update = cursor.fetchone()[0]
        print(f"   Found {to_update} records without prefixes")
        
        if to_update > 0:
            # Add an_ prefix to all Avtonet records without prefix
            cursor.execute("""
                UPDATE MarketData 
                SET content_id = 'an_' || content_id
                WHERE content_id NOT LIKE 'an_%' AND content_id NOT LIKE 'bo_%'
            """)
            conn.commit()
            print(f"   ✅ Updated {to_update} records with an_ prefix")
        
        # 3. SENTADS PREFIX NORMALIZATION
        print("\n3️⃣  NORMALIZING SentAds...")
        
        # Count records without prefixes
        cursor.execute("""
            SELECT COUNT(*) FROM SentAds 
            WHERE content_id NOT LIKE 'an_%' AND content_id NOT LIKE 'bo_%'
        """)
        to_update = cursor.fetchone()[0]
        print(f"   Found {to_update} records without prefixes")
        
        if to_update > 0:
            # Add an_ prefix to all old Avtonet records without prefix
            cursor.execute("""
                UPDATE SentAds 
                SET content_id = 'an_' || content_id
                WHERE content_id NOT LIKE 'an_%' AND content_id NOT LIKE 'bo_%'
            """)
            conn.commit()
            print(f"   ✅ Updated {to_update} records with an_ prefix")
        
        # 4. VERIFY
        print("\n4️⃣  VERIFYING...")
        cursor.execute("SELECT COUNT(*) FROM MarketData WHERE content_id LIKE 'an_%'")
        an_market = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM MarketData WHERE content_id LIKE 'bo_%'")
        bo_market = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM SentAds WHERE content_id LIKE 'an_%'")
        an_sent = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM SentAds WHERE content_id LIKE 'bo_%'")
        bo_sent = cursor.fetchone()[0]
        
        print(f"   MarketData: an_={an_market}, bo_={bo_market}")
        print(f"   SentAds: an_={an_sent}, bo_={bo_sent}")
        
        conn.close()
        
        print("\n" + "=" * 70)
        print("✅ NORMALIZATION COMPLETED!")
        print("=" * 70)
        print(f"\n📊 Summary:")
        print(f"   All content_ids now have proper prefixes")
        print(f"   Deduplication will work correctly going forward")
        print(f"   Bolha ads can now be saved to MarketData")
        
        return 0
        
    except Exception as e:
        print(f"\n❌ MIGRATION FAILED: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 normalize_prefixes.py <path_to_bot.db>")
        sys.exit(1)
    
    db_path = sys.argv[1]
    exit_code = main(db_path)
    sys.exit(exit_code)
