"""Apply any *.sql files in supabase/migrations/ in lexicographic order.

Idempotency is the caller's responsibility (use IF NOT EXISTS / OR REPLACE).
"""
import os
import asyncio
from pathlib import Path
from sqlalchemy import text

from app.database import engine

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "db" / "migrations"


async def main() -> None:
    if not MIGRATIONS_DIR.exists():
        print(f"no migrations dir at {MIGRATIONS_DIR}")
        return
    files = sorted(p for p in MIGRATIONS_DIR.glob("*.sql"))
    if not files:
        print("no .sql files")
        return
    async with engine.begin() as conn:
        for f in files:
            sql = f.read_text()
            print(f"  → {f.name}")
            await conn.exec_driver_sql(sql)
    print(f"applied {len(files)} files.")


if __name__ == "__main__":
    asyncio.run(main())
