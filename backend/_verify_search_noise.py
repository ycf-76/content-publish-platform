# -*- coding: utf-8 -*-
"""跑 3 个 topic 的搜索，打印结果摘要，验证噪音过滤的必要性。

零侵入：直接调 TrendingSearchSkill，不走工作流，不写库，不消耗 LLM token。
"""
import asyncio
import json
import os
import sys

# 加载环境变量
from dotenv import load_dotenv
load_dotenv()

from app.agents.skills.trending_search import TrendingSearchSkill
from app.agents.skills.sources.manager import init_sources, source_manager


async def _ensure_sources():
    """初始化内容源（小红书/HN/Reddit 等），与 main.py startup 一致"""
    await init_sources()
    plats = source_manager.list_platforms()
    print(f"已注册平台: {plats}")
    if "xiaohongshu" not in plats:
        print("警告: 小红书平台未注册，搜索会返回空")


# 3 个代表性 topic（覆盖知识/科技/生活三类）
TOPICS = [
    "AI对程序员的影响",       # 科技类，可能搜出 AI 工具广告
    "四级高频词1500词",       # 知识类，可能搜出培训广告
    "夏季5种养生之道",        # 生活类，可能搜出营销号
]


async def run_one(topic: str) -> dict:
    """跑单个 topic 的搜索，返回结果摘要"""
    skill = TrendingSearchSkill()
    output = await skill.execute({
        "keyword": topic,
        "limit": 10,
        "min_interactions": 5,
        "time_range": "week",
        "platform": "xiaohongshu",  # 只搜小红书，和真实工作流一致
        "disable_fallback": False,
    })

    results = output.get("results", [])
    filter_stats = output.get("filter_stats", {})

    # 打印每条结果的摘要
    print(f"\n{'='*70}")
    print(f"topic: {topic!r}")
    print(f"平台: {output.get('platform', '?')}  count: {output.get('count', 0)}")
    print(f"filter_stats: searched={filter_stats.get('searched_platforms', [])}, "
          f"dropped_low={filter_stats.get('dropped_low_interaction', 0)}, "
          f"fallback={filter_stats.get('fallback_used', False)}")
    print(f"{'='*70}")

    if not results:
        print("  (空结果)")
        return {"topic": topic, "count": 0, "results": []}

    # 按互动量排序打印
    sorted_results = sorted(
        results,
        key=lambda x: x.get("interactions", x.get("likes", 0)),
        reverse=True
    )
    for i, r in enumerate(sorted_results, 1):
        title = r.get("title", "")[:45]
        likes = r.get("likes", 0)
        comments = r.get("comments", 0)
        shares = r.get("shares", 0)
        interactions = r.get("interactions", likes + comments + shares)
        author = r.get("author", "?")[:15]
        fans = r.get("fans_count", 0)
        url = r.get("url", "")[:50]
        print(f"  [{i:2d}] 互动={interactions:>6} 赞={likes:>5} 评={comments:>4} 粉={fans:>6} | {title!r}")
        print(f"       作者={author!r}  url={url}")

    return {"topic": topic, "count": len(results), "results": sorted_results}


async def main():
    print("=== 搜索噪音验证（3 个 topic，零 LLM 成本） ===")
    await _ensure_sources()
    all_dumps = []
    for topic in TOPICS:
        try:
            dump = await run_one(topic)
            all_dumps.append(dump)
        except Exception as e:
            print(f"\n[ERROR] topic={topic!r}: {e}")
            import traceback
            traceback.print_exc()

    # 保存完整 dump 供后续分析
    out_path = "_search_noise_dump.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(all_dumps, f, ensure_ascii=False, indent=2)
    print(f"\n\n=== 完整数据已保存到 {out_path} ===")
    print(f"共 {len(all_dumps)} 个 topic，{sum(d['count'] for d in all_dumps)} 条结果")


if __name__ == "__main__":
    asyncio.run(main())
