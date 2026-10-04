import os
import json
import re
from playwright.sync_api import sync_playwright
from PIL import Image
from io import BytesIO

icons_dir = os.path.dirname(os.path.abspath(__file__))


def download_and_save(page, url, out_path, min_size=100):
    """Download an image URL and save as 512x512 PNG."""
    try:
        if url.startswith("//"):
            url = "https:" + url
        elif url.startswith("/"):
            url = "https://www.xiaohongshu.com" + url

        resp = page.request.get(url)
        if resp.ok:
            body = resp.body()
            img = Image.open(BytesIO(body))
            if img.size[0] >= min_size and img.size[1] >= min_size:
                img = img.convert("RGBA")
                img = img.resize((512, 512), Image.LANCZOS)
                img.save(out_path, "PNG")
                print(f"  Saved: {os.path.getsize(out_path)} bytes, source: {img.size}")
                return True
            else:
                print(f"  Too small: {img.size}")
    except Exception as e:
        print(f"  Download error: {e}")
    return False


with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)

    # 1. Xiaohongshu - check manifest.json for app icons
    page = browser.new_page()
    try:
        page.goto("https://www.xiaohongshu.com", wait_until="domcontentloaded", timeout=15000)
        page.wait_for_timeout(2000)

        # Check for manifest link
        manifest_el = page.query_selector('link[rel="manifest"]')
        if manifest_el:
            manifest_href = manifest_el.get_attribute("href") or ""
            print(f"XHS manifest: {manifest_href}")
            if manifest_href.startswith("/"):
                manifest_href = "https://www.xiaohongshu.com" + manifest_href
            resp = page.request.get(manifest_href)
            if resp.ok:
                manifest = resp.json()
                icons = manifest.get("icons", [])
                print(f"  Manifest icons: {json.dumps(icons, indent=2)}")
                # Find the largest icon
                for icon in sorted(icons, key=lambda x: int(x.get("sizes", "0x0").split("x")[0]), reverse=True):
                    src = icon.get("src", "")
                    if src:
                        out = os.path.join(icons_dir, "xiaohongshu-app.png")
                        if download_and_save(page, src, out):
                            break
        else:
            print("XHS: no manifest link found")

        # Also check apple-touch-icon
        apple_el = page.query_selector('link[rel="apple-touch-icon"]')
        if apple_el:
            apple_href = apple_el.get_attribute("href") or ""
            print(f"XHS apple-touch-icon: {apple_href}")

        # Check all icon links
        icon_els = page.query_selector_all('link[rel*="icon"]')
        for el in icon_els:
            href = el.get_attribute("href") or ""
            sizes = el.get_attribute("sizes") or ""
            rel = el.get_attribute("rel") or ""
            print(f"XHS icon: rel={rel}, sizes={sizes}, href={href[:100]}")

    except Exception as e:
        print(f"XHS error: {e}")
    finally:
        page.close()

    # 2. Douyin
    page = browser.new_page()
    try:
        page.goto("https://www.douyin.com", wait_until="domcontentloaded", timeout=15000)
        page.wait_for_timeout(2000)

        manifest_el = page.query_selector('link[rel="manifest"]')
        if manifest_el:
            manifest_href = manifest_el.get_attribute("href") or ""
            print(f"Douyin manifest: {manifest_href}")
            if manifest_href.startswith("/"):
                manifest_href = "https://www.douyin.com" + manifest_href
            resp = page.request.get(manifest_href)
            if resp.ok:
                manifest = resp.json()
                icons = manifest.get("icons", [])
                print(f"  Manifest icons: {json.dumps(icons, indent=2)}")
                for icon in sorted(icons, key=lambda x: int(x.get("sizes", "0x0").split("x")[0]), reverse=True):
                    src = icon.get("src", "")
                    if src:
                        out = os.path.join(icons_dir, "douyin-app.png")
                        if download_and_save(page, src, out):
                            break
        else:
            print("Douyin: no manifest link found")

        icon_els = page.query_selector_all('link[rel*="icon"]')
        for el in icon_els:
            href = el.get_attribute("href") or ""
            sizes = el.get_attribute("sizes") or ""
            rel = el.get_attribute("rel") or ""
            print(f"Douyin icon: rel={rel}, sizes={sizes}, href={href[:100]}")

    except Exception as e:
        print(f"Douyin error: {e}")
    finally:
        page.close()

    # 3. Bilibili
    page = browser.new_page()
    try:
        page.goto("https://www.bilibili.com", wait_until="domcontentloaded", timeout=15000)
        page.wait_for_timeout(2000)

        manifest_el = page.query_selector('link[rel="manifest"]')
        if manifest_el:
            manifest_href = manifest_el.get_attribute("href") or ""
            print(f"Bilibili manifest: {manifest_href}")
            if manifest_href.startswith("/"):
                manifest_href = "https://www.bilibili.com" + manifest_href
            resp = page.request.get(manifest_href)
            if resp.ok:
                manifest = resp.json()
                icons = manifest.get("icons", [])
                print(f"  Manifest icons: {json.dumps(icons, indent=2)}")
                for icon in sorted(icons, key=lambda x: int(x.get("sizes", "0x0").split("x")[0]), reverse=True):
                    src = icon.get("src", "")
                    if src:
                        out = os.path.join(icons_dir, "bilibili-app.png")
                        if download_and_save(page, src, out):
                            break
        else:
            print("Bilibili: no manifest link found")

        icon_els = page.query_selector_all('link[rel*="icon"]')
        for el in icon_els:
            href = el.get_attribute("href") or ""
            sizes = el.get_attribute("sizes") or ""
            rel = el.get_attribute("rel") or ""
            print(f"Bilibili icon: rel={rel}, sizes={sizes}, href={href[:100]}")

    except Exception as e:
        print(f"Bilibili error: {e}")
    finally:
        page.close()

    browser.close()