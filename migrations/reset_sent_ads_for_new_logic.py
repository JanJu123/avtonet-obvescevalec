#!/usr/bin/env python3
"""
Reset SentAds tracking to allow new logic to work properly.

The new logic is:
1. Startup (silent): Find ads in MarketData -> mark as sent (no notification)
2. Next cycle: Query MarketData -> check SentAds per user -> send only unsent

This script clears SentAds so the new tracking can start fresh per user.
"""

import sqlite3
import sys

def reset_sent_ads(db_path="bot.db"):
    """Clear SentAds table to reset tracking."""
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    
    print("=" * 80)
    print("RESET: SentAds tracking for new per-user logic")
    print("=" * 80)
    
    # Count before
    c.execute("SELECT COUNT(*) FROM SentAds")
    before = c.fetchone()[0]
    print(f"\nBefore: {before} sent ads tracked")
    
    # Clear
    c.execute("DELETE FROM SentAds")
    conn.commit()
    
    # Count after
    c.execute("SELECT COUNT(*) FROM SentAds")
    after = c.fetchone()[0]
    print(f"After: {after} sent ads tracked")
    
    print(f"\n{' ' * 80}")
    print("WORKFLOW AFTER RESET:")
    print(f"{' ' * 80}")
    print("""
1. Next startup (silent check):
   - Find all ads in MarketData for tracked URLs
   - Mark them as sent in SentAds per user
   - Don't send notifications

2. Next normal cycle:
   - Query MarketData for unsent ads per user
   - SentAds prevents duplicate sends
   - Each user only gets ads they haven't seen

3. When user adds NEW URL:
   - Scraper finds ads
   - Startup mode marks as sent (silent)
   - Next cycle: nothing new yet (marked as sent)
   - Future cycles: new ads from that URL sent normally
    """)
    
    print(f"\n{'=' * 80}")
    print(f"[DONE] SentAds reset - {before} records cleared")
    print(f"{'=' * 80}")

if __name__ == "__main__":
    db_path = sys.argv[1] if len(sys.argv) > 1 else "bot.db"
    reset_sent_ads(db_path)
