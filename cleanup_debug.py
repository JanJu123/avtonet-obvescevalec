#!/usr/bin/env python3
"""
Clean up debugging files and prepare for production.
This script removes debug/test files that aren't needed in production.
"""
import os
import shutil

DEBUG_FILES = [
    'app_debug.log',
    'check_tables.py',
    'check_timestamps.py',
    'migrate_timestamps.py',
    'run_migration.py',
    'test_migration.py',
    'verify_migration.py',
    'initialize_pending_urls.py',
    'MIGRATION_REPORT.md',
    'workflow.excalidraw',
    'test_bot.db',
]

print("="*70)
print("PRODUCTION CLEANUP - Removing Debug Files")
print("="*70)

removed_count = 0
for file in DEBUG_FILES:
    if os.path.exists(file):
        try:
            if os.path.isfile(file):
                os.remove(file)
            else:
                shutil.rmtree(file)
            print(f"✓ Removed: {file}")
            removed_count += 1
        except Exception as e:
            print(f"✗ Failed to remove {file}: {e}")
    else:
        print(f"- Skip (not found): {file}")

print(f"\n{'='*70}")
print(f"Cleanup complete: {removed_count} files removed")
print(f"{'='*70}")
print("\nProduction-ready files remaining:")
print(f"  Core: main.py, database.py, data_manager.py")
print(f"  Scrapers: scraper/avtonet/, scraper/bolha/")
print(f"  Config: config.py, .env, requirements.txt")
print(f"  Migrations: migrations/")
print(f"  Integrations: telegram_bot.py, ai_handler.py")
print(f"\nReady for production deployment! 🚀")
