"""查询 DB 中已绑定的账号，用于发布测试。"""

import asyncio
import os
from pathlib import Path


def _load_env() -> None:
    env = Path(".env")
    if not env.exists():
        return
    for line in env.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


async def main() -> None:
    _load_env()
    from sqlalchemy import select
    from app.db.session import AsyncSessionLocal
    from app.db.models import XhsAccount

    async with AsyncSessionLocal() as db:
        stmt = select(XhsAccount)
        result = await db.execute(stmt)
        accounts = result.scalars().all()

        print(f"DB 中账号数: {len(accounts)}")
        for acc in accounts:
            has_cookies = bool(acc.session_data_encrypted)
            print(f"  id={acc.id}")
            print(f"    nickname: {acc.xhs_nickname}")
            print(f"    has_cookies: {has_cookies}")
            print(f"    cookies_len: {len(acc.session_data_encrypted or '')}")
            print()


if __name__ == "__main__":
    asyncio.run(main())
