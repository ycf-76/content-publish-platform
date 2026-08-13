"""分析点击后的截图：看是否有弹窗、加载状态、错误提示。"""

from pathlib import Path
from PIL import Image

diag = Path("logs/publish_diag/20260809_172253_publish_no_redirect")
img = Image.open(diag / "page.png")
print(f"截图尺寸: {img.size}")

# 裁剪几个关键区域
img_rgb = img.convert("RGB")
w, h = img_rgb.size

# 1. 顶部区域（可能有 toast 提示）
top = img_rgb.crop((0, 0, w, 100))
top.save(diag / "region_top.png")
print(f"顶部区域已保存")

# 2. 点击位置周围（可能有弹窗）
center = img_rgb.crop((400, 600, 900, 800))
center.save(diag / "region_click_center.png")
print(f"点击中心区域已保存")

# 3. 找所有非灰色像素（弹窗/提示通常是彩色）
print(f"\n找非灰色像素（可能的弹窗/提示）:")
for y in range(0, h, 10):
    for x in range(0, w, 10):
        r, g, b = img_rgb.getpixel((x, y))
        # 跳过灰色（r≈g≈b）和白色
        if abs(r - g) < 20 and abs(g - b) < 20:
            continue
        # 跳过品牌红（发布按钮）
        if r > 200 and g < 100 and b < 100:
            continue
        # 找到彩色像素
        print(f"  ({x},{y}) RGB=({r},{g},{b})")

# 4. 分析点击后页面的 URL 变化
url = (diag / "url.txt").read_text(encoding="utf-8").strip()
print(f"\n点击后 URL: {url}")

# 5. 看 buttons.json 是否有新弹窗元素
import json
btns = json.loads((diag / "buttons.json").read_text(encoding="utf-8"))
print(f"\n点击后 buttons.json: {len(btns)} 个按钮")
# 找弹窗相关
for b in btns:
    txt = b.get("text", "")
    cls = b.get("class", "")
    if any(kw in txt for kw in ["确认", "确定", "取消", "再想想", "继续", "重试"]) or \
       any(kw in cls.lower() for kw in ["dialog", "modal", "toast", "popup", "confirm"]):
        print(f"  弹窗元素: {b}")
