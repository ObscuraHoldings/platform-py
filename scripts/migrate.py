"""Simple migrations runner for TimescaleDB using asyncpg.

Reads SQL files in db/migrations in lexical order and executes them once.
This script is idempotent when migrations are written to be idempotent.
"""
from __future__ import annotations

import asyncio
from pathlib import Path

import asyncpg

from platform_py.config import config

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "db" / "migrations"


async def ensure_migrations_table(conn: asyncpg.Connection) -> None:
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            id SERIAL PRIMARY KEY,
            filename TEXT UNIQUE NOT NULL,
            applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        """
    )


async def applied_migrations(conn: asyncpg.Connection) -> set[str]:
    rows = await conn.fetch("SELECT filename FROM schema_migrations")
    return {r["filename"] for r in rows}


async def apply_migration(conn: asyncpg.Connection, path: Path) -> None:
    sql = path.read_text()
    async with conn.transaction():
        await conn.execute(sql)
        await conn.execute(
            "INSERT INTO schema_migrations(filename) VALUES($1) ON CONFLICT DO NOTHING",
            path.name,
        )


async def main() -> None:
    dsn = config.database.url
    conn = await asyncpg.connect(dsn)
    try:
        await ensure_migrations_table(conn)
        done = await applied_migrations(conn)
        for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
            if path.name in done:
                continue
            print(f"Applying migration {path.name}...")
            await apply_migration(conn, path)
        print("Migrations complete.")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
