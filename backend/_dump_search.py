# -*- coding: utf-8 -*-
"""拉取最近 workflow 的 search 节点输出，分析噪音问题"""
import asyncio
import os
import json
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text
from dotenv import load_dotenv

load_dotenv()
url = os.getenv("DATABASE_URL", "")
# 统一成 mysql+aiomysql
if url.startswith("mysql://"):
    url = url.replace("mysql://", "mysql+aiomysql://", 1)
elif url.startswith("mysql+pymysql://"):
    url = url.replace("mysql+pymysql://", "mysql+aiomysql://", 1)
# 避免重复
if url.count("aiomysql") > 1:
    url = url.replace("mysql+aiomysql+aiomysql://", "mysql+aiomysql://")
print("DB URL:", url[:60])
eng = create_async_engine(url, pool_pre_ping=True)


async def main():
    async with eng.connect() as c:
        # 1. 查最近 5 条 workflow
        r = await c.execute(text(
            "SELECT id, topic, status, created_at FROM workflows ORDER BY created_at DESC LIMIT 5"
        ))
        workflows = r.fetchall()
        print("\n=== 最近 5 条 workflow ===")
        for w in workflows:
            print(f"  id={w[0]}  topic={w[1][:40]!r}  status={w[2]}  created={w[3]}")

        if not workflows:
            print("数据库里没有 workflow 记录")
            return

        # 2. 对每条 workflow，查 search 节点的 output_data
        # workflow_nodes 表里 node_type 列存的是枚举值字符串
        print("\n=== search 节点输出 ===")
        for w in workflows:
            wf_id = w[0]
            r = await c.execute(text(
                "SELECT node_type, status, output_data, input_data, duration_ms, "
                "error_message, started_at, completed_at "
                "FROM workflow_nodes WHERE workflow_id=:wid AND node_type='search'"
            ), {"wid": wf_id})
            rows = r.fetchall()
            if not rows:
                print(f"\n[{wf_id}] topic={w[1]!r} -- 无 search 节点记录")
                continue
            for row in rows:
                print(f"\n[{wf_id}] topic={w[1]!r}")
                print(f"  status={row[1]}  duration_ms={row[4]}  error={row[5]}")
                print(f"  started={row[6]}  completed={row[7]}")
                out = row[2] or {}
                if isinstance(out, str):
                    try: out = json.loads(out)
                    except: pass
                print(f"  output_data keys: {list(out.keys()) if isinstance(out, dict) else type(out)}")
                # 搜索结果核心数据
                results = out.get("results") or out.get("search_results") or []
                print(f"  results 数量: {len(results)}")
                # filter_stats
                fs = out.get("filter_stats") or {}
                if fs:
                    print(f"  filter_stats: {fs}")
                # 打印前 5 条结果的字段
                for i, item in enumerate(results[:5]):
                    if isinstance(item, dict):
                        title = item.get("title", "")[:50]
                        likes = item.get("likes") or item.get("interactions") or item.get("score")
                        plat = item.get("platform", "?")
                        print(f"    [{i+1}] platform={plat}  likes={likes}  title={title!r}")
                # 噪音维度：按平台分布
                if results:
                    plat_count = {}
                    for item in results:
                        p = item.get("platform", "?") if isinstance(item, dict) else "?"
                        plat_count[p] = plat_count.get(p, 0) + 1
                    print(f"  平台分布: {plat_count}")
                # 完整 dump 到文件供后续分析
                with open(f"_dump_search_{wf_id}.json", "w", encoding="utf-8") as f:
                    json.dump({"workflow_id": wf_id, "topic": w[1], "output": out}, f, ensure_ascii=False, indent=2)
                print(f"  完整 dump: _dump_search_{wf_id}.json")

asyncio.run(main())
