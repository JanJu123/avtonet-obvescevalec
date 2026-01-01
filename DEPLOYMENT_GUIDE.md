"""
DEPLOYMENT GUIDE: New Database Architecture
=============================================

Run this guide EXACTLY in this order on your VPS.

STEP 1: Backup your database
==============================

ssh into your VPS and:

    cd /path/to/bot
    cp bot.db bot.db.backup.$(date +%Y%m%d_%H%M%S)

STEP 2: Run migration script
=============================

Copy the migration script to VPS if not already there, then run:

    python migrate_db_v2.py --db-path bot.db

Expected output:
    ======================================================================
    MIGRATION STEP 1: Create AIQueue table
    ======================================================================
    Creating AIQueue table...
    ✅ AIQueue table created successfully
    
    ======================================================================
    MIGRATION STEP 2: Update MarketData table
    ======================================================================
    Current MarketData columns: [...]
    Adding 'enriched' column to MarketData...
    ✅ 'enriched' column added
    Adding 'updated_at' column to MarketData...
    ✅ 'updated_at' column added
    
    ======================================================================
    MIGRATION STEP 3: Migrate existing data
    ======================================================================
    ✅ Updated 909 records - set enriched=0 (default state)
    
    ======================================================================
    MIGRATION COMPLETED SUCCESSFULLY!
    ======================================================================

If it fails, restore backup:
    cp bot.db.backup.* bot.db

STEP 3: Deploy new code
========================

Pull the latest code from git:

    git pull origin main

Verify files updated:
    - scraper.py (uses AIQueue for new ads)
    - database.py (new AIQueue methods)
    - data_manager.py (checks MarketData exists)

STEP 4: Restart bot
====================

Using pm2:
    pm2 stop avtonet-bot
    pm2 start main.py --name avtonet-bot
    pm2 logs avtonet-bot

Or using systemd:
    systemctl restart avtonet-bot
    journalctl -f -u avtonet-bot

STEP 5: Verify operation
=========================

Watch logs for about 15 minutes to see:

1. Scraper runs and fetches ads
2. AIQueue gets new ads:
   [TIMESTAMP] Oglas XXXXX dodan v AIQueue.

3. AI processes them:
   [TIMESTAMP] AI obdeluje X oglasov za ...

4. MarketData gets updated with enriched=0

5. Users receive ads:
   [TIMESTAMP] Pošiljam oglase...

STEP 6: Monitor for 24 hours
=============================

Check:
- Are users receiving ads normally?
- Are there any database errors?
- Is performance similar to before?

Monitor with:
    pm2 logs avtonet-bot | grep ERROR
    pm2 logs avtonet-bot | grep "Pošiljam oglase"

ROLLBACK (if needed)
====================

If something goes wrong:

1. Restore backup:
   cp bot.db.backup.* bot.db

2. Revert code:
   git checkout HEAD -- scraper.py database.py data_manager.py

3. Restart bot:
   pm2 restart avtonet-bot

WHAT TO EXPECT
==============

✅ Same ad delivery to users
✅ Same performance
✅ New AIQueue table (empty if no new ads being processed)
✅ All existing MarketData records get enriched=0
✅ Future miner can use enriched flag for additional processing

QUESTIONS?
==========

If you have issues during deployment:
- Check migration script output for errors
- Check bot.db size (should be slightly larger due to new columns)
- Check pm2 logs for any database errors
- Restore backup and try again if unsure

Contact support with:
- Error message from migration script
- Last 50 lines of pm2 logs
- Output of: sqlite3 bot.db "PRAGMA table_info(MarketData);"
"""
