"""Run MarketData enrichment migration safely (idempotent)."""
import sqlite3
import os

DB_PATH = os.getenv("DB_PATH", "bot.db")

SQL = [
    "ALTER TABLE MarketData ADD COLUMN enriched INTEGER DEFAULT 0;",
    "ALTER TABLE MarketData ADD COLUMN enriched_json TEXT;",
]


def column_exists(conn, table, column):
    cur = conn.execute(f"PRAGMA table_info({table})")
    cols = [row[1] for row in cur.fetchall()]
    return column in cols


def main():
    conn = sqlite3.connect(DB_PATH)
    applied = 0
    try:
        for stmt in SQL:
            # crude parse to get column name (last word before optional type)
            col = stmt.split("ADD COLUMN", 1)[1].strip().split()[0]
            if column_exists(conn, "MarketData", col):
                continue
            try:
                conn.execute(stmt)
                applied += 1
            except sqlite3.OperationalError as e:
                # Ignore if already exists; otherwise raise
                if "duplicate column name" in str(e).lower():
                    continue
                raise
        conn.commit()
        print(f"Migration done. Statements applied: {applied}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
