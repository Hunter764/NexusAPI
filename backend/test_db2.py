import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
import os
from dotenv import load_dotenv

load_dotenv()

url = os.getenv("DATABASE_URL")
url = url.replace("postgres://", "postgresql+asyncpg://", 1).replace("postgresql://", "postgresql+asyncpg://", 1)
url = url.replace("sslmode=require", "ssl=require")
url = url.replace("&channel_binding=require", "")

async def test():
    print(f"Testing connection to: {url}")
    try:
        engine = create_async_engine(url)
        print("Engine created.")
        async with engine.begin() as conn:
            await conn.run_sync(lambda sync_conn: print("Connected successfully!"))
            # get a simple query
            res = await conn.execute(engine.dialect.statement_compiler(engine.dialect, None).statement("SELECT 1"))
    except Exception as e:
        print(f"Connection failed: {type(e).__name__} - {e}")

asyncio.run(test())
