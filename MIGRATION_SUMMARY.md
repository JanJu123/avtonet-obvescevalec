"""
MIGRATION AND UPDATE SUMMARY
=============================

This document summarizes all changes made for the new database architecture.

NEW ARCHITECTURE:
================

1. **AIQueue** (NEW TABLE)
   - Temporary working table for ads pending AI processing
   - Used for future miner integration
   - Fields: id, content_id, link, raw_snippet, basic_info, created_at, attempts, last_error

2. **MarketData** (UPDATED)
   - Final persistent data warehouse
   - Removed: `processed` flag (now everything here is processed)
   - Removed: `processing` flag (no longer needed with AIQueue)
   - Added: `enriched` (0=waiting for miner, 1=enriched with full details)
   - Added: `updated_at` (timestamp)

3. **ScrapedData** (UNCHANGED)
   - Raw snapshot from each scraper run
   - Contains ALL ads fetched from avto.net (unfiltered)

4. **SentAds** (UNCHANGED)  
   - Tracks which ads were sent to which users
   - Prevents re-sending to same user

DATA FLOW:
==========

avto.net URL
    ↓
Scraper fetches all ads
    ↓
ScrapedData (raw snapshot - cleared & repopulated)
    ├─→ [REUSE] ads from MarketData → final_results
    └─→ NEW ads → AIQueue + final_results
    ↓
AI processes final_results
    ↓
MarketData (enriched=0, waiting for miner)
    ↓
check_new_offers() filters:
  - Not in user's SentAds
  - Exists in MarketData
  - Interval elapsed
    ↓
Send to user + add to SentAds
    ↓
(Future) Miner processes MarketData where enriched=0
    ↓
MarketData (enriched=1, fully enriched)

MIGRATION STEPS:
================

1. Run migration script on local bot.db:
   python migrate_db_v2.py --db-path bot.db

2. Run same script on VPS bot.db:
   python migrate_db_v2.py --db-path /path/to/vps/bot.db

Script is safe to run multiple times - it checks if migrations are already applied.

WHAT WAS CHANGED IN CODE:
==========================

1. database.py:
   - Added methods: add_to_ai_queue(), get_ai_queue_items(), remove_from_ai_queue(), increment_ai_queue_attempts()
   - Updated insert_market_data() to set enriched=0 by default

2. scraper.py:
   - NEW ads now added to AIQueue (not directly processed)
   - AI processing simplified - works on final_results only
   - All ads still inserted into ScrapedData (unfiltered)
   - [REUSE] ads added to final_results and ScrapedData

3. data_manager.py:
   - Added check for ads in MarketData: only send if EXISTS in MarketData
   - This ensures only processed ads are sent

DATA COMPATIBILITY:
===================

- Old `processed` and `ingested` columns kept in MarketData for backward compatibility
- New code ignores them, but they won't cause errors
- Existing SentAds data untouched
- Existing MarketData records set to enriched=0 on first migration

TESTING:
========

After migration and deployment:

1. Run scraper on a test URL
2. Check ScrapedData is populated
3. Check AIQueue has entries for new ads
4. Check MarketData gets updated with enriched=0
5. Check ads are sent to users via check_new_offers()

ROLLBACK:
=========

If needed, you can revert:
1. Delete AIQueue table: DROP TABLE AIQueue;
2. Ignore enriched/updated_at columns (they'll just be NULL/unused)

NOTES:
======

- The enriched flag is set to 0 for all ads processed by AI
- A future miner service will set enriched=1 after gathering full details
- Users don't care about enriched status - it's only for admin/miner operations
- The system is now properly separated: Scraper → AI → Miner → Users
"""
