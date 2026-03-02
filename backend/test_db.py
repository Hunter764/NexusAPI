import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
import os
from dotenv import load_dotenv

load_dotenv()

url = os.getenv("DATABASE_URL")
if url and url.startswith("postgres://"):
    url = url.replace("postgres://", "postgresql+asyncpg://", 1)
elif url and url.startswith("postgresql://"):
    url = url.replace("postgresql://", "postgresql+asyncpg://", 1)

async def test():
    print(f"Testing connection to: {url}")
    try:
        engine = create_async_engine(url)
        async with engine.begin() as conn:
            await conn.run_sync(lambda sync_conn: print("Connected successfully!"))
    except Exception as e:
        print(f"Connection failed: {type(e).__name__} - {e}")

asyncio.run(test())
