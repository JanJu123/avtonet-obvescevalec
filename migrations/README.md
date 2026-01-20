# 🚀 VPS Database Migration Guide

## Available Migrations

### 1. Full Database Migration (`full_database_migration.py`)
Updates production database with schema updates and timestamp conversion.

**What it does:**
- Adds missing `url_id` column to MarketData table
- Converts timestamps from `DD.MM.YYYY HH:MM:SS` to `YYYY-MM-DD HH:MM:SS` format
- Creates automatic backup before changes

### 2. JSON Schema Migration (`migrate_to_json_schema.py`) ⭐ **NEW**
Converts ScrapedData from fixed columns to flexible JSON metadata.

**What it does:**
- Migrates `leto_1_reg`, `prevozenih`, `gorivo`, `menjalnik`, `motor`, `lokacija`, `published_date` to JSON metadata
- Keeps only essential queryable fields in main columns
- Allows adding new fields without schema changes
- Makes database future-proof and modular

**Benefits:**
- No more database schema changes when adding new fields (Bolha, Nepremičnine, etc.)
- Cleaner, more scalable design
- Same data, better organization

## ⚠️ IMPORTANT: Migration Order

**ALWAYS run migrations in this order:**

1. First: `python migrations/full_database_migration.py` (fix old schema)
2. Then: `python migrations/migrate_to_json_schema.py` (upgrade to JSON)
3. Finally: Restart bot with `python main.py`

## Steps to Follow

### 1. Copy Migration Script to VPS

```bash
# On your local machine, copy the migrations folder to VPS
scp -r migrations/ user@your-vps-ip:/home/user/AvotNet_Scraper_Telegram/
```

### 2. SSH into VPS

```bash
ssh user@your-vps-ip
cd /path/to/AvotNet_Scraper_Telegram
```

### 3. Stop the Running Bot

```bash
# Kill the bot process if running
pkill -f "python main.py"
# Or use your systemd service if you have one
sudo systemctl stop avtonet-bot
```

### 4. Run the Migration

```bash
# For production database:
python migrations/full_database_migration.py bot.db

# OR if you have test database:
python migrations/full_database_migration.py test_bot.db
```

### 5. Verify Migration Success

You should see output like:
```
============================================================
🚀 FULL DATABASE MIGRATION STARTING
============================================================

1️⃣  CREATING BACKUP...
✅ Backup created: bot.db.backup

2️⃣  MIGRATING SCHEMA...
📋 Adding url_id column to MarketData...
   ✅ url_id column added

3️⃣  MIGRATING TIMESTAMPS...
   ✅ Converted timestamps...

============================================================
✅ MIGRATION COMPLETED SUCCESSFULLY!
============================================================
```

### 6. Restart Bot

```bash
# Start the bot again
python main.py

# Or restart systemd service:
sudo systemctl start avtonet-bot
```

## If Something Goes Wrong

If the migration fails, your **backup file** is at:
```
bot.db.backup
```

To restore:
```bash
mv bot.db.backup bot.db
```

## What Gets Fixed

### Before
- Timestamps like: `29.01.2026 14:30:45` (can't sort correctly)
- MarketData table missing `url_id` column (linking issue)
- SQLite browser shows "0" for dates

### After
- Timestamps like: `2026-01-29 14:30:45` (sorts chronologically)
- MarketData properly linked to URLs
- Sorting by date works in any SQL browser

## Questions?

If you encounter issues:
1. Check the backup exists
2. Run the script again (it's safe - it checks for existing columns)
3. Check the console output for specific error messages
