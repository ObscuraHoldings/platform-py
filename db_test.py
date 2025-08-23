import asyncio
import asyncpg

async def test_db_connection():
    conn = await asyncpg.connect(
        host='localhost',
        port=5432,
        database='platform_events',
        user='platform',
        password='platform_secure_pass'
    )
    print("Successfully connected to database")
    await conn.close()

asyncio.run(test_db_connection())
