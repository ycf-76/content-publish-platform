"""平台扫码登录子进程脚本。

由 platform_login.py 通过 subprocess.Popen 启动，
通过 stdout 输出 JSON 行与父进程通信：
  - 第一行：二维码数据 {"qr_base64": "..."} 或 {"error": "..."}
  - 第二行：登录结果 {"ok": true, "cookies": [...], "user_info": {...}} 或 {"ok": false, "error": "..."}
"""
from __future__ import annotations

import base64
import json
import os
import re
import sys
import time
from pathlib import Path

STORAGE_DIR = Path(__file__).resolve().parent.parent / "storage_states"

LOGIN_URLS = {
    "xiaohongshu": "https://www.xiaohongshu.com/login",
    "douyin": "https://www.douyin.com",
    "bilibili": "https://passport.bilibili.com/login",
}

POLL_INTERVAL = 3
MAX_POLL_ATTEMPTS = 100


def _emit(data: dict) -> None:
    sys.stdout.write(json.dumps(data, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def _find_login_cookies(cookie_names: set, platform: str) -> set:
    patterns = {
        "xiaohongshu": {"web_session", "galaxy_creator_session_id"},
        "douyin": {"sessionid", "sessionid_ss", "sid_tt", "uid_tt", "odin_tt"},
        "bilibili": {"SESSDATA", "bili_jct", "DedeUserID"},
    }
    return cookie_names & patterns.get(platform, set())


def _extract_uid_from_cookies(cookies_raw: list, platform: str) -> str:
    uid_names = {
        "xiaohongshu": ["galaxy_creator_user_id", "uid", "customerClientId", "web_session"],
        "douyin": ["uid_tt", "sid_tt", "userId"],
        "bilibili": ["DedeUserID"],
    }
    for name in uid_names.get(platform, []):
        for c in cookies_raw:
            if c.get("name") == name:
                val = c.get("value", "")
                if val and len(val) < 50:
                    return val
    return ""


def _try_click_login(page, platform: str) -> None:
    sels = {
        "xiaohongshu": [
            ".login-btn", "[class*='login-btn']", "a[href*='login']",
            "[class*='Login-btn']", "[class*='loginBtn']",
            "div.login-container .login-btn",
        ],
        "douyin": [".login-btn", "[class*='login-btn']"],
        "bilibili": [],
    }
    for sel in sels.get(platform, []):
        try:
            el = page.query_selector(sel)
            if el:
                el.click()
                time.sleep(2)
                return
        except Exception:
            continue


def _try_switch_qr_tab(page, platform: str) -> None:
    sels = {
        "xiaohongshu": [
            "[class*='qrcode-tab']", "[class*='scan-login']", "[class*='qr-login']",
            "[class*='Qrcode-tab']", "[class*='icon-qrcode']",
            "div[class*='login-container'] [class*='qrcode']",
        ],
        "douyin": ["[class*='qrcode-tab']", "[class*='scan-login']"],
        "bilibili": [],
    }
    for sel in sels.get(platform, []):
        try:
            el = page.query_selector(sel)
            if el:
                el.click()
                time.sleep(2)
                return
        except Exception:
            continue


def _extract_qr_code(page, platform: str) -> dict:
    qr_sels = {
        "xiaohongshu": [
            ".login-qrcode", ".qrcode", "[class*='qr-code']", "[class*='qrcode']",
            ".login-container", "[class*='Qrcode']", "[class*='login-qr']",
            "img[src*='qrcode']", "canvas",
        ],
        "douyin": [".qrcode", "[class*='qrcode']", "[class*='qr-code']"],
        "bilibili": [".qrcode-img", "[class*='qrcode']", ".login-qr"],
    }
    for sel in qr_sels.get(platform, []):
        try:
            el = page.query_selector(sel)
            if el and el.is_visible():
                ss_bytes = el.screenshot()
                b64 = base64.b64encode(ss_bytes).decode()
                return {"qr_base64": f"data:image/png;base64,{b64}"}
        except Exception:
            continue
    try:
        login_box = page.query_selector("[class*='login'], [class*='Login']")
        if login_box:
            ss_bytes = login_box.screenshot()
            b64 = base64.b64encode(ss_bytes).decode()
            return {"qr_base64": f"data:image/png;base64,{b64}"}
    except Exception:
        pass
    try:
        ss_bytes = page.screenshot()
        b64 = base64.b64encode(ss_bytes).decode()
        return {"qr_base64": f"data:image/png;base64,{b64}"}
    except Exception as e:
        return {"error": f"截图失败: {e}"}


def _extract_user_info(page, platform: str) -> dict:
    info = {}
    nick_sels = {
        "xiaohongshu": [".user-nickname", ".nickname", ".user-name", "[class*='nickname']", "[class*='user-name']", ".side-nav .user-name"],
        "douyin": [".nickname", ".user-nickname", "[class*='nickname']"],
        "bilibili": [".nickname", ".header-entry-mini", "[class*='nickname']"],
    }
    for sel in nick_sels.get(platform, []):
        try:
            el = page.query_selector(sel)
            if el:
                text = (el.inner_text() or "").strip()
                if text and len(text) < 50:
                    info["nickname"] = text
                    break
        except Exception:
            continue
    avatar_sels = {
        "xiaohongshu": [".user-avatar img", ".avatar img", "[class*='avatar'] img"],
        "douyin": [".avatar img", "[class*='avatar'] img"],
        "bilibili": [".header-avatar img", "[class*='avatar'] img"],
    }
    for sel in avatar_sels.get(platform, []):
        try:
            el = page.query_selector(sel)
            if el:
                src = el.get_attribute("src") or ""
                if src:
                    info["avatar_url"] = src
                    break
        except Exception:
            continue
    uid_sels = {
        "xiaohongshu": [".user-info a[href*='profile']", "a[href*='/user/profile/']", "[class*='user-id']"],
        "douyin": ["a[href*='/user/']", "[class*='user-id']"],
        "bilibili": ["a[href*='space.bilibili.com']", "[class*='user-id']"],
    }
    for sel in uid_sels.get(platform, []):
        try:
            el = page.query_selector(sel)
            if el:
                href = el.get_attribute("href") or ""
                uid = _parse_uid_from_url(href, platform)
                if uid:
                    info["uid"] = uid
                    break
        except Exception:
            continue
    if not info.get("uid"):
        try:
            uid = _parse_uid_from_url(page.url, platform)
            if uid:
                info["uid"] = uid
        except Exception:
            pass
    return info


def _parse_uid_from_url(url: str, platform: str) -> str:
    patterns = {
        "xiaohongshu": [r'/user/profile/([0-9a-fA-F]{24})', r'/user/profile/(\w+)'],
        "douyin": [r'/user/(\w+)', r'/u/(\d+)'],
        "bilibili": [r'space\.bilibili\.com/(\d+)', r'/(\d{6,})'],
    }
    for pat in patterns.get(platform, []):
        m = re.search(pat, url)
        if m:
            return m.group(1)
    return ""


def main() -> None:
    if len(sys.argv) < 2:
        _emit({"error": "缺少 platform 参数"})
        return

    platform = sys.argv[1]

    try:
        STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        _emit({"error": "Playwright 未安装，请运行: pip install playwright && playwright install chromium"})
        return

    url = LOGIN_URLS.get(platform)
    if not url:
        _emit({"error": f"不支持的平台: {platform}"})
        return

    pw = None
    browser = None
    try:
        pw = sync_playwright().start()
        browser = pw.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage"],
        )
        context = browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        )
        page = context.new_page()
        page.goto(url, wait_until="networkidle", timeout=30000)
        time.sleep(2)

        _try_click_login(page, platform)
        time.sleep(1)
        _try_switch_qr_tab(page, platform)
        time.sleep(3)

        qr_data = _extract_qr_code(page, platform)
        _emit(qr_data)

        initial_cookies = {c["name"] for c in context.cookies()}
        initial_url = page.url

        for attempt in range(MAX_POLL_ATTEMPTS):
            time.sleep(POLL_INTERVAL)
            try:
                current_cookies = {c["name"] for c in context.cookies()}
                login_cookie_found = bool(_find_login_cookies(current_cookies, platform))

                user_info = _extract_user_info(page, platform)
                nickname = user_info.get("nickname", "")

                url_changed = page.url != initial_url and "login" not in page.url.lower()

                login_detected = False

                if login_cookie_found and (nickname or url_changed):
                    login_detected = True

                if not login_detected and attempt % 5 == 4:
                    try:
                        current_url = page.url
                        if "login" in current_url.lower():
                            page.goto(f"https://www.{platform}.com", wait_until="networkidle", timeout=15000)
                            time.sleep(2)
                            final_url = page.url
                            if "login" not in final_url.lower():
                                login_detected = True
                                current_cookies = {c["name"] for c in context.cookies()}
                                login_cookie_found = bool(_find_login_cookies(current_cookies, platform))
                                user_info = _extract_user_info(page, platform)
                                nickname = user_info.get("nickname", "")
                    except Exception:
                        pass

                if login_detected:
                    if not nickname:
                        try:
                            page.reload(wait_until="networkidle", timeout=15000)
                            time.sleep(2)
                            user_info = _extract_user_info(page, platform)
                            nickname = user_info.get("nickname", "")
                        except Exception:
                            pass

                    if not user_info.get("uid"):
                        try:
                            uid_from_cookie = _extract_uid_from_cookies(context.cookies(), platform)
                            if uid_from_cookie:
                                user_info["uid"] = uid_from_cookie
                        except Exception:
                            pass

                    if not user_info.get("uid"):
                        try:
                            if platform == "xiaohongshu":
                                page.goto("https://www.xiaohongshu.com", wait_until="networkidle", timeout=15000)
                                time.sleep(2)
                                try:
                                    uid_js = page.evaluate("() => { try { return window.__INITIAL_STATE__?.user?.id || ''; } catch(e) { return ''; } }")
                                    if uid_js and len(str(uid_js)) > 5:
                                        user_info["uid"] = str(uid_js)
                                except Exception:
                                    pass
                                if not user_info.get("uid"):
                                    try:
                                        uid_js2 = page.evaluate("() => { try { const m = document.cookie.match(/galaxy_creator_user_id=([^;]+)/); return m ? m[1] : ''; } catch(e) { return ''; } }")
                                        if uid_js2 and len(str(uid_js2)) > 5:
                                            user_info["uid"] = str(uid_js2)
                                    except Exception:
                                        pass
                            else:
                                page.goto(f"https://www.{platform}.com", wait_until="networkidle", timeout=15000)
                                time.sleep(2)
                        except Exception:
                            pass

                    if not user_info.get("uid"):
                        try:
                            user_info2 = _extract_user_info(page, platform)
                            if user_info2.get("uid"):
                                user_info["uid"] = user_info2["uid"]
                            if not nickname and user_info2.get("nickname"):
                                nickname = user_info2["nickname"]
                        except Exception:
                            pass

                    cookies_raw = context.cookies()
                    cookies = [
                        {
                            "name": c["name"],
                            "value": c["value"],
                            "domain": c.get("domain", ""),
                            "path": c.get("path", "/"),
                        }
                        for c in cookies_raw
                    ]

                    storage_path = STORAGE_DIR / f"{platform}.json"
                    try:
                        STORAGE_DIR.mkdir(parents=True, exist_ok=True)
                        state = context.storage_state()
                        storage_path.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
                    except Exception:
                        pass

                    if not nickname:
                        nickname = f"{platform}_user"
                    user_info["nickname"] = nickname
                    _emit({"ok": True, "cookies": cookies, "user_info": user_info})
                    return

                if attempt % 5 == 4:
                    try:
                        page.reload(wait_until="networkidle", timeout=15000)
                    except Exception:
                        pass

            except Exception as e:
                pass

        _emit({"ok": False, "error": f"登录超时（{MAX_POLL_ATTEMPTS * POLL_INTERVAL}秒）"})

    except Exception as e:
        _emit({"error": f"浏览器启动失败: {e}"})
        _emit({"ok": False, "error": str(e)[:500]})

    finally:
        try:
            if browser:
                browser.close()
            if pw:
                pw.stop()
        except Exception:
            pass


if __name__ == "__main__":
    main()