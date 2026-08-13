"""用 OCR + 图像分析识别截图中的发布按钮。

用 PIL 分析 page.png：
1. 整体尺寸
2. 颜色直方图
3. 切割区域分析（找底部红色/品牌色按钮）
"""

from pathlib import Path
from PIL import Image

diag = Path("logs/publish_diag/20260809_171552_publish_no_redirect")
img = Image.open(diag / "page.png")
print(f"截图尺寸: {img.size}")
print(f"模式: {img.mode}")

# 转 RGB
img_rgb = img.convert("RGB")
w, h = img_rgb.size

# 分析底部 1/4 区域的颜色分布
# 小红书发布按钮通常是红色 (#ff2442) 或品牌色
bottom = img_rgb.crop((0, int(h * 0.75), w, h))
bottom_w, bottom_h = bottom.size
print(f"\n底部 1/4 区域: {bottom.size}")

# 找红色像素（小红书品牌红 #ff2442 附近）
red_pixels = []
brand_red_pixels = []
for y in range(0, bottom_h, 2):
    for x in range(0, bottom_w, 2):
        r, g, b = bottom.getpixel((x, y))
        # 红色按钮：r > 200, g < 100, b < 100
        if r > 200 and g < 100 and b < 100:
            red_pixels.append((x, y, (r, g, b)))
        # 小红书品牌红 #ff2442: r=255, g=36, b=66
        if r > 230 and g < 80 and 50 < b < 100:
            brand_red_pixels.append((x, y, (r, g, b)))

print(f"底部红色像素数: {len(red_pixels)}")
print(f"小红书品牌红像素数: {len(brand_red_pixels)}")

if brand_red_pixels:
    # 找品牌红像素的 bounding box
    xs = [p[0] for p in brand_red_pixels]
    ys = [p[1] for p in brand_red_pixels]
    print(f"  品牌红区域: x={min(xs)}-{max(xs)}, y={min(ys)}-{max(ys)}")
    print(f"  品牌红尺寸: {max(xs)-min(xs)+1} x {max(ys)-min(ys)+1}")
    print(f"  在原图位置: x={min(xs)}, y={min(ys) + int(h * 0.75)}")
    # 保存裁剪
    crop = img_rgb.crop((min(xs) - 10, min(ys) + int(h * 0.75) - 10,
                         max(xs) + 10, max(ys) + int(h * 0.75) + 10))
    crop.save(diag / "brand_red_area.png")
    print(f"  已保存品牌红区域到 brand_red_area.png")

# 分析整个底部行的颜色，找按钮
print(f"\n分析底部 50px 高度的横向条带:")
for y_offset in [10, 30, 50, 70, 90, 110, 130, 150]:
    y = bottom_h - y_offset
    if y < 0:
        continue
    # 统计这一行的颜色
    colors = {}
    for x in range(0, bottom_w, 5):
        r, g, b = bottom.getpixel((x, y))
        # 量化到 32
        qr, qg, qb = r // 32 * 32, g // 32 * 32, b // 32 * 32
        key = (qr, qg, qb)
        colors[key] = colors.get(key, 0) + 1
    top_colors = sorted(colors.items(), key=lambda x: -x[1])[:3]
    print(f"  y_offset={y_offset:3d} (y={y}): {top_colors}")
