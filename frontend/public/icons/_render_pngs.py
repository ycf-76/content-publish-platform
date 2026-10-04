import os
from playwright.sync_api import sync_playwright

icons_dir = r"D:\My_Project\多智能体小红书发布平台\frontend\public\icons"

svgs = ["xiaohongshu-app.svg", "douyin-app.svg", "bilibili-app.svg"]

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()

    for svg_name in svgs:
        svg_path = os.path.join(icons_dir, svg_name)
        png_name = svg_name.replace(".svg", ".png")
        png_path = os.path.join(icons_dir, png_name)

        with open(svg_path, "r", encoding="utf-8") as f:
            svg_content = f.read()

        html = f"""<html><body style="margin:0;padding:0;background:transparent;display:flex;justify-content:center;align-items:center;width:512px;height:512px">
            <div style="width:512px;height:512px">{svg_content}</div>
        </body></html>"""

        page.set_content(html)
        page.wait_for_timeout(300)

        div_el = page.query_selector("div")
        div_el.screenshot(path=png_path)
        print(f"{png_name}: {os.path.getsize(png_path)} bytes")

    browser.close()