"""检查点击后的诊断：看是否有弹窗、是否真的点到了按钮内部。"""

import json
from pathlib import Path

diag = Path("logs/publish_diag/20260809_172117_publish_no_redirect")
btns = json.loads((diag / "buttons.json").read_text(encoding="utf-8"))

print(f"诊断目录: {diag}")
print(f"buttons.json: {len(btns)} 个按钮\n")

# 找 xhs-publish-btn
print("=" * 70)
print("XHS-PUBLISH-BTN 元素:")
print("=" * 70)
for i, b in enumerate(btns):
    if "XHS" in b.get("tag", "").upper():
        print(f"  #{i}: {b}")

# 找所有可能的确认/弹窗按钮
print(f"\n{'=' * 70}")
print("含'确认'/'确定'/'弹窗'/'dialog'/'modal'的元素:")
print("=" * 70)
for i, b in enumerate(btns):
    txt = b.get("text", "")
    cls = b.get("class", "")
    if any(kw in txt for kw in ["确认", "确定", "再想想", "取消"]) or \
       any(kw in cls.lower() for kw in ["dialog", "modal", "confirm", "popup"]):
        print(f"  #{i}: {b}")

# 看看 xhs-publish-btn 的内部结构（通过 innerHTML 长度判断）
print(f"\n{'=' * 70}")
print("XHS-PUBLISH-BTN 位置附近的元素:")
print("=" * 70)
for i, b in enumerate(btns):
    y = b.get("y", 0)
    if 600 < y < 800:
        print(f"  #{i}: tag={b['tag']} text={b.get('text', '')[:30]!r} class={b.get('class', '')[:60]!r} y={y}")
