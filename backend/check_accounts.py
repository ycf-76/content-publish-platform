import asyncio
from app.db.session import AsyncSessionLocal
from sqlalchemy import text

async def check():
    async with AsyncSessionLocal() as db:
        result = await db.execute(text(
            "SELECT id, platform, platform_uid, sync_status, sync_error FROM platform_accounts"
        ))
        rows = result.fetchall()
        if not rows:
            print("No platform_accounts found!")
        for r in rows:
            print(r)

asyncio.run(check())