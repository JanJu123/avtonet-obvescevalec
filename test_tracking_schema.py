"""
Check Tracking table schema and data
"""

from database import Database

db = Database('bot.db')
conn = db.get_connection()

# Get schema
schema = conn.execute("PRAGMA table_info(Tracking)").fetchall()
print("Tracking table columns:")
for col in schema:
    print(f"  {col[1]} ({col[2]})")

print("\nTracking data for user 8004323652:")
tracking = conn.execute("""
    SELECT * FROM Tracking WHERE telegram_id = 8004323652
""").fetchall()
for row in tracking:
    print(f"  {row}")

conn.close()
