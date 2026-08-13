"""分析最新发布诊断：检查按钮是否找到、点击了什么。"""

import json
from pathlib import Path

diag = Path("logs/publish_diag/20260809_171552_publish_no_redirect")
btns = json.loads((diag / "buttons.json").read_text(encoding="utf-8"))

print(f"诊断目录: {diag}")
print(f"buttons.json: {len(btns)} 个按钮\n")

# 找所有 class/text 含发布的
print("=" * 70)
print("含'发布'/'publish'/'submit' 的按钮:")
print("=" * 70)
for i, b in enumerate(btns):
    txt = b.get("text", "")
    cls = b.get("class", "")
    if "发布" in txt or "publish" in cls.lower() or "submit" in cls.lower():
        print(f"  #{i}: tag={b['tag']} text={txt!r} class={cls!r}")
        print(f"      x={b['x']} y={b['y']} w={b['w']} h={b['h']} disabled={b['disabled']}")

# 列出所有底部按钮（y > 600）
print(f"\n{'=' * 70}")
print("底部按钮 (y > 600):")
print("=" * 70)
bottom = [b for b in btns if b.get("y", 0) > 600]
for b in bottom:
    print(f"  tag={b['tag']} text={b.get('text', '')!r} class={b.get('class', '')!r}")
    print(f"    x={b['x']} y={b['y']} w={b['w']} h={b['h']}")

# 所有按钮简表
print(f"\n{'=' * 70}")
print(f"全部 {len(btns)} 个按钮简表:")
print("=" * 70)
for i, b in enumerate(btns):
    print(f"  #{i:02d} {b['tag']:8s} text={b.get('text', '')[:30]!r:32s} class={b.get('class', '')[:60]!r}  y={b.get('y')}")
