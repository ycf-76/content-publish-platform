"""批量真实冒烟：跑 N 个不同 topic，统计"终止信号"指标基线。

用真实 deepseek + 真实工具，绕过 HTTP 认证直接驱动 LoopExecutor。
每个 topic 单独挂 logging.Handler 收集日志，统计 5 个指标。
结果写 backend/logs/smoke_batch_<ts>.json。
"""

import asyncio
import json
import logging
import os
import sys
import time
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

logging.basicConfig(
    level=logging.INFO,
    stream=sys.stdout,
    force=True,
    format="%(levelname)s %(name)s %(message)s",
)

from app.engine import factory  # noqa: E402
from app.engine.harness.executor.loop import LoopExecutor  # noqa: E402
from app.engine.harness.runtime import AgentHarness  # noqa: E402
from app.engine.schemas import WorkflowContext  # noqa: E402
from app.tools.trending_search import TrendingSearchSkill  # noqa: E402
from app.tools.dev_tools import GlobSkill, GrepSkill  # noqa: E402

TOPICS = [
    "帮我搜索小红书上 AI 教育的热点趋势",
    "帮我出一期穿搭文案",
    "分析一下小红书上爆款笔记的共同特征",
    "你好",
    "帮我写个小红书标题，主题是夏天防晒",
    "搜索一下露营装备的热门笔记",
    "给我做个小红书封面",
    "总结一下小红书母婴赛道的内容特点",
    "帮我出一期美食探店笔记",
    "最近有什么值得做的小红书选题",
]

MAX_ITER = 20


class _Collector(logging.Handler):
    def __init__(self):
        super().__init__(level=logging.INFO)
        self.msgs: list[str] = []

    def emit(self, record):
        try:
            self.msgs.append(record.getMessage())
        except Exception:
            pass


def _count(msgs, needle):
    return sum(1 for m in msgs if needle in m)


async def run_one(idx: int, topic: str) -> dict:
    col = _Collector()
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(col)
    t0 = time.time()
    try:
        harness = AgentHarness(
            agent_id=f"smoke{idx}",
            role="tester",
            llm=factory.get_deepseek_llm(),
            skills=[TrendingSearchSkill(), GlobSkill(), GrepSkill()],
            memory=factory.AgentMemory(),
            observer=factory._make_observer(f"smoke{idx}"),
            executor=LoopExecutor(max_iterations=MAX_ITER),
        )
        ctx = WorkflowContext(
            workflow_id=f"smoke{idx}",
            node_id=f"smoke{idx}",
            user_id="smoke",
            account_id="smoke",
        )
        out = await harness.run({"topic": topic}, ctx)
        o = out.output or {}
        return {
            "idx": idx,
            "topic": topic,
            "ok": True,
            "iterations": o.get("_iterations"),
            "truncated": bool(o.get("_loop_truncated")),
            "l3": _count(col.msgs, "_parse_step L3 degraded"),
            "l1_l2": _count(col.msgs, "_parse_step L1")
            + _count(col.msgs, "_parse_step L2"),
            "nudge": _count(col.msgs, "zero tool invocation"),
            "arg_fail": _count(col.msgs, "arguments JSON parse failed"),
            "compaction": _count(col.msgs, "compaction"),
            "summary_head": str(o.get("summary"))[:150],
            "seconds": round(time.time() - t0, 1),
        }
    except Exception as e:  # noqa: BLE001
        return {
            "idx": idx,
            "topic": topic,
            "ok": False,
            "error": f"{type(e).__name__}: {str(e)[:200]}",
            "seconds": round(time.time() - t0, 1),
        }
    finally:
        root.removeHandler(col)


async def main() -> None:
    llm = factory.get_deepseek_llm()
    print(f"[BATCH] llm={llm!r}", flush=True)
    if llm is None:
        print("[BATCH] NO_LLM — 无法运行", flush=True)
        return

    results = []
    for i, topic in enumerate(TOPICS, 1):
        print(f"[BATCH] --- {i}/{len(TOPICS)}: {topic}", flush=True)
        r = await run_one(i, topic)
        results.append(r)
        print(f"[BATCH] {i} done: {json.dumps(r, ensure_ascii=False)}", flush=True)

    ok = [r for r in results if r.get("ok")]
    total_iter = sum(r.get("iterations") or 0 for r in ok)
    total_l3 = sum(r.get("l3") or 0 for r in ok)
    summary = {
        "tasks": len(results),
        "ok": len(ok),
        "failed": len(results) - len(ok),
        "total_iterations": total_iter,
        "total_l3": total_l3,
        "l3_rate": round(total_l3 / total_iter, 3) if total_iter else None,
        "truncated_tasks": sum(1 for r in ok if r.get("truncated")),
        "truncate_rate": round(sum(1 for r in ok if r.get("truncated")) / len(ok), 3)
        if ok
        else None,
        "total_nudge": sum(r.get("nudge") or 0 for r in ok),
        "total_arg_fail": sum(r.get("arg_fail") or 0 for r in ok),
        "total_compaction": sum(r.get("compaction") or 0 for r in ok),
        "avg_iterations": round(total_iter / len(ok), 2) if ok else None,
        "total_seconds": round(sum(r.get("seconds") or 0 for r in results), 1),
    }
    print("[BATCH] === SUMMARY ===", flush=True)
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)

    os.makedirs("logs", exist_ok=True)
    ts = datetime.now().strftime("%m%d_%H%M%S")
    path = f"logs/smoke_batch_{ts}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"summary": summary, "results": results}, f, ensure_ascii=False, indent=2)
    print(f"[BATCH] written to {path}", flush=True)


asyncio.run(main())
