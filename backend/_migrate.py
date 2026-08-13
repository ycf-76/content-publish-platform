import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text
from dotenv import load_dotenv
import os

load_dotenv()
url = os.getenv("DATABASE_URL")
engine = create_async_engine(url)

async def run():
    async with engine.begin() as conn:
        await conn.execute(text(
            "ALTER TABLE topic_pool_items "
            "ADD COLUMN tags JSON DEFAULT NULL, "
            "ADD COLUMN ai_summary TEXT DEFAULT NULL, "
            "ADD COLUMN view_count INT NOT NULL DEFAULT 0, "
            "ADD COLUMN ai_summary_generated_at DATETIME DEFAULT NULL"
        ))
    print("Migration done!")

asyncio.run(run())