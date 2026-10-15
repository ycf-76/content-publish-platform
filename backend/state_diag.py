"""诊断脚本：打印 __INITIAL_STATE__ 中 user.notes 的原始结构，分析可用字段。"""
import asyncio
import json
import logging
import sys
import time
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("state_diag")

BACKEND_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BACKEND_DIR))


async def get_account_info():
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy import text
    engine = create_async_engine(
        "mysql+aiomysql://ycf:ycf94946@127.0.0.1:3306/xhs_agent?charset=utf8mb4"
    )
    async with engine.connect() as conn:
        result = await conn.execute(text(
            "SELECT id, platform_uid, cookies_json FROM platform_accounts "
            "WHERE platform='xiaohongshu' LIMIT 1"
        ))
        row = result.fetchone()
    await engine.dispose()
    if not row:
        return None
    return {"id": row[0], "platform_uid": row[1], "cookies_json": row[2]}


async def main():
    account = await get_account_info()
    if not account:
        print("ERROR: 未找到小红书账号")
        return

    platform_uid = account["platform_uid"]
    cookies = account["cookies_json"] or {}

    from scrapling.spiders.request import Request
    from scrapling.spiders.session import SessionManager
    from scrapling.engines._browsers._stealth import AsyncStealthySession

    storage_path = BACKEND_DIR / "storage_states" / "xiaohongshu.json"
    cookie_list = []
    if storage_path.exists():
        state = json.loads(storage_path.read_text(encoding="utf-8"))
        for c in state.get("cookies", []):
            sc = {"name": c.get("name", ""), "value": c.get("value", "")}
            for key in ("domain", "path", "url", "expires", "httpOnly", "secure", "sameSite"):
                if c.get(key) is not None:
                    sc[key] = c[key]
            if sc.get("expires", 0) < 0:
                del sc["expires"]
            if not sc.get("domain"):
                continue
            sc.pop("url", None)
            if not sc.get("path"):
                sc["path"] = "/"
            cookie_list.append(sc)

    _cookies = cookie_list

    async def _inject_cookies(page):
        try:
            await page.context.add_cookies(_cookies)
        except Exception as e:
            logger.warning(f"add_cookies failed: {e}")

    manager = SessionManager()
    manager.add("stealthy", AsyncStealthySession(
        headless=True,
        network_idle=True,
        google_search=False,
        wait=3000,
        page_setup=_inject_cookies,
        cookies=cookie_list,
    ), default=True)

    url = f"https://www.xiaohongshu.com/user/profile/{platform_uid}"
    logger.info(f"Fetching: {url}")

    async with manager:
        response = await manager.fetch(Request(url=url))

    logger.info(f"Response status: {response.status_code if hasattr(response, 'status_code') else 'unknown'}")

    scripts = response.css("script")
    logger.info(f"Found {len(scripts)} script tags")

    for s in scripts:
        txt = s.text if hasattr(s, "text") else ""
        if not txt or "__INITIAL_STATE__" not in txt:
            continue

        idx = txt.find("__INITIAL_STATE__")
        eq_idx = txt.find("=", idx)
        json_start = eq_idx + 1
        while json_start < len(txt) and txt[json_start] in " \t":
            json_start += 1
        if json_start >= len(txt) or txt[json_start] != "{":
            continue

        import re
        depth = 0
        json_end = json_start
        in_str = False
        escape = False
        for i in range(json_start, len(txt)):
            ch = txt[i]
            if escape:
                escape = False
                continue
            if ch == "\\":
                escape = True
                continue
            if ch == '"' and not in_str:
                in_str = True
                continue
            if ch == '"' and in_str:
                in_str = False
                continue
            if in_str:
                continue
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    json_end = i + 1
                    break

        raw = txt[json_start:json_end]
        raw = re.sub(r'\bundefined\b', 'null', raw)
        raw = re.sub(r'\bNaN\b', 'null', raw)

        from app.platform_spider.xhs_spider import XhsSpider
        raw = XhsSpider._strip_js_constructors(raw)

        try:
            state = json.loads(raw)
        except json.JSONDecodeError as e:
            logger.error(f"JSON parse failed: {e}")
            continue

        user_data = state.get("user", {})
        raw_notes = user_data.get("notes", [])

        print("\n" + "=" * 60)
        print("__INITIAL_STATE__.user 顶级 keys:")
        print("=" * 60)
        for k in sorted(user_data.keys()):
            v = user_data[k]
            if isinstance(v, (list, dict)):
                print(f"  {k}: {type(v).__name__} len={len(v)}")
            else:
                print(f"  {k}: {type(v).__name__} = {str(v)[:80]}")

        print("\n" + "=" * 60)
        print("user.notes 结构分析:")
        print("=" * 60)
        print(f"  type: {type(raw_notes)}")
        print(f"  len: {len(raw_notes)}")
        if raw_notes and isinstance(raw_notes[0], list):
            print(f"  nested array: notes[0] is list of len={len(raw_notes[0])}")
            flat_notes = []
            for sub in raw_notes:
                if isinstance(sub, list):
                    flat_notes.extend(sub)
            print(f"  total after flatten: {len(flat_notes)}")
            raw_notes = flat_notes

        if raw_notes:
            first = raw_notes[0]
            print(f"\n  第1条笔记的所有 keys:")
            if isinstance(first, dict):
                for k in sorted(first.keys()):
                    v = first[k]
                    if k == "noteCard":
                        print(f"    {k}: dict with keys={sorted(v.keys()) if isinstance(v, dict) else type(v)}")
                        if isinstance(v, dict):
                            for nk in sorted(v.keys()):
                                nv = v[nk]
                                if isinstance(nv, (list, dict)):
                                    print(f"      {nk}: {type(nv).__name__} len={len(nv)}")
                                else:
                                    val_str = str(nv)[:100]
                                    print(f"      {nk}: {val_str}")
                    elif isinstance(v, (list, dict)):
                        print(f"    {k}: {type(v).__name__} len={len(v)}")
                    else:
                        print(f"    {k}: {str(v)[:100]}")

            print(f"\n  第1条笔记完整JSON（前2000字符）:")
            print(json.dumps(first, ensure_ascii=False, indent=2)[:2000])

        break


if __name__ == "__main__":
    asyncio.run(main())