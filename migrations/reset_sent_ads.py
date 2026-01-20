#!/usr/bin/env python3
"""
Reset SentAds table for a fresh start.

Problem: On VPS startup, ALL ads were marked as sent without actually being sent.
This prevents users from ever seeing new ads.

Solution: Delete all SentAds records so they get re-evaluated.
Users will then receive ads they haven't seen yet.
"""

import sqlite3
import sys

def reset_sent_ads(db_path="bot.db", telegram_id=None):
    """Clear SentAds records to reset ad delivery."""
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    
    print("=" * 80)
    print("RESET: SentAds Table")
    print("=" * 80)
    
    if telegram_id:
        # Reset for specific user
        c.execute("SELECT COUNT(*) FROM SentAds WHERE telegram_id = ?", (telegram_id,))
        count = c.fetchone()[0]
        c.execute("DELETE FROM SentAds WHERE telegram_id = ?", (telegram_id,))
        print(f"\nDeleted {count} SentAds records for user {telegram_id}")
    else:
        # Reset for ALL users
        c.execute("SELECT COUNT(*) FROM SentAds")
        count = c.fetchone()[0]
        c.execute("DELETE FROM SentAds")
        print(f"\nDeleted ALL {count} SentAds records")
        print("⚠️  WARNING: All ads will be re-sent to all users on next cycle!")
    
    conn.commit()
    conn.close()
    
    print(f"{'=' * 80}\n")
    return count

if __name__ == "__main__":
    db_path = sys.argv[1] if len(sys.argv) > 1 else "bot.db"
    telegram_id = int(sys.argv[2]) if len(sys.argv) > 2 else None
    reset_sent_ads(db_path, telegram_id)
