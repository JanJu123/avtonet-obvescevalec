# VPS Database Migrations

## Quick Start

On VPS:

```bash
cd ~/avtonet-obvescevalec
git pull origin main

# Run migrations IN ORDER
python3 migrations/vps_schema_migration.py bot.db
python3 migrations/full_database_migration.py bot.db

# Restart bot
python3 main.py
```

## What Each Migration Does

### 1. vps_schema_migration.py
- Adapts VPS database schema to match current code
- Verifies ScrapedData has metadata column
- Adds missing columns to MarketData
- Creates automatic backup

### 2. full_database_migration.py
- Adds url_id column to MarketData
- Creates automatic backup

## Rollback

If migration fails:

```bash
# List backups
ls -lah bot.db.backup*

# Restore
mv bot.db bot.db.broken
mv bot.db.backup.20260120_181416 bot.db
```

## Verification

Check if migration worked:

```bash
sqlite3 bot.db "SELECT COUNT(*) FROM ScrapedData;"
sqlite3 bot.db "PRAGMA table_info(MarketData);" | grep url_id
```
