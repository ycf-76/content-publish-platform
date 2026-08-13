"""LangSmith 项目 run 分析。

用 list_runs 直接拉取项目下所有 runs，做汇总：
1. Run 类型分布
2. Token 消耗检测（验证 mock 是否生效）
3. 节点执行耗时
4. 评估器得分（如果存在）
5. 最近 trace 列表

运行：
    .venv\\Scripts\\python.exe tests/analyze_langsmith.py
"""

from __future__ import annotations

import os
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


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


def _fmt_time(dt: Any) -> str:
    if not dt:
        return "N/A"
    try:
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    except Exception:
        return str(dt)


def main() -> None:
    _load_env()

    if not os.environ.get("LANGCHAIN_API_KEY"):
        print("[ERROR] LANGCHAIN_API_KEY 未配置")
        return

    from langsmith import Client

    client = Client()
    project = os.environ.get("LANGCHAIN_PROJECT", "default")
    print(f"LangSmith 项目: {project}")
    print(f"API Key: {os.environ.get('LANGCHAIN_API_KEY', '')[:20]}...")

    # 拉取项目下最近 100 条 run（LangSmith 单次上限 100）
    print(f"\n拉取最近 runs...")
    try:
        runs = list(client.list_runs(project_name=project, limit=100))
    except Exception as e:
        print(f"[ERROR] list_runs 失败: {e}")
        return

    print(f"共拉取 {len(runs)} 条 run")

    if not runs:
        print("项目无 run 数据")
        return

    # === 1. Run 类型分布 ===
    print(f"\n{'=' * 70}")
    print("1. Run 类型分布")
    print('=' * 70)
    by_type: dict[str, int] = defaultdict(int)
    for r in runs:
        by_type[r.run_type or "unknown"] += 1
    for t, c in sorted(by_type.items(), key=lambda x: -x[1]):
        print(f"  {t:<20s}  {c}")

    # === 2. Token 消耗检测 ===
    print(f"\n{'=' * 70}")
    print("2. Token 消耗检测（验证 mock 是否生效）")
    print('=' * 70)
    llm_runs = [r for r in runs if r.run_type == "llm"]
    total_prompt = sum(getattr(r, "prompt_tokens", 0) or 0 for r in llm_runs)
    total_completion = sum(getattr(r, "completion_tokens", 0) or 0 for r in llm_runs)
    total_total = sum(getattr(r, "total_tokens", 0) or 0 for r in llm_runs)
    print(f"  LLM run 数:          {len(llm_runs)}")
    print(f"  prompt_tokens 总和:  {total_prompt}")
    print(f"  completion_tokens:   {total_completion}")
    print(f"  total_tokens 总和:   {total_total}")
    if total_total == 0:
        print(f"  >>> ✅ 零 token 消耗（_MockLLM 生效，未调用真实 DeepSeek）")
    else:
        print(f"  >>> ⚠️ 检测到 token 消耗！mock 可能未生效")

    # === 3. 按 name 聚合（节点执行情况）===
    print(f"\n{'=' * 70}")
    print("3. 按 name 聚合的 run 统计")
    print('=' * 70)
    by_name: dict[str, list[Any]] = defaultdict(list)
    for r in runs:
        by_name[r.name or "(unnamed)"].append(r)

    print(f"  {'name':<40s}  {'count':>5s}  {'avg_ms':>8s}  {'total_tk':>9s}")
    print(f"  {'-' * 40}  {'-' * 5}  {'-' * 8}  {'-' * 9}")
    for name, rs in sorted(by_name.items(), key=lambda x: -len(x[1]))[:20]:
        durations = []
        for r in rs:
            if r.start_time and r.end_time:
                ms = (r.end_time - r.start_time).total_seconds() * 1000
                durations.append(ms)
        avg_ms = sum(durations) / len(durations) if durations else 0
        total_tk = sum(getattr(r, "total_tokens", 0) or 0 for r in rs)
        print(f"  {name[:40]:<40s}  {len(rs):>5d}  {avg_ms:>7.1f}ms  {total_tk:>9d}")

    # === 4. 评估器得分（如果有 evaluator run）===
    eval_runs = [r for r in runs if r.run_type == "evaluator"]
    if eval_runs:
        print(f"\n{'=' * 70}")
        print(f"4. 评估器得分（共 {len(eval_runs)} 条）")
        print('=' * 70)
        scores_by_key: dict[str, list[float]] = defaultdict(list)
        comments_by_key: dict[str, list[str]] = defaultdict(list)
        for r in eval_runs:
            out = r.outputs or {}
            final = out.get("final_result") or out
            score = final.get("score")
            key = final.get("key") or r.name or "unknown"
            comment = final.get("comment") or ""
            if score is not None:
                scores_by_key[key].append(float(score))
                if comment:
                    comments_by_key[key].append(str(comment))

        print(f"  {'评估器 key':<28s}  {'样本数':>6s}  {'平均分':>8s}  {'满分率':>8s}")
        print(f"  {'-' * 28}  {'-' * 6}  {'-' * 8}  {'-' * 8}")
        for key, scores in sorted(scores_by_key.items()):
            avg = sum(scores) / len(scores)
            full = sum(1 for s in scores if s >= 1.0)
            rate = full / len(scores) if scores else 0
            print(f"  {key:<28s}  {len(scores):>6d}  {avg:>8.2f}  {rate:>7.1%}")

        # 输出部分 comment 样本
        print(f"\n  [评估器 comment 样本]")
        for key, comments in list(comments_by_key.items())[:5]:
            print(f"  {key}:")
            for c in comments[:3]:
                print(f"    - {c}")
    else:
        print(f"\n[INFO] 未发现 evaluator 类型 run")

    # === 5. 最近 trace 列表（顶层 run）===
    print(f"\n{'=' * 70}")
    print("5. 最近 trace（顶层 run，按时间倒序）")
    print('=' * 70)
    # 顶层 run：parent_run_id 为 None
    top_runs = [r for r in runs if not r.parent_run_id]
    top_runs.sort(key=lambda r: r.start_time or datetime.min, reverse=True)

    print(f"  {'时间':<22s}  {'name':<35s}  {'type':<10s}  {'耗时':>8s}")
    print(f"  {'-' * 22}  {'-' * 35}  {'-' * 10}  {'-' * 8}")
    for r in top_runs[:15]:
        start = _fmt_time(r.start_time)[5:22] if r.start_time else "N/A"
        duration = ""
        if r.start_time and r.end_time:
            ms = (r.end_time - r.start_time).total_seconds() * 1000
            if ms > 1000:
                duration = f"{ms / 1000:.2f}s"
            else:
                duration = f"{ms:.0f}ms"
        name = (r.name or "(unnamed)")[:35]
        print(f"  {start:<22s}  {name:<35s}  {(r.run_type or '?'):<10s}  {duration:>8s}")


if __name__ == "__main__":
    main()
