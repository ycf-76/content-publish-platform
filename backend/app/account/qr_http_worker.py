"""QR 登录 Worker（独立进程）。

根因：C:\\Python312 的 ProactorEventLoop 在 Windows 上与 playwright.async_api 不兼容，
在 uvicorn 已有事件循环里调 async_playwright 会卡死。本 worker 作为独立进程运行，
用 sync_playwright + 同步 HTTP server，绕开事件循环冲突。

启动：
    set QR_WORKER_PORT=9010
    backend\\.venv\\Scripts\\python.exe backend\\app\\account\\qr_http_worker.py 9010

接口：
    POST /qrcode                 生成二维码（保持 page alive）
    POST /status/{qr_id}         检测扫码状态（检查 URL 跳转 / cookies）
    POST /user_info/{qr_id}       抓取真实用户信息（导航到 /user/profile）
    POST /cookies/{qr_id}         导出会话 cookies（供业务端存储）
    POST /close/{qr_id}           关闭会话
    GET  /health                  健康检查

工作会话接口（用 cookies 创建，不依赖扫码 qr_id）：
    POST /session/create          用 cookies 创建工作会话 → {session_id}
    POST /search/{session_id}     搜索笔记
    POST /user_info_current/{session_id}  获取当前登录用户信息
    POST /note_detail/{session_id}        获取笔记详情
    POST /publish/{session_id}            发布笔记（半自动：填好内容不点击，等用户手动点）
    POST /publish/{session_id}/check      回查发布结果（前端轮询判断是否已跳转）
    DELETE /session/{session_id}          关闭工作会话
"""
import base64
import json
import logging
import os
import re
import secrets
import sys
import threading
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright

logging.basicConfig(level=logging.INFO, format="%(asctime)s [worker] %(levelname)s %(message)s")
logger = logging.getLogger("qr_worker")

# 浏览器在默认位置 ms-playwright/chromium-1228，不设 PLAYWRIGHT_BROWSERS_PATH
# （旧代码硬编码项目根/pw-browsers 是错的，那个目录是空的）

# 全局锁：sync_playwright 非线程安全，所有 playwright 操作必须串行
_pw_lock = threading.Lock()

_pw = None
_browser = None

# 会话表：qr_id -> {ctx, page, status, created_at, last_check}
# status: pending / scanned / confirmed / expired / error
_sessions: dict[str, dict] = {}
_sessions_lock = threading.Lock()

# 会话超时（分钟）
SESSION_TIMEOUT_MIN = 10


def _ensure_browser():
    """懒加载浏览器实例（进程级单例，带反检测参数）。

    headless 模式由环境变量 QR_WORKER_HEADLESS 控制：
      - "0" / "false"  有头模式（弹出真实浏览器窗口，用于发布功能验证）
      - 其他 / 未设置  headless 模式（默认，适合服务器/无显示器环境）

    小红书发布页的 <xhs-publish-btn> Web Component 在 headless 模式下
    可能被风控识别而拒绝渲染内部按钮（类已注册、props 齐全但 innerHTML=0）。
    参考开源项目（CSDN Playwright 教程）均使用 headless=False。
    """
    global _pw, _browser
    if _browser:
        return _browser
    _pw = sync_playwright().start()
    headless = os.environ.get("QR_WORKER_HEADLESS", "1").lower() not in ("0", "false")
    # 反自动化检测参数：
    #   --disable-blink-features=AutomationControlled  隐藏 navigator.webdriver=true
    #   其他参数屏蔽 headless 痕迹
    _browser = _pw.chromium.launch(
        headless=headless,
        args=[
            "--no-sandbox",
            "--disable-blink-features=AutomationControlled",
            "--disable-dev-shm-usage",
            "--disable-features=IsolateOrigins,site-per-process",
            "--disable-infobars",
            "--window-size=1280,800",
        ],
    )
    logger.info(f"Browser launched (headless={headless}, anti-detection enabled)")
    return _browser


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _cleanup_expired():
    """清理超时会话（调用方需持有 _pw_lock）。"""
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=SESSION_TIMEOUT_MIN)
    expired_ids = []
    with _sessions_lock:
        for qr_id, s in _sessions.items():
            created = s.get("created_at")
            if created and created < cutoff:
                expired_ids.append(qr_id)
    for qr_id in expired_ids:
        _close_session(qr_id)


def _close_session(qr_id: str):
    """关闭单个会话的 ctx（调用方需持有 _pw_lock）。"""
    with _sessions_lock:
        s = _sessions.pop(qr_id, None)
    if not s:
        return
    try:
        if s.get("page"):
            s["page"].close()
    except Exception as e:
        logger.warning(f"close page {qr_id}: {e}")
    try:
        if s.get("ctx"):
            s["ctx"].close()
    except Exception as e:
        logger.warning(f"close ctx {qr_id}: {e}")


def gen_qrcode() -> dict:
    """生成二维码：打开登录页，截图，保持 ctx+page alive。

    生成前会关闭所有旧的 pending/scanned 会话，避免残留会话堆积。
    """
    with _pw_lock:
        _cleanup_expired()
        old_ids = []
        with _sessions_lock:
            for qid, s in _sessions.items():
                if s["status"] in ("pending", "scanned"):
                    old_ids.append(qid)
        for qid in old_ids:
            logger.info(f"gen_qrcode: closing stale session {qid}")
            _close_session(qid)
        browser = _ensure_browser()
        # 反检测：使用真实 User-Agent，设置 locale/timezone 模拟真实浏览器
        ctx = browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            locale="zh-CN",
            timezone_id="Asia/Shanghai",
            extra_http_headers={
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            },
        )
        # 注入脚本：在页面加载前覆盖 navigator.webdriver = false
        ctx.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
            "Object.defineProperty(navigator, 'plugins', {get: () => [1,2,3,4,5]});"
            "Object.defineProperty(navigator, 'languages', {get: () => ['zh-CN','zh','en']});"
            "window.chrome = {runtime: {}};"
        )
        page = ctx.new_page()
        try:
            page.goto("https://www.xiaohongshu.com/login", timeout=30000)
            # 等待页面网络空闲，确保二维码加载完成
            try:
                page.wait_for_load_state("networkidle", timeout=15000)
            except Exception:
                pass
            page.wait_for_timeout(2000)
        except Exception as e:
            try:
                ctx.close()
            except Exception:
                pass
            raise RuntimeError(f"打开登录页失败: {e}")

        # 候选 selector：从小红书各版本登录页收集
        qr_selectors = [
            "img.qrcode-img",
            "#qrcode-image",
            "#qrcode-image img",
            ".login-qrcode img",
            ".qrcode img",
            "img[class*='qrcode']",
            "canvas[class*='qrcode']",
            "canvas",
        ]
        qr_el = None
        used_sel = None
        # 先尝试 wait_for_selector 等核心 selector（给足加载时间）
        for sel in qr_selectors[:3]:
            try:
                qr_el = page.wait_for_selector(sel, timeout=5000, state="visible")
                if qr_el:
                    used_sel = sel
                    break
            except Exception:
                continue
        # 兜底：query_selector 快速尝试剩余 selector
        if not qr_el:
            for sel in qr_selectors[3:]:
                el = page.query_selector(sel)
                if el:
                    try:
                        if el.is_visible():
                            qr_el = el
                            used_sel = sel
                            break
                    except Exception:
                        pass

        if not qr_el:
            # 找不到二维码元素：保存整页截图用于排查，但返回错误
            try:
                debug_ss = page.screenshot(full_page=False)
                logger.error(
                    f"QR element not found! page.url={page.url!r}, "
                    f"html snippet: {page.content()[:500]!r}"
                )
            except Exception:
                pass
            try:
                ctx.close()
            except Exception:
                pass
            raise RuntimeError("未找到二维码元素，可能页面结构变化或被反爬拦截")

        # 确保元素在视口内并完全渲染
        try:
            qr_el.scroll_into_view_if_needed()
        except Exception:
            pass
        # 多等一会让二维码图片/canvas 完全渲染（解决"二维码不完整"问题）
        page.wait_for_timeout(2500)

        # 截图前验证：对 img 元素检查 naturalWidth，对 canvas 检查非空
        tag_name = ""
        try:
            tag_name = qr_el.evaluate("el => el.tagName.toLowerCase()")
        except Exception:
            pass
        logger.info(f"QR element found via selector: {used_sel!r}, tag={tag_name!r}")

        # 如果是 img，等图片真正加载完成（naturalWidth > 0）
        if tag_name == "img":
            try:
                page.wait_for_function(
                    "el => el.complete && el.naturalWidth > 0",
                    arg=qr_el,
                    timeout=8000,
                )
            except Exception:
                logger.warning("QR img not fully loaded after 8s, screenshot anyway")

        # 截图二维码元素（用 bounding_box 确保截到完整区域）
        try:
            # 先拿 bounding_box 确认尺寸合理
            box = qr_el.bounding_box()
            if box:
                logger.info(f"QR bbox: {box}")
                # 尺寸过小可能是 placeholder
                if box.get("width", 0) < 50 or box.get("height", 0) < 50:
                    logger.warning(f"QR bbox too small: {box}, wait 2s and retry")
                    page.wait_for_timeout(2000)
                    box = qr_el.bounding_box()
                    logger.info(f"QR bbox after wait: {box}")
            d = qr_el.screenshot()
            qr_b64 = "data:image/png;base64," + base64.b64encode(d).decode()
            # 校验截图非空（PNG header + IHDR 后必须有像素数据，最小 ~1KB）
            if len(d) < 500:
                logger.warning(f"QR screenshot too small: {len(d)} bytes, retrying")
                page.wait_for_timeout(2000)
                d = qr_el.screenshot()
                qr_b64 = "data:image/png;base64," + base64.b64encode(d).decode()
            logger.info(f"QR screenshot size: {len(d)} bytes")
        except Exception as e:
            try:
                ctx.close()
            except Exception:
                pass
            raise RuntimeError(f"二维码截图失败: {e}")

        qr_id = "qr_" + secrets.token_urlsafe(16)
        with _sessions_lock:
            _sessions[qr_id] = {
                "ctx": ctx,
                "page": page,
                "status": "pending",
                "created_at": datetime.now(timezone.utc),
                "last_check": datetime.now(timezone.utc),
            }
        logger.info(f"QR generated: {qr_id}")
        return {
            "qr_id": qr_id,
            "qrcode_base64": qr_b64,
            "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat(),
        }


# 小红书登录态 cookie 关键字段（任一存在即视为已登录）
_LOGIN_COOKIE_KEYS = (
    "xhsuserid",        # 主用户 ID
    "customer-sso-sid", # SSO 会话
    "local_session",    # 本地会话
    "customerClientId", # 客户端 ID
    "access-token-creator.xiaohongshu.com",
    "galaxy_creator_session",
)

# 搜索时必须存在的 cookie（缺失会导致被风控识别为未登录）
# a1: 设备指纹（几乎所有请求都带）
# web_session: 会话 token（登录态核心）
_LOGIN_COOKIE_REQUIRED = ("a1", "web_session")


def _wait_login_cookies(ctx, page, timeout: int = 10) -> bool:
    """等待关键登录态 cookie 出现（扫码后 cookies 可能异步设置）。

    扫码确认后，小红书会异步设置 a1 / web_session 等登录态 cookie。
    如果在 cookies 完全设置前就导出，会只拿到 acw_tc（WAF cookie），
    导致后续搜索被风控识别为未登录。

    Args:
        ctx: Playwright BrowserContext
        page: Playwright Page（用于触发导航刷新 cookies）
        timeout: 最大等待秒数

    Returns:
        True 如果关键 cookie 已出现，False 如果超时
    """
    import time

    deadline = time.time() + timeout
    last_count = 0
    while time.time() < deadline:
        try:
            cookies = ctx.cookies()
            cookie_names = {c.get("name", "") for c in cookies}
            # 检查必须的登录态 cookie 是否都已出现
            has_required = all(
                any(key in name for name in cookie_names)
                for key in _LOGIN_COOKIE_REQUIRED
            )
            if has_required and len(cookies) >= 5:
                logger.info(
                    f"_wait_login_cookies: OK after {timeout - int(deadline - time.time())}s, "
                    f"{len(cookies)} cookies, has a1+web_session"
                )
                return True
            last_count = len(cookies)
        except Exception:
            pass
        time.sleep(1)

    # 超时：记录当前 cookies 状态，帮助诊断
    try:
        cookies = ctx.cookies()
        cookie_names = [c.get("name", "") for c in cookies]
        missing = [
            key for key in _LOGIN_COOKIE_REQUIRED
            if not any(key in n for n in cookie_names)
        ]
        logger.warning(
            f"_wait_login_cookies: TIMEOUT after {timeout}s, "
            f"only {len(cookies)} cookies, missing={missing}, "
            f"names={cookie_names}"
        )
    except Exception:
        logger.warning(f"_wait_login_cookies: TIMEOUT and cannot read cookies")
    return False


def _detect_login_state(page, ctx) -> str:
    """检测登录状态：'confirmed' / 'scanned' / 'pending'。

    三重判断（任一 confirmed 条件满足即视为已登录）：
    1. URL 已离开 /login
    2. 出现登录态 cookie
    3. DOM 出现登录后元素（用户头像 / "进入主页" 按钮）

    'scanned' 判断：DOM 出现 "扫描成功"/"请在手机上确认" 等文案。
    """
    # 1. URL 判断
    try:
        url = page.url or ""
    except Exception:
        url = ""
    if url and "/login" not in url:
        return "confirmed"

    # 2. Cookie 判断
    try:
        cookies = ctx.cookies()
    except Exception:
        cookies = []
    cookie_names = {c.get("name", "") for c in cookies}
    for key in _LOGIN_COOKIE_KEYS:
        if key in cookie_names:
            return "confirmed"

    # 3. DOM 判断（已登录标志）
    try:
        logged_dom = page.evaluate(
            """() => {
                // 已登录：出现用户头像或"进入主页"按钮
                if (document.querySelector('.user-avatar, .avatar-wrapper, [class*="user-info"]')) return 'confirmed';
                const btns = Array.from(document.querySelectorAll('button, a, div'));
                if (btns.some(el => /进入主页|开始使用|立即体验/.test(el.textContent || ''))) return 'confirmed';
                // 已扫码未确认：出现确认提示
                if (btns.some(el => /扫描成功|请在手机上确认|已扫描/.test(el.textContent || ''))) return 'scanned';
                return 'pending';
            }"""
        )
        if logged_dom in ("confirmed", "scanned"):
            return logged_dom
    except Exception:
        pass

    return "pending"


def check_status(qr_id: str) -> dict:
    """检测扫码状态。pending -> scanned(已扫码未确认) -> confirmed(已登录)。

    如果检测到"二维码已过期"提示，自动点击刷新按钮重新生成二维码，
    并把新的 qrcode_base64 写回 session，返回 refreshed 状态供前端更新。
    """
    with _pw_lock:
        with _sessions_lock:
            s = _sessions.get(qr_id)
        if not s:
            return {"status": "expired", "message": "会话不存在或已过期"}
        if s["status"] in ("confirmed", "expired", "error"):
            return {"status": s["status"], "message": s.get("message", "")}

        page = s["page"]
        ctx = s["ctx"]
        try:
            # 先检查页面是否提示"二维码已过期"，若是则点击刷新并重截
            try:
                expired_info = page.evaluate(
                    """() => {
                        const body = document.body?.innerText || '';
                        const expired = /二维码已过期|已过期|点击刷新/.test(body);
                        const refreshBtn = document.querySelector(
                            '[class*="refresh"], [class*="refresh-code"], .status-desc.refresh, button[class*="refresh"]'
                        );
                        return {
                            expired: expired,
                            refreshBtn: !!refreshBtn,
                            refreshClass: refreshBtn ? refreshBtn.className : '',
                        };
                    }"""
                )
            except Exception:
                expired_info = {"expired": False}

            if expired_info.get("expired"):
                logger.info(
                    f"QR {qr_id} expired on page, refreshing... "
                    f"(refreshBtn={expired_info.get('refreshBtn')}, "
                    f"class={expired_info.get('refreshClass', '')!r})"
                )
                # 点击刷新按钮（多个候选）
                refreshed = False
                for sel in [
                    ".status-desc.refresh",
                    "[class*='refresh-code']",
                    "button[class*='refresh']",
                    "[class*='refresh']",
                ]:
                    try:
                        btn = page.query_selector(sel)
                        if btn:
                            btn.click()
                            refreshed = True
                            logger.info(f"QR {qr_id} refresh clicked: {sel!r}")
                            break
                    except Exception:
                        continue
                if refreshed:
                    # 等待新二维码加载
                    page.wait_for_timeout(800)
                    # 重新截图
                    try:
                        qr_el = page.query_selector("img.qrcode-img") or page.query_selector("img[class*='qrcode']")
                        if qr_el:
                            try:
                                qr_el.scroll_into_view_if_needed()
                            except Exception:
                                pass
                            page.wait_for_timeout(300)
                            try:
                                page.wait_for_function(
                                    "el => el.complete && el.naturalWidth > 0",
                                    arg=qr_el,
                                    timeout=8000,
                                )
                            except Exception:
                                pass
                            d = qr_el.screenshot()
                            new_b64 = "data:image/png;base64," + base64.b64encode(d).decode()
                            s["qrcode_base64"] = new_b64
                            s["status"] = "pending"
                            s["last_check"] = datetime.now(timezone.utc)
                            logger.info(f"QR {qr_id} refreshed, new screenshot size={len(d)} bytes")
                            return {
                                "status": "pending",
                                "message": "二维码已自动刷新",
                                "qrcode_base64": new_b64,
                            }
                    except Exception as e:
                        logger.warning(f"QR {qr_id} refresh screenshot failed: {e}")
                # 刷新失败，标记过期
                s["status"] = "expired"
                s["message"] = "二维码已过期，请重新生成"
                return {"status": "expired", "message": "二维码已过期，请重新生成"}

            state = _detect_login_state(page, ctx)
            s["last_check"] = datetime.now(timezone.utc)

            # 调试日志：当前 URL + cookie 数量
            try:
                url = page.url
                n_cookies = len(ctx.cookies())
                logger.info(f"QR {qr_id} state={state} url={url!r} cookies={n_cookies}")
            except Exception:
                pass

            if state == "confirmed":
                s["status"] = "confirmed"
                s["message"] = "已登录"
                logger.info(f"QR {qr_id} confirmed (logged in)")
                return {"status": "confirmed", "message": "已登录"}
            if state == "scanned":
                # 仅记录扫描状态，但不固化（防止误判）
                if s["status"] != "scanned":
                    s["status"] = "scanned"
                    logger.info(f"QR {qr_id} scanned (waiting for confirm)")
                return {"status": "scanned", "message": "已扫码，请在手机上确认"}
            # 仍待扫码
            if s["status"] == "scanned":
                # 从 scanned 回退到 pending（状态变化）
                s["status"] = "pending"
            return {"status": "pending", "message": "等待扫码"}
        except Exception as e:
            s["status"] = "error"
            s["message"] = f"检测失败: {e}"
            logger.warning(f"QR {qr_id} status check failed: {e}")
            return {"status": "error", "message": f"检测失败: {e}"}


_last_bg_detect: dict[str, float] = {}
_BG_DETECT_INTERVAL = 2.0
_bg_detect_queue: list[str] = []


def _background_detect_pending():
    """后台检测 pending/scanned 会话的扫码状态（在 HTTP 请求间隙调用）。

    每次只检测一个会话，检测完立即返回主循环，避免长时间阻塞 HTTP 请求。
    每个 qr_id 最多每 _BG_DETECT_INTERVAL 秒检测一次。
    """
    import time as _time

    global _bg_detect_queue

    now = _time.monotonic()
    if not _bg_detect_queue:
        with _sessions_lock:
            _bg_detect_queue = [
                qid for qid, s in _sessions.items()
                if s["status"] in ("pending", "scanned")
            ]
    if not _bg_detect_queue:
        return

    qr_id = _bg_detect_queue.pop(0)
    last = _last_bg_detect.get(qr_id, 0.0)
    if now - last < _BG_DETECT_INTERVAL:
        return
    _last_bg_detect[qr_id] = now
    try:
        check_status(qr_id)
    except Exception as e:
        logger.warning(f"bg detect {qr_id}: {e}")
    with _sessions_lock:
        expired_ids = [
            qid for qid in list(_last_bg_detect)
            if qid not in _sessions
        ]
    for qid in expired_ids:
        _last_bg_detect.pop(qid, None)


# 提取用户信息的 JS 脚本（多渠道兜底）
# 渠道1: __NEXT_DATA__（旧版 Next.js SSR）
# 渠道2: window.__INITIAL_STATE__（Redux 状态）
# 渠道3: script[type=application/json]（新版 SSR 数据）
# 渠道4: DOM 元素（用户头像 alt、name 容器等）
_USER_INFO_JS = """() => {
  const findUser = (o, dp) => {
    if (!o || typeof o !== 'object' || dp > 7) return null;
    if (o.user_id && o.nickname && (o.image || o.avatar || o.red_id !== undefined || o.desc)) return o;
    if (o.id && o.nickname && (o.image || o.avatar)) return {user_id: o.id, nickname: o.nickname, image: o.image, red_id: o.red_id || ''};
    if (o.userId && o.nickname) return {user_id: o.userId, nickname: o.nickname, image: o.image || o.avatar || '', red_id: o.red_id || ''};
    for (const v of Object.values(o)) {
      const r = findUser(v, dp + 1);
      if (r) return r;
    }
    return null;
  };

  const normalizeUser = (u) => {
    if (!u) return null;
    const uid = String(u.user_id || u.id || u.userId || '');
    const nick = String(u.nickname || u.nickName || u.name || '');
    // 小红书 SSR 用户对象字段：images（小图）/ imageb（大图）
    const avatar = String(u.images || u.imageb || u.image || u.avatar || u.avatar_url || u.head || '');
    const red = String(u.red_id || u.redId || u.redID || '');
    if (!uid || !nick) return null;
    return { xhs_user_id: uid, nickname: nick, avatar_url: avatar, red_id: red };
  };

  // 渠道1: __NEXT_DATA__
  try {
    const nd = document.getElementById('__NEXT_DATA__');
    if (nd) {
      const d = JSON.parse(nd.textContent || '{}');
      const u = findUser(d.props?.pageProps, 0) || findUser(d, 0);
      const r = normalizeUser(u);
      if (r) return r;
    }
  } catch(e) {}

  // 渠道2: window.__INITIAL_STATE__（Vue ref，真实值在 _value）
  // 小红书 /explore 页面的 user.userInfo 是 Vue ref，需要读 _value
  try {
    if (window.__INITIAL_STATE__) {
      const state = window.__INITIAL_STATE__;
      const userSection = state.user || {};
      // 直接读 userInfo 的 _value（Vue ref 内部存储）
      let ui = userSection.userInfo;
      if (ui) {
        // Vue ref: 真实值在 _value
        if (ui._value !== undefined) ui = ui._value;
        else if (ui.value !== undefined) ui = ui.value;
        if (ui && (ui.userId || ui.user_id) && ui.nickname) {
          const r = normalizeUser({
            user_id: ui.userId || ui.user_id,
            nickname: ui.nickname,
            images: ui.images || '',
            imageb: ui.imageb || '',
            image: ui.image || '',
            red_id: ui.redId || ui.red_id || '',
          });
          if (r) return r;
        }
      }
      // 兜底：递归查找（处理非 ref 情况）
      const u = findUser(state, 0);
      const r = normalizeUser(u);
      if (r) return r;
    }
  } catch(e) {}

  // 渠道3: 所有 script[type=application/json]
  try {
    const scripts = document.querySelectorAll('script[type="application/json"]');
    for (const sc of scripts) {
      try {
        const d = JSON.parse(sc.textContent || '{}');
        const u = findUser(d, 0);
        const r = normalizeUser(u);
        if (r) return r;
      } catch(e) {}
    }
  } catch(e) {}

  // 渠道4: DOM 元素提取
  try {
    // 用户头像 img：alt 通常是昵称，src 是头像 URL
    const avatarImg = document.querySelector(
      '.user-avatar img, .avatar img, img[class*="avatar"], .user-info img, .info-avatar img'
    );
    // 昵称容器
    const nickEl = document.querySelector(
      '.user-nickname, .nickname, .user-name, [class*="nickname"], [class*="user-name"], .info-name'
    );
    // 小红书号容器
    const redIdEl = document.querySelector(
      '[class*="red-id"], [class*="redId"], [class*="xhs-id"]'
    );

    if (avatarImg || nickEl) {
      const nick = nickEl ? (nickEl.textContent || '').trim() : (avatarImg?.alt || '').trim();
      const avatar = avatarImg ? (avatarImg.src || '') : '';
      // 从 redIdEl 提取红号
      let red = '';
      if (redIdEl) {
        const t = (redIdEl.textContent || '').trim();
        const m = t.match(/\\d+/);
        if (m) red = m[0];
      }
      if (nick && nick.length < 32) {
        // 注意：red_id 不是 user_id（两个字段不同），不能用作 xhs_user_id。
        // 渠道 4 仅作为兜底，返回 red_id 但 user_id 留空，让上层从其他渠道获取 user_id。
        // 如果只有渠道 4 命中（无 user_id），上层会校验失败抛异常。
        if (red) {
          return { xhs_user_id: '', nickname: nick, avatar_url: avatar, red_id: red };
        }
      }
    }
  } catch(e) {}

  return null;
}"""


def fetch_user_info(qr_id: str) -> dict:
    """扫码成功后抓取真实用户信息。

    策略（避免触发风控）：
    1. 先回 /explore（登录成功后的首页，不会触发风控），从 __NEXT_DATA__ / DOM 拿用户信息
    2. 如果 /explore 拿不到，再尝试 /user/profile（可能触发二次验证，作为兜底）
    """
    with _pw_lock:
        with _sessions_lock:
            s = _sessions.get(qr_id)
        if not s:
            raise RuntimeError("会话不存在或已过期")
        if s["status"] != "confirmed":
            raise RuntimeError(f"会话未确认登录（status={s['status']}），请先扫码")

        page = s["page"]
        ctx = s["ctx"]
        logger.info(f"fetch_user_info start: qr_id={qr_id}")
        try:
            # 导航前记录当前状态
            try:
                logger.info(
                    f"fetch_user_info pre-nav: url={page.url!r}, "
                    f"cookies={len(ctx.cookies())}"
                )
            except Exception:
                pass

            # 如果当前在 captcha 验证码页，先回 /explore
            try:
                current_url = page.url or ""
            except Exception:
                current_url = ""
            if "captcha" in current_url or "/login" in current_url:
                logger.info(f"fetch_user_info: current url is {current_url!r}, navigating to /explore")
                page.goto(
                    "https://www.xiaohongshu.com/explore",
                    wait_until="domcontentloaded",
                    timeout=30000,
                )
                page.wait_for_timeout(3000)
                try:
                    page.wait_for_load_state("networkidle", timeout=15000)
                except Exception:
                    pass

            # 步骤 1：从当前页（应该是 /explore）提取用户信息
            try:
                post_url = page.url or ""
                logger.info(f"fetch_user_info post-nav: url={post_url!r}, cookies={len(ctx.cookies())}")
            except Exception:
                pass

            if "/login" in (page.url or "") or "captcha" in (page.url or ""):
                raise RuntimeError(f"会话无效：被重定向到 {page.url}")

            info = page.evaluate(_USER_INFO_JS)
            if info:
                xhs_user_id = (info.get("xhs_user_id") or "").strip()
                nickname = (info.get("nickname") or "").strip()
                avatar_url = (info.get("avatar_url") or "").strip()
                if xhs_user_id and nickname:
                    fake_nicknames = {"xiaohongshu_user", "未命名用户", "小红书用户"}
                    if nickname not in fake_nicknames:
                        logger.info(
                            f"[REAL] user_info OK from /explore: user_id={xhs_user_id}, nickname={nickname}"
                        )
                        # 等待关键登录态 cookie 异步设置完成（防止导出时只有 acw_tc）
                        _wait_login_cookies(ctx, page, timeout=10)
                        return {
                            "xhs_user_id": xhs_user_id,
                            "nickname": nickname,
                            "avatar_url": avatar_url,
                            "red_id": info.get("red_id", ""),
                        }

            # 步骤 2：/explore 拿不到，尝试 /user/profile（可能触发风控，作为兜底）
            logger.info(f"fetch_user_info: /explore no user info, trying /user/profile")
            page.goto(
                "https://www.xiaohongshu.com/user/profile",
                wait_until="domcontentloaded",
                timeout=30000,
            )
            page.wait_for_timeout(3000)
            try:
                page.wait_for_load_state("networkidle", timeout=15000)
            except Exception:
                pass

            try:
                profile_url = page.url or ""
                logger.info(f"fetch_user_info profile-nav: url={profile_url!r}")
            except Exception:
                pass

            if "/login" in (page.url or ""):
                raise RuntimeError("会话无效：被重定向到登录页")
            if "captcha" in (page.url or ""):
                raise RuntimeError("访问个人主页触发了小红书二次验证（风控），请稍后重试或在 App 内活跃一段时间后再试")

            info = page.evaluate(_USER_INFO_JS)
            if not info:
                # 记录详细诊断信息
                try:
                    diag = page.evaluate(
                        """() => {
                            const out = {};
                            out.scripts = Array.from(document.querySelectorAll('script')).map(sc => ({
                                type: sc.type || '',
                                id: sc.id || '',
                                hasContent: !!(sc.textContent && sc.textContent.trim()),
                                contentLen: (sc.textContent || '').length,
                            }));
                            out.globals = Object.keys(window).filter(k =>
                                /state|initial|user|profile|__/.test(k) && typeof window[k] === 'object'
                            );
                            out.dom = {
                                avatarImgs: document.querySelectorAll('img[class*="avatar"], img[class*="Avatar"]').length,
                                userDivs: document.querySelectorAll('[class*="user"], [class*="User"]').length,
                                nickDivs: document.querySelectorAll('[class*="nick"], [class*="Nick"], [class*="name"], [class*="Name"]').length,
                            };
                            out.bodyText = (document.body?.innerText || '').slice(0, 500);
                            return out;
                        }"""
                    )
                    logger.error(
                        f"fetch_user_info no user info! diag={diag!r}"
                    )
                except Exception as e:
                    logger.error(f"fetch_user_info diag failed: {e}")
                raise RuntimeError("无法从页面提取用户信息（页面结构已变化，需更新提取脚本）")

            xhs_user_id = (info.get("xhs_user_id") or "").strip()
            nickname = (info.get("nickname") or "").strip()
            avatar_url = (info.get("avatar_url") or "").strip()

            if not xhs_user_id or not nickname:
                logger.warning(
                    f"fetch_user_info incomplete: user_id={xhs_user_id!r}, "
                    f"nickname={nickname!r}, raw={info!r}"
                )
                raise RuntimeError(
                    f"用户信息不完整: user_id={xhs_user_id!r}, nickname={nickname!r}"
                )

            fake_nicknames = {"xiaohongshu_user", "未命名用户", "小红书用户"}
            if nickname in fake_nicknames:
                logger.warning(f"fetch_user_info fake nickname: {nickname!r}")
                raise RuntimeError(f"检测到假昵称: {nickname!r}")

            logger.info(
                f"[REAL] user_info OK: user_id={xhs_user_id}, nickname={nickname}"
            )
            # 等待关键登录态 cookie 异步设置完成（防止导出时只有 acw_tc）
            _wait_login_cookies(ctx, page, timeout=10)
            return {
                "xhs_user_id": xhs_user_id,
                "nickname": nickname,
                "avatar_url": avatar_url,
                "red_id": info.get("red_id", ""),
            }
        except RuntimeError:
            raise
        except Exception as e:
            logger.exception(f"fetch_user_info unexpected error: {e}")
            raise RuntimeError(f"抓取用户信息失败: {e}")


def export_cookies(qr_id: str) -> list[dict]:
    """导出会话 cookies 供业务端持久化存储。

    导出前会再次等待关键登录态 cookie（fetch_user_info 已等过一次，
    这里作为兜底，防止 cookies 在 fetch_user_info 后又丢失）。
    """
    with _pw_lock:
        with _sessions_lock:
            s = _sessions.get(qr_id)
        if not s:
            raise RuntimeError("会话不存在或已过期")
        ctx = s["ctx"]
        page = s.get("page")
        try:
            # 兜底：再等一次关键 cookie（最多 5 秒）
            if page:
                _wait_login_cookies(ctx, page, timeout=5)

            cookies = ctx.cookies()

            # 完整性校验：记录关键 cookie 是否存在
            cookie_names = {c.get("name", "") for c in cookies}
            missing_required = [
                key for key in _LOGIN_COOKIE_REQUIRED
                if not any(key in name for name in cookie_names)
            ]
            if len(cookies) < 5 or missing_required:
                logger.warning(
                    f"export_cookies: INCOMPLETE - {len(cookies)} cookies, "
                    f"missing required={missing_required}, "
                    f"names={sorted(cookie_names)}"
                )
            else:
                logger.info(
                    f"export_cookies: OK - {len(cookies)} cookies, "
                    f"has a1+web_session"
                )

            # 序列化为可 JSON 化的 dict 列表
            return [
                {
                    "name": c["name"],
                    "value": c["value"],
                    "domain": c.get("domain", ""),
                    "path": c.get("path", "/"),
                    "expires": c.get("expires", -1),
                }
                for c in cookies
            ]
        except Exception as e:
            raise RuntimeError(f"导出 cookies 失败: {e}")


def close_session(qr_id: str) -> dict:
    with _pw_lock:
        _close_session(qr_id)
    return {"success": True, "message": "会话已关闭"}


# ---------------------------------------------------------------------------
# 工作会话接口（用 cookies 创建，不依赖扫码 qr_id）
# ---------------------------------------------------------------------------

def _new_anti_detect_context():
    """创建反检测浏览器 context（复用 gen_qrcode 的反检测参数）。"""
    browser = _ensure_browser()
    ctx = browser.new_context(
        viewport={"width": 1280, "height": 800},
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        locale="zh-CN",
        timezone_id="Asia/Shanghai",
        extra_http_headers={"Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8"},
    )
    ctx.add_init_script(
        "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
        "Object.defineProperty(navigator, 'plugins', {get: () => [1,2,3,4,5]});"
        "Object.defineProperty(navigator, 'languages', {get: () => ['zh-CN','zh','en']});"
        "window.chrome = {runtime: {}};"
    )
    return ctx


def create_work_session(cookies: list[dict]) -> dict:
    """用 cookies 创建工作会话，返回 session_id。

    cookies 格式与 export_cookies 输出一致：
        [{name, value, domain, path, expires}, ...]
    """
    with _pw_lock:
        _cleanup_expired()
        ctx = _new_anti_detect_context()
        # 注入 cookies
        playwright_cookies = []
        for c in cookies:
            pc = {
                "name": c.get("name", ""),
                "value": c.get("value", ""),
                "domain": c.get("domain", ".xiaohongshu.com"),
                "path": c.get("path", "/"),
            }
            if c.get("expires", -1) > 0:
                pc["expires"] = c["expires"]
            playwright_cookies.append(pc)
        try:
            ctx.add_cookies(playwright_cookies)
        except Exception as e:
            try:
                ctx.close()
            except Exception:
                pass
            raise RuntimeError(f"注入 cookies 失败: {e}")

        page = ctx.new_page()
        session_id = "sess_" + secrets.token_urlsafe(16)
        with _sessions_lock:
            _sessions[session_id] = {
                "ctx": ctx,
                "page": page,
                "status": "confirmed",  # 已有 cookies，视为已登录
                "created_at": datetime.now(timezone.utc),
                "last_check": datetime.now(timezone.utc),
            }
        logger.info(f"Work session created: {session_id}")
        return {"session_id": session_id}


def _parse_count(text) -> int:
    """解析小红书的数字文本，支持 '253' / '1.4万' / '2.6万' / '3亿'。

    小红书前端显示的互动量可能是字符串格式（如 "1.4万"），
    feed 接口的 interact_info 里 count 也是字符串（如 "253"），需要统一转 int。
    """
    if not text:
        return 0
    s = str(text).strip().replace(",", "").replace(" ", "")
    if not s:
        return 0
    try:
        if "万" in s:
            return int(float(s.replace("万", "")) * 10000)
        if "亿" in s:
            return int(float(s.replace("亿", "")) * 100000000)
        return int(s)
    except (ValueError, TypeError):
        import re
        nums = re.findall(r"[\d.]+", s)
        if not nums:
            return 0
        try:
            n = float(nums[0])
            if "万" in s:
                return int(n * 10000)
            if "亿" in s:
                return int(n * 100000000)
            return int(n)
        except ValueError:
            return 0


def search_with_details(
    session_id: str,
    keyword: str,
    limit: int = 8,
    detail_top_n: int = 5,
) -> dict:
    """搜索小红书笔记，并对 top N 结果采集详情数据（绕过风控）。

    绕过 300031 风控的关键：搜索结果卡片的 href 自带 xsec_token，
    点击进入的 URL 带 token 不会被风控拦截（直接 goto /explore/{note_id} 会被拦截）。
    进入详情页后拦截 /api/sns/web/v1/feed XHR，提取 interact_info。

    Args:
        session_id: 工作会话 ID
        keyword: 搜索关键词
        limit: 搜索结果数量（默认8）
        detail_top_n: 对前 N 条采集详情（默认5）

    Returns:
        {"results": [...], "details_collected": int}
        top N 条 result 包含完整字段：
        - 基础：note_id, title, author, likes, comments, url, cover_img, platform
        - 详情：collects, shares, desc, type, tags, author_id, author_avatar, detail_collected
    """
    from urllib.parse import quote
    import time

    with _pw_lock:
        _cleanup_expired()
        with _sessions_lock:
            s = _sessions.get(session_id)
        if not s:
            raise RuntimeError("工作会话不存在或已过期")
        page = s["page"]

        try:
            # 1. 搜索
            encoded_keyword = quote(keyword, safe="")
            search_url = (
                "https://www.xiaohongshu.com/search_result?keyword="
                + encoded_keyword + "&source=web_search_result_notes"
            )
            page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(4000)
            try:
                page.wait_for_load_state("networkidle", timeout=15000)
            except Exception:
                pass

            # 检查登录态
            has_login = page.evaluate(
                "() => !!document.querySelector('[class*=\"login\"], [class*=\"qrcode\"]')"
            )
            if has_login:
                raise RuntimeError("cookies 已过期，页面跳转到登录页")

            # 2. 提取搜索结果（基础信息）
            results = page.evaluate(
                """(limit) => {
    const items = document.querySelectorAll('section[class*="note-item"]');
    const out = [];
    for (let i = 0; i < Math.min(items.length, limit); i++) {
        const el = items[i];
        const link = el.querySelector('a[href*="explore"]') || el.querySelector('a');
        const titleEl = el.querySelector('[class*="title"]');
        const authorEl = el.querySelector('[class*="author"] [class*="name"], [class*="author"]');
        const likeEl = el.querySelector('[class*="count"]');
        const imgEl = el.querySelector('img');
        const href = link ? (link.getAttribute('href') || '') : '';
        const noteId = href.match(/explore\\/([^\\/?]+)/)?.[1] || '';

        out.push({
            note_id: noteId,
            title: titleEl ? titleEl.textContent.trim() : '',
            author: authorEl ? authorEl.textContent.trim() : '',
            likes_text: likeEl ? likeEl.textContent.trim() : '0',
            url: href.startsWith('http') ? href : 'https://www.xiaohongshu.com' + href,
            cover_img: imgEl ? (imgEl.getAttribute('src') || '') : '',
        });
    }
    return out;
}""", limit)

            # 解析 likes（支持 "X.X万" 格式），补全默认字段
            for r in results:
                r["likes"] = _parse_count(r.pop("likes_text", "0"))
                r["comments"] = 0
                r["platform"] = "xiaohongshu"

            if not results:
                logger.info(f"[WORK] search_with_details '{keyword}': 0 notes")
                return {"results": [], "details_collected": 0}

            detail_top_n = min(detail_top_n, len(results))
            logger.info(
                f"[WORK] search_with_details '{keyword}': {len(results)} notes, "
                f"collecting details for top {detail_top_n}"
            )

            # 3. 对 top N 条采集详情（点击卡片 + 拦截 feed XHR）
            details_collected = 0

            for i in range(detail_top_n):
                try:
                    # 重新查找卡片（DOM 可能因滚动/渲染变化）
                    cards = page.query_selector_all('section[class*="note-item"]')
                    if i >= len(cards):
                        logger.warning(
                            f"[WORK] detail {i+1}: card index {i} out of {len(cards)} cards"
                        )
                        break

                    card = cards[i]
                    try:
                        card.scroll_into_view_if_needed(timeout=3000)
                    except Exception:
                        pass
                    page.wait_for_timeout(500)

                    # 点击卡片，同时等待 feed XHR 响应
                    feed_data = None
                    try:
                        with page.expect_response(
                            lambda resp: "/api/sns/web/v1/feed" in resp.url,
                            timeout=15000
                        ) as resp_info:
                            card.click(timeout=5000)
                        response = resp_info.value
                        feed_data = response.json()
                    except Exception as e:
                        logger.warning(f"[WORK] detail {i+1}: feed XHR timeout/failed: {e}")

                    # 提取 note_card 数据
                    if feed_data:
                        try:
                            feed_items = feed_data.get("data", {}).get("items", [])
                            if feed_items:
                                note_card = feed_items[0].get("note_card", {}) or {}
                                interact = note_card.get("interact_info", {}) or {}
                                user = note_card.get("user", {}) or {}

                                results[i]["likes"] = _parse_count(interact.get("liked_count", "0"))
                                results[i]["comments"] = _parse_count(interact.get("comment_count", "0"))
                                results[i]["collects"] = _parse_count(interact.get("collected_count", "0"))
                                results[i]["shares"] = _parse_count(interact.get("share_count", "0"))
                                results[i]["author_fans"] = 0  # feed 接口不返回 fans
                                results[i]["desc"] = note_card.get("desc", "")
                                results[i]["type"] = note_card.get("type", "")
                                results[i]["tags"] = [
                                    t.get("name", "")
                                    for t in note_card.get("tag_list", [])
                                    if isinstance(t, dict) and t.get("name")
                                ]
                                results[i]["author"] = user.get("nickname", results[i].get("author", ""))
                                results[i]["author_id"] = user.get("user_id", "")
                                results[i]["author_avatar"] = user.get("avatar", "")
                                results[i]["detail_collected"] = True
                                details_collected += 1
                                logger.info(
                                    f"[WORK] detail {i+1}/{detail_top_n}: "
                                    f"note_id={results[i]['note_id']}, "
                                    f"likes={results[i]['likes']}, "
                                    f"comments={results[i]['comments']}, "
                                    f"collects={results[i]['collects']}"
                                )
                            else:
                                logger.warning(f"[WORK] detail {i+1}: feed items empty")
                                results[i]["detail_collected"] = False
                        except Exception as e:
                            logger.warning(f"[WORK] detail {i+1}: parse feed failed: {e}")
                            results[i]["detail_collected"] = False
                    else:
                        results[i]["detail_collected"] = False

                    # 4. 关闭详情 modal，回到搜索页
                    try:
                        page.keyboard.press("Escape")
                        page.wait_for_timeout(1500)
                        current_url = page.url or ""
                        # 如果 ESC 没关掉（还在 /explore/），尝试点击关闭按钮
                        if "/explore/" in current_url and "/search_result" not in current_url:
                            try:
                                close_btn = page.query_selector('[class*="close"], [class*="close-circle"], [class*="back"]')
                                if close_btn:
                                    close_btn.click(timeout=2000)
                                    page.wait_for_timeout(1000)
                            except Exception:
                                pass
                        # 如果还不行，重新 goto 搜索页
                        if "/search_result" not in (page.url or ""):
                            page.goto(search_url, wait_until="domcontentloaded", timeout=20000)
                            page.wait_for_timeout(2000)
                    except Exception as e:
                        logger.warning(f"[WORK] detail {i+1}: close modal failed: {e}")

                    # 间隔 2 秒防风控
                    if i < detail_top_n - 1:
                        time.sleep(2)

                except Exception as e:
                    logger.warning(f"[WORK] detail {i+1} outer failed: {e}")
                    if i < len(results):
                        results[i]["detail_collected"] = False
                    continue

            logger.info(
                f"[WORK] search_with_details done: "
                f"{details_collected}/{detail_top_n} details collected"
            )
            return {"results": results, "details_collected": details_collected}

        except RuntimeError:
            raise
        except Exception as e:
            logger.error(f"[WORK] search_with_details failed: {e}")
            raise RuntimeError(f"搜索失败: {e}")


def search_notes(session_id: str, keyword: str, limit: int = 20) -> list[dict]:
    """用指定工作会话搜索小红书笔记。"""
    from urllib.parse import quote
    with _pw_lock:
        _cleanup_expired()  # 顺带清理过期会话
        with _sessions_lock:
            s = _sessions.get(session_id)
        if not s:
            raise RuntimeError("工作会话不存在或已过期")
        page = s["page"]
        try:
            # 关键词 URL 编码，避免中文导致 URL 异常
            encoded_keyword = quote(keyword, safe="")
            url = (
                "https://www.xiaohongshu.com/search_result?keyword="
                + encoded_keyword + "&source=web_search_result_notes"
            )
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(4000)
            try:
                page.wait_for_load_state("networkidle", timeout=15000)
            except Exception:
                pass

            # 检查是否被重定向到登录页（cookies 过期）
            has_login = page.evaluate(
                "() => !!document.querySelector('[class*=\"login\"], [class*=\"qrcode\"]')"
            )
            if has_login:
                logger.warning(f"[WORK] search '{keyword}': cookies 过期，页面跳转登录页")
                raise RuntimeError("cookies 已过期，页面跳转到登录页，请重新扫码登录")

            results = page.evaluate(
                """(limit) => {
    const items = document.querySelectorAll('[class*=note-item], [class*=search-result-item], section[class*=note]');
    const out = [];
    for (let i = 0; i < Math.min(items.length, limit); i++) {
        const el = items[i]; const link = el.querySelector('a') || el;
        const titleEl = el.querySelector('[class*=title]');
        const descEl = el.querySelector('[class*=desc], [class*=content]');
        const authorEl = el.querySelector('[class*=author], [class*=name]');
        const likeEl = el.querySelector('[class*=like], [class*=count]');
        const imgEl = el.querySelector('img');
        const href = link.getAttribute('href') || '';
        const noteId = href.match(/explore\\/([^\\/?]+)/)?.[1] || '';

        // 【临时探测】提取所有含数字的文本节点，找评论数/粉丝数在哪
        let _debugAllTexts = [];
        if (i === 0) {
            const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
            let node;
            while (node = walker.nextNode()) {
                const t = node.textContent.trim();
                if (t) _debugAllTexts.push(t.substring(0, 50));
            }
        }

        // 探测评论数：找含"评论"字样的元素，或第 2 个数字类元素
        let comments = 0;
        const commentEl = el.querySelector('[class*=comment], [class*=discuss]');
        if (commentEl) {
            comments = parseInt(commentEl.textContent.replace(/[^0-9]/g, '') || '0') || 0;
        }
        // 兜底：找所有数字类元素，第 2 个通常是评论数（第 1 个是点赞）
        if (!comments) {
            const numEls = el.querySelectorAll('[class*=count], [class*=like], [class*=num]');
            if (numEls.length >= 2) {
                comments = parseInt(numEls[1].textContent.replace(/[^0-9]/g, '') || '0') || 0;
            }
        }

        out.push({
            note_id: noteId,
            title: titleEl ? titleEl.textContent.trim() : '',
            desc: descEl ? descEl.textContent.trim().substring(0, 200) : '',
            author: authorEl ? authorEl.textContent.trim() : '',
            likes: parseInt(likeEl?.textContent?.replace(/[^0-9]/g, '') || '0') || 0,
            comments: comments,
            url: href.startsWith('http') ? href : 'https://www.xiaohongshu.com' + href,
            cover_img: imgEl ? imgEl.getAttribute('src') || '' : '',
            _debug_first_card_texts: i === 0 ? _debugAllTexts : undefined,
            _debug_first_card_html: i === 0 ? el.outerHTML.substring(0, 2000) : undefined,
        });
    }
    return out;
}""", limit)

            # 【临时探测】打印第一条卡片的完整文本和 HTML
            if results and results[0].get("_debug_first_card_texts"):
                logger.info(f"[WORK] ====== 第一条卡片所有文本节点 ======")
                for t in results[0]["_debug_first_card_texts"]:
                    logger.info(f"[WORK]   text={t!r}")
                logger.info(f"[WORK] ====== 第一条卡片 outerHTML ======")
                logger.info(f"[WORK] {results[0].get('_debug_first_card_html', '')}")
                logger.info(f"[WORK] ====== end ======")

            logger.info(f"[WORK] search '{keyword}': {len(results)} notes")
            return results[:limit]
        except RuntimeError:
            raise
        except Exception as e:
            logger.error(f"[WORK] search failed: {e}")
            raise RuntimeError(f"搜索失败: {e}")


def get_current_user_info_via_session(session_id: str) -> dict:
    """用指定工作会话获取当前登录用户信息。

    策略（避免触发风控）：
    1. 先去 /explore（不会触发风控），从 __INITIAL_STATE__.user.userInfo._value 提取
    2. 如果 /explore 拿不到，再尝试 /user/profile（可能触发二次验证，作为兜底）
    """
    with _pw_lock:
        _cleanup_expired()  # 顺带清理过期会话
        with _sessions_lock:
            s = _sessions.get(session_id)
        if not s:
            raise RuntimeError("工作会话不存在或已过期")
        page = s["page"]
        try:
            # 步骤 1：先去 /explore 提取用户信息（避免风控）
            current_url = ""
            try:
                current_url = page.url or ""
            except Exception:
                pass
            if "xiaohongshu.com" not in current_url or "captcha" in current_url or "/login" in current_url:
                page.goto(
                    "https://www.xiaohongshu.com/explore",
                    wait_until="domcontentloaded",
                    timeout=30000,
                )
                page.wait_for_timeout(3000)
                try:
                    page.wait_for_load_state("networkidle", timeout=15000)
                except Exception:
                    pass

            if "/login" in (page.url or "") or "captcha" in (page.url or ""):
                raise RuntimeError(f"会话无效：被重定向到 {page.url}")

            info = page.evaluate(_USER_INFO_JS)
            if info:
                xhs_user_id = (info.get("xhs_user_id") or "").strip()
                nickname = (info.get("nickname") or "").strip()
                fake_nicknames = {"xiaohongshu_user", "未命名用户", "小红书用户"}
                if xhs_user_id and nickname and nickname not in fake_nicknames:
                    logger.info(
                        f"[WORK] user_info OK from /explore: user_id={xhs_user_id}, nickname={nickname}"
                    )
                    return {
                        "xhs_user_id": xhs_user_id,
                        "nickname": nickname,
                        "avatar_url": (info.get("avatar_url") or "").strip(),
                        "red_id": info.get("red_id", ""),
                    }

            # 步骤 2：/explore 拿不到，尝试 /user/profile（可能触发风控）
            logger.info("[WORK] /explore no user info, trying /user/profile")
            page.goto(
                "https://www.xiaohongshu.com/user/profile",
                wait_until="domcontentloaded",
                timeout=30000,
            )
            page.wait_for_timeout(3000)
            try:
                page.wait_for_load_state("networkidle", timeout=15000)
            except Exception:
                pass

            if "/login" in (page.url or ""):
                raise RuntimeError("会话无效：被重定向到登录页")
            if "captcha" in (page.url or ""):
                raise RuntimeError("访问个人主页触发了小红书二次验证（风控）")

            info = page.evaluate(_USER_INFO_JS)
            if not info:
                raise RuntimeError("无法从页面提取用户信息")

            xhs_user_id = (info.get("xhs_user_id") or "").strip()
            nickname = (info.get("nickname") or "").strip()
            if not xhs_user_id or not nickname:
                raise RuntimeError(
                    f"用户信息不完整: user_id={xhs_user_id!r}, nickname={nickname!r}"
                )

            fake_nicknames = {"xiaohongshu_user", "未命名用户", "小红书用户"}
            if nickname in fake_nicknames:
                raise RuntimeError(f"检测到假昵称: {nickname!r}")

            logger.info(
                f"[WORK] user_info OK from /user/profile: user_id={xhs_user_id}, nickname={nickname}"
            )
            return {
                "xhs_user_id": xhs_user_id,
                "nickname": nickname,
                "avatar_url": (info.get("avatar_url") or "").strip(),
                "red_id": info.get("red_id", ""),
            }
        except RuntimeError:
            raise
        except Exception as e:
            logger.exception(f"[WORK] get_user_info failed: {e}")
            raise RuntimeError(f"获取用户信息失败: {e}")


def get_note_detail_via_session(session_id: str, note_id: str) -> dict:
    """用指定工作会话获取笔记详情。"""
    with _pw_lock:
        _cleanup_expired()  # 顺带清理过期会话
        with _sessions_lock:
            s = _sessions.get(session_id)
        if not s:
            raise RuntimeError("工作会话不存在或已过期")
        page = s["page"]
        try:
            page.goto(
                f"https://www.xiaohongshu.com/explore/{note_id}",
                wait_until="domcontentloaded",
                timeout=30000,
            )
            page.wait_for_timeout(3000)
            try:
                page.wait_for_load_state("networkidle", timeout=15000)
            except Exception:
                pass

            # 【临时诊断】先抓 page.url 和 __NEXT_DATA__ 状态，判断页面走向
            _debug = page.evaluate(
                """() => {
    const nd = document.getElementById('__NEXT_DATA__');
    const bodyText = (document.body?.innerText || '').substring(0, 300);
    return {
        url: location.href,
        title_tag: document.title,
        has_next_data: !!nd,
        next_data_len: nd ? (nd.textContent || '').length : 0,
        body_text_head: bodyText,
    };
}"""
            )
            logger.info(f"[WORK] note_detail debug for {note_id}: {_debug}")

            detail = page.evaluate(
                """(noteId) => {
    const nd = document.getElementById('__NEXT_DATA__');
    if (nd) {
        try {
            const d = JSON.parse(nd.textContent || '{}');
            const walk = (o, dp) => {
                if (!o || typeof o !== 'object' || dp > 5) return null;
                if (o.note_id || o.id) return o;
                for (const v of Object.values(o)) { const r = walk(v, dp+1); if (r) return r; }
                return null;
            };
            return walk(d.props?.pageProps, 0);
        } catch(e) {}
    }
    const titleEl = document.querySelector('h1, [class*=title]');
    const contentEl = document.querySelector('[class*=content], article, [class*=desc]');
    const imgs = Array.from(document.querySelectorAll('.carousel img, [class*=image] img, .swiper img'))
        .map(i => i.getAttribute('src') || '').filter(s => s.startsWith('http'));
    return {note_id: noteId, title: titleEl ? titleEl.textContent.trim() : '',
            content: contentEl ? contentEl.textContent.trim() : '', images: imgs, tags: []};
}""", note_id)
            if not detail:
                detail = {"note_id": note_id, "title": "", "content": "", "images": [], "tags": []}
            # 【临时诊断】附上调试字段（实施B时移除）
            detail["_debug"] = _debug
            return detail
        except Exception as e:
            logger.error(f"[WORK] get_note_detail failed: {e}")
            raise RuntimeError(f"获取笔记详情失败: {e}")


def close_work_session(session_id: str) -> dict:
    """关闭工作会话。"""
    with _pw_lock:
        _close_session(session_id)
    return {"success": True, "message": "工作会话已关闭"}


def _save_publish_diagnostic(page, tag: str) -> str:
    """发布失败时保存诊断信息：截图 + HTML + 按钮候选元素列表。

    保存到 backend/logs/publish_diag/{timestamp}_{tag}/，返回该目录路径。
    用于排查"未找到发布按钮"类问题：看截图确认页面实际状态、看 buttons.json
    确认页面上有哪些疑似按钮元素（class/text/位置）。
    """
    import os
    import time

    diag_root = os.path.join(
        os.path.dirname(__file__), "..", "..", "logs", "publish_diag"
    )
    os.makedirs(diag_root, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")
    save_dir = os.path.join(diag_root, f"{ts}_{tag}")
    os.makedirs(save_dir, exist_ok=True)

    # 1. 当前 URL
    try:
        with open(os.path.join(save_dir, "url.txt"), "w", encoding="utf-8") as f:
            f.write(page.url or "")
    except Exception:
        pass

    # 2. 整页截图（可见区域，避免 full_page 卡死）
    try:
        page.screenshot(path=os.path.join(save_dir, "page.png"), full_page=False)
    except Exception as e:
        logger.warning(f"diag screenshot failed: {e}")

    # 3. 页面 HTML（截断 200KB）
    try:
        html = page.content()
        with open(os.path.join(save_dir, "page.html"), "w", encoding="utf-8") as f:
            f.write(html[:200000])
    except Exception as e:
        logger.warning(f"diag html save failed: {e}")

    # 4. 扫描页面上所有疑似按钮元素（可见的），输出 class/text/位置
    #    诊断用：selector 尽量宽，便于排查"发布按钮缺失"类问题
    #    关键：包含 xhs-* 自定义元素（小红书改版后发布按钮是 Web Component）
    try:
        btn_info = page.evaluate(
            """() => {
                const out = [];
                const sels = 'xhs-publish-btn, xhs-publish-button, [class*="xhs-"], button, div[role="button"], [class*="btn"], [class*="publish"], [class*="submit"], [class*="footer"], [class*="bottom"], a[href]';
                document.querySelectorAll(sels).forEach(el => {
                    const r = el.getBoundingClientRect();
                    if (r.width <= 0 || r.height <= 0) return;
                    const style = window.getComputedStyle(el);
                    if (style.display === 'none' || style.visibility === 'hidden') return;
                    if (parseFloat(style.opacity) < 0.1) return;
                    const cls = el.className || '';
                    out.push({
                        tag: el.tagName,
                        text: (el.innerText || el.textContent || '').trim().slice(0, 60),
                        class: typeof cls === 'string' ? cls.slice(0, 100) : '',
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        disabled: el.disabled === true || el.getAttribute('aria-disabled') === 'true',
                    });
                });
                return out.slice(0, 200);
            }"""
        )
        with open(os.path.join(save_dir, "buttons.json"), "w", encoding="utf-8") as f:
            json.dump(btn_info, f, ensure_ascii=False, indent=2)
        logger.info(
            f"[WORK] publish diag: {len(btn_info)} button candidates scanned"
        )
    except Exception as e:
        logger.warning(f"diag buttons scan failed: {e}")

    logger.info(f"[WORK] publish diag saved to {save_dir}")
    return save_dir


def publish_note_via_session(
    session_id: str,
    title: str,
    content: str,
    images_b64: list[str],
) -> dict:
    """用指定工作会话发布小红书笔记。

    流程（单次发布，不重试，避免风控）：
    1. 打开创作者发布页 https://creator.xiaohongshu.com/publish/publish
    2. 上传图片（点击上传区域，逐张传 base64 临时文件）
    3. 填写标题（input 限制 20 字）
    4. 填写正文（contenteditable div）
    5. 点击发布按钮
    6. 等待跳转到发布成功页（URL 变化或成功提示出现）

    Args:
        session_id: 工作会话ID
        title: 笔记标题（小红书限制 20 字）
        content: 笔记正文
        images_b64: base64 编码的图片列表（PNG/JPG）

    Returns:
        {"success": bool, "post_id": str, "message": str}
    """
    import os
    import tempfile

    with _pw_lock:
        _cleanup_expired()  # 顺带清理过期会话
        with _sessions_lock:
            s = _sessions.get(session_id)
        if not s:
            raise RuntimeError("工作会话不存在或已过期")
        page = s["page"]

        # 临时文件列表（发布后清理）
        tmp_files: list[str] = []
        try:
            # ===== 1. 打开发布页 =====
            # 新版小红书发布页通过 URL 参数区分 tab：
            #   ?target=video  上传视频（默认，直接访问 /publish/publish 会被重定向到这里）
            #   ?target=image  上传图文（图片笔记）
            # 直接带 target=image 打开，避开重定向到 video tab。
            logger.info(f"[WORK] publish: opening creator page, title={title!r}")
            page.goto(
                "https://creator.xiaohongshu.com/publish/publish?from=menu&target=image",
                wait_until="domcontentloaded",
                timeout=20000,
            )
            page.wait_for_timeout(2000)
            try:
                page.wait_for_load_state("networkidle", timeout=8000)
            except Exception:
                pass

            # 检查是否真的在发布页（未登录会跳转登录页）
            current_url = page.url
            if "login" in current_url or "creator.xiaohongshu.com" not in current_url:
                raise RuntimeError(
                    f"未登录或页面跳转异常（当前URL: {current_url}），请重新登录"
                )

            # 用户确认流程（2026 实测）：
            #   落地页（无论 target=image/video）都是入口页，
            #   必须点左上角"发布笔记"入口 → popover 弹出 → 点"图片上传" → 才进入图文编辑器。
            #   编辑器内中间底部偏右有"发布"提交按钮。
            # 不再用 _is_in_image_editor() 短路（之前误判导致跳过 popover 流程）。
            logger.info(
                f"[WORK] publish: landing page (url={page.url}), "
                f"clicking 发布笔记 entry to open popover"
            )
            # 步骤 A：点左侧"发布笔记"入口按钮，弹出选项菜单
            entry_selectors = [
                'div.btn-wrapper:has-text("发布笔记")',
                'div.publish-video:has-text("发布笔记")',
                'div.btn-inner:has-text("发布笔记")',
                'span.btn-text:has-text("发布笔记")',
            ]
            entry_clicked = False
            for sel in entry_selectors:
                try:
                    btn = page.wait_for_selector(
                        sel, timeout=5000, state="visible"
                    )
                    if btn:
                        btn.scroll_into_view_if_needed(timeout=3000)
                        btn.click(timeout=5000)
                        entry_clicked = True
                        logger.info(
                            f"[WORK] publish: clicked 发布笔记 entry "
                            f"(selector={sel!r})"
                        )
                        page.wait_for_timeout(1000)
                        break
                except Exception:
                    continue

            if not entry_clicked:
                diag_path = _save_publish_diagnostic(page, "entry_btn_not_found")
                logger.error(
                    f"[WORK] publish: 发布笔记 entry button not found, "
                    f"url={page.url}, diag={diag_path}"
                )
                return {
                    "success": False,
                    "post_id": "",
                    "message": (
                        f"未找到「发布笔记」入口按钮（当前URL: {page.url}），"
                        f"发布中止。诊断信息已保存至 {diag_path}"
                    ),
                }

            # 步骤 B：在弹出的 popover 菜单里点"图片上传"
            # 用户确认：菜单选项文案是"图片上传"（不是"上传图文"）
            popover_item_selectors = [
                '.publish-video-popover :text("图片上传")',
                '.d-popover:has-text("图片上传") :text("图片上传")',
                'div.d-popover >> text="图片上传"',
                '[class*="popover"] :text("图片上传")',
                'div:has-text("图片上传"):not(.publish-video):not(.btn-wrapper)',
                # 兼容旧文案"上传图文"
                '.publish-video-popover :text("上传图文")',
                '.d-popover:has-text("上传图文") :text("上传图文")',
                '[class*="popover"] :text("上传图文")',
            ]
            image_item_clicked = False
            for sel in popover_item_selectors:
                try:
                    item = page.locator(sel).first
                    if item.count() > 0 and item.is_visible():
                        item.scroll_into_view_if_needed(timeout=3000)
                        item.click(timeout=5000)
                        page.wait_for_timeout(2000)
                        image_item_clicked = True
                        logger.info(
                            f"[WORK] publish: clicked 图片上传 in popover "
                            f"(selector={sel!r})"
                        )
                        break
                except Exception:
                    continue

            if not image_item_clicked:
                diag_path = _save_publish_diagnostic(page, "image_item_not_found")
                logger.error(
                    f"[WORK] publish: failed to click 图片上传 in popover, "
                    f"url={page.url}, diag={diag_path}"
                )
                return {
                    "success": False,
                    "post_id": "",
                    "message": (
                        f"在弹出菜单中未找到「图片上传」选项（当前URL: {page.url}），"
                        f"发布中止。诊断信息已保存至 {diag_path}"
                    ),
                }

            # ===== 2. 上传图片 =====
            if images_b64:
                # 找到图片上传 input（type=file 且 accept 包含 image）
                # 小红书发布页有多个 file input：第一个是视频上传（accept=.mp4,.mov...），
                # 图片上传是后面的 input（accept 含 image/* 或 .png,.jpg...）。
                # 用 .first 会选错成视频 input，导致 set_input_files 报错。
                file_input = page.locator(
                    'input[type="file"][accept*="image" i], '
                    'input[type="file"][accept*=".png" i], '
                    'input[type="file"][accept*=".jpg" i]'
                ).first
                if file_input.count() == 0:
                    # 兜底：排除视频 input 后取第一个
                    file_input = page.locator(
                        'input[type="file"]:not([accept*=".mp4" i]):not([accept*="video" i])'
                    ).first
                if file_input.count() == 0:
                    raise RuntimeError("找不到图片上传入口，发布页结构可能已变更")

                # 把 base64 图片写入临时文件（Playwright set_input_files 需要文件路径）
                # 用 secrets.token_urlsafe 加随机后缀，避免并发发布互相覆盖
                for i, b64 in enumerate(images_b64[:9]):  # 小红书最多 9 张图
                    try:
                        # 去掉可能的 data:image/...;base64, 前缀
                        if "," in b64 and b64.startswith("data:"):
                            b64 = b64.split(",", 1)[1]
                        img_bytes = base64.b64decode(b64)
                        # 根据魔数判断扩展名
                        ext = ".png"
                        if img_bytes[:3] == b"\xff\xd8\xff":
                            ext = ".jpg"
                        # 加随机后缀避免并发发布冲突
                        rand_suffix = secrets.token_urlsafe(6)
                        tmp_path = os.path.join(
                            tempfile.gettempdir(),
                            f"xhs_publish_{i}_{rand_suffix}{ext}",
                        )
                        with open(tmp_path, "wb") as f:
                            f.write(img_bytes)
                        tmp_files.append(tmp_path)
                    except Exception as e:
                        logger.warning(f"[WORK] publish: decode image {i} failed: {e}")

                if tmp_files:
                    # 图片 input 支持 multiple，单次传入所有文件
                    file_input.set_input_files(tmp_files)
                    logger.info(f"[WORK] publish: uploaded {len(tmp_files)} images")
                    # 等待图片上传完成（上传后会出现图片预览）
                    page.wait_for_timeout(2000)

            # ===== 3. 填写标题 =====
            # 小红书标题 input（限制 20 字）
            title_str = (title or "").strip()[:20]
            try:
                title_input = page.locator(
                    'input[placeholder*="标题"], input[placeholder*="title"], '
                    'div[contenteditable][class*="title"]'
                ).first
                if title_input.count() > 0:
                    title_input.click()
                    title_input.fill(title_str)
                    logger.info(f"[WORK] publish: title filled: {title_str!r}")
                else:
                    logger.warning("[WORK] publish: title input not found")
            except Exception as e:
                logger.warning(f"[WORK] publish: fill title failed: {e}")

            # ===== 4. 填写正文 =====
            content_str = (content or "").strip()
            try:
                # 正文编辑器：新版小红书用 ProseMirror (tiptap) 富文本编辑器
                # class="tiptap ProseMirror", role="textbox", contenteditable="true"
                # 旧版是 div[contenteditable][class*="content"] 或 #post-textarea
                content_div = page.locator(
                    'div[contenteditable="true"].ProseMirror, '
                    'div[contenteditable="true"][class*="tiptap"], '
                    'div[role="textbox"][contenteditable="true"], '
                    'div[contenteditable="true"][class*="content"], '
                    'div[contenteditable="true"][class*="desc"], '
                    '#post-textarea'
                ).first
                if content_div.count() > 0:
                    content_div.click()
                    # ProseMirror/tiptap 富文本编辑器用 fill() 不触发 input 事件，
                    # 必须用 type() 模拟键盘输入（delay=0 快速输入）。
                    # 旧版 #post-textarea 等普通元素 fill() 也能用，type() 兼容两者。
                    content_div.type(content_str, delay=0)
                    logger.info(
                        f"[WORK] publish: content filled ({len(content_str)} chars)"
                    )
                else:
                    logger.warning("[WORK] publish: content div not found")
            except Exception as e:
                logger.warning(f"[WORK] publish: fill content failed: {e}")

            # ===== 5. 半自动发布：不点击，保留页面供用户手动点「发布」 =====
            # 排查结论：xhs-publish-btn 是小红书原生 JS 直接 createElement 插入 DOM
            # 的孤立节点，Vue vnode 树里没渲染它（xhsHosts=[]），没有 Vue 实例、没
            # 有事件绑定——Playwright 点击它永远不触发发布。
            # 改半自动：标题/正文/图片已由前几步填好，保留浏览器窗口让用户手动点。
            page.wait_for_timeout(1500)
            logger.info(
                "[WORK] publish: content filled, awaiting manual publish click "
                "(半自动：请用户在浏览器窗口手动点击「发布」按钮)"
            )
            diag_path = _save_publish_diagnostic(page, "awaiting_manual_publish")
            return {
                "success": True,
                "post_id": "",
                "message": (
                    "内容已填好（标题/正文/图片），请在弹出的浏览器窗口手动点击"
                    "「发布」按钮完成发布。页面已停留在编辑器，未做任何点击。"
                    f"诊断截图已保存至 {diag_path}"
                ),
            }

        except Exception as e:
            logger.exception(f"[WORK] publish failed: {e}")
            raise RuntimeError(f"发布失败: {e}")
        finally:
            # 清理临时图片文件
            for tmp in tmp_files:
                try:
                    os.remove(tmp)
                except Exception:
                    pass


def check_publish_result(session_id: str) -> dict:
    """回查半自动发布结果。

    半自动模式下 publish 填好内容后不点击，由用户在浏览器窗口手动点「发布」。
    前端轮询此接口判断发布是否完成。

    判断依据：
    - URL 离开 publish/publish 且非 login → published（发布成功，已跳转）
    - URL 含 login → failed（登录态失效）
    - URL 仍在 publish/publish → 检查页面错误提示：
        有错误 → failed；无错误 → pending（等待用户点击）

    Returns:
        {"status": "pending"|"published"|"failed"|"session_invalid",
         "url": str, "message": str}
    """
    with _pw_lock:
        with _sessions_lock:
            s = _sessions.get(session_id)
        if not s:
            return {
                "status": "session_invalid",
                "url": "",
                "message": "工作会话不存在或已过期，请重新创建发布会话",
            }
        page = s["page"]
        try:
            url = page.url or ""
        except Exception as e:
            return {
                "status": "session_invalid",
                "url": "",
                "message": f"会话页面已失效: {e}",
            }

        # URL 判断
        if "login" in url:
            return {
                "status": "failed",
                "url": url,
                "message": "登录态已失效，页面跳转到登录页，请重新登录小红书账号",
            }
        if "publish/publish" not in url and "creator.xiaohongshu.com" in url:
            # 已离开发布编辑器，跳到管理页/成功页
            return {
                "status": "published",
                "url": url,
                "message": f"发布成功，页面已跳转至 {url}",
            }

        # 仍在编辑器：检查页面错误提示
        try:
            err_hint = page.evaluate(
                r"""() => {
                    const hints = [
                        '请上传图片', '请至少上传', '图片上传中',
                        '请填写标题', '标题不能为空', '请输入正文',
                        '正文不能为空', '发布失败', '操作频繁',
                        '含有违规', '审核未通过', '发布中'
                    ];
                    const body = document.body?.innerText || '';
                    for (const h of hints) {
                        if (body.includes(h)) return h;
                    }
                    return '';
                }"""
            ) or ""
        except Exception:
            err_hint = ""

        # "发布中" 算 pending（用户点了发布，正在上传/提交）
        if err_hint and err_hint != "发布中":
            return {
                "status": "failed",
                "url": url,
                "message": f"发布可能失败，页面提示: {err_hint}",
            }

        return {
            "status": "pending",
            "url": url,
            "message": (
                "等待用户在浏览器窗口手动点击「发布」按钮"
                if not err_hint
                else f"发布进行中: {err_hint}"
            ),
        }


class Handler(BaseHTTPRequestHandler):
    def _send_json(self, code: int, payload: dict):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        try:
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except ConnectionAbortedError:
            logger.warning(f"_send_json: client disconnected before response sent ({len(body)} bytes)")
        except BrokenPipeError:
            logger.warning(f"_send_json: broken pipe, client gone ({len(body)} bytes)")
        except OSError:
            logger.warning(f"_send_json: OS error, client gone ({len(body)} bytes)")

    def _read_body(self) -> dict:
        length = int(self.headers.get("Content-Length", 0))
        if length == 0:
            return {}
        raw = self.rfile.read(length)
        try:
            return json.loads(raw) if raw else {}
        except Exception:
            return {}

    def do_GET(self):
        if self.path == "/health":
            with _sessions_lock:
                count = len(_sessions)
            self._send_json(200, {"status": "ok", "sessions": count})
            return
        self._send_json(404, {"error": "not found"})

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path
        try:
            if path == "/qrcode":
                result = gen_qrcode()
                self._send_json(200, result)
                return
            if path.startswith("/status/"):
                qr_id = path[len("/status/"):]
                with _sessions_lock:
                    s = _sessions.get(qr_id)
                if not s:
                    self._send_json(200, {"status": "expired", "message": "会话不存在或已过期"})
                else:
                    result = {"status": s["status"], "message": s.get("message", "")}
                    if s.get("qrcode_base64"):
                        result["qrcode_base64"] = s["qrcode_base64"]
                    self._send_json(200, result)
                return
            if path.startswith("/status_detect/"):
                qr_id = path[len("/status_detect/"):]
                result = check_status(qr_id)
                self._send_json(200, result)
                return
            if path.startswith("/user_info/"):
                qr_id = path[len("/user_info/"):]
                try:
                    result = fetch_user_info(qr_id)
                    self._send_json(200, {"success": True, "data": result})
                except RuntimeError as e:
                    self._send_json(200, {"success": False, "message": str(e)})
                return
            if path.startswith("/cookies/"):
                qr_id = path[len("/cookies/"):]
                try:
                    result = export_cookies(qr_id)
                    self._send_json(200, {"success": True, "data": result})
                except RuntimeError as e:
                    self._send_json(200, {"success": False, "message": str(e)})
                return
            if path.startswith("/close/"):
                qr_id = path[len("/close/"):]
                result = close_session(qr_id)
                self._send_json(200, result)
                return
            # === 工作会话接口 ===
            if path == "/session/create":
                body = self._read_body()
                cookies = body.get("cookies", [])
                if not cookies:
                    self._send_json(400, {"error": "cookies 不能为空"})
                    return
                try:
                    result = create_work_session(cookies)
                    self._send_json(200, {"success": True, "data": result})
                except RuntimeError as e:
                    self._send_json(200, {"success": False, "message": str(e)})
                return
            if path.startswith("/search/"):
                session_id = path[len("/search/"):]
                body = self._read_body()
                keyword = body.get("keyword", "")
                try:
                    limit = int(body.get("limit", 20))
                except (TypeError, ValueError):
                    limit = 20
                # clamp 到合理范围，避免负数或超大值导致异常
                limit = max(1, min(limit, 100))
                if not keyword:
                    self._send_json(400, {"error": "keyword 不能为空"})
                    return
                try:
                    result = search_notes(session_id, keyword, limit)
                    self._send_json(200, {"success": True, "data": result})
                except RuntimeError as e:
                    self._send_json(200, {"success": False, "message": str(e)})
                return
            if path.startswith("/search_with_details/"):
                session_id = path[len("/search_with_details/"):]
                body = self._read_body()
                keyword = body.get("keyword", "")
                try:
                    limit = int(body.get("limit", 8))
                except (TypeError, ValueError):
                    limit = 8
                try:
                    detail_top_n = int(body.get("detail_top_n", 5))
                except (TypeError, ValueError):
                    detail_top_n = 5
                limit = max(1, min(limit, 30))
                detail_top_n = max(0, min(detail_top_n, limit))
                if not keyword:
                    self._send_json(400, {"error": "keyword 不能为空"})
                    return
                try:
                    result = search_with_details(session_id, keyword, limit, detail_top_n)
                    self._send_json(200, {"success": True, "data": result})
                except RuntimeError as e:
                    self._send_json(200, {"success": False, "message": str(e)})
                return
            if path.startswith("/user_info_current/"):
                session_id = path[len("/user_info_current/"):]
                try:
                    result = get_current_user_info_via_session(session_id)
                    self._send_json(200, {"success": True, "data": result})
                except RuntimeError as e:
                    self._send_json(200, {"success": False, "message": str(e)})
                return
            if path.startswith("/note_detail/"):
                session_id = path[len("/note_detail/"):]
                body = self._read_body()
                note_id = body.get("note_id", "")
                if not note_id:
                    self._send_json(400, {"error": "note_id 不能为空"})
                    return
                try:
                    result = get_note_detail_via_session(session_id, note_id)
                    self._send_json(200, {"success": True, "data": result})
                except RuntimeError as e:
                    self._send_json(200, {"success": False, "message": str(e)})
                return
            if path.startswith("/publish/"):
                # 子路由：/publish/{session_id} 发起发布
                #         /publish/{session_id}/check 回查发布结果
                rest = path[len("/publish/"):]
                if rest.endswith("/check"):
                    session_id = rest[: -len("/check")]
                    try:
                        result = check_publish_result(session_id)
                        self._send_json(200, {"success": True, "data": result})
                    except RuntimeError as e:
                        self._send_json(200, {"success": False, "message": str(e)})
                    return
                session_id = rest
                body = self._read_body()
                title = body.get("title", "")
                content = body.get("content", "")
                images_b64 = body.get("images_b64", [])
                if not title and not content:
                    self._send_json(400, {"error": "title 和 content 不能同时为空"})
                    return
                try:
                    result = publish_note_via_session(
                        session_id, title, content, images_b64
                    )
                    self._send_json(200, {"success": True, "data": result})
                except RuntimeError as e:
                    self._send_json(200, {"success": False, "message": str(e)})
                return
            if path.startswith("/debug_eval/"):
                session_id = path[len("/debug_eval/"):]
                body = self._read_body()
                js = body.get("js", "")
                if not js:
                    self._send_json(400, {"error": "js 不能为空"})
                    return
                try:
                    with _pw_lock:
                        with _sessions_lock:
                            s = _sessions.get(session_id)
                        if not s:
                            raise RuntimeError("工作会话不存在或已过期")
                        result = s["page"].evaluate(js)
                    self._send_json(200, {"success": True, "data": result})
                except Exception as e:
                    self._send_json(200, {"success": False, "message": str(e)})
                return
            self._send_json(404, {"error": "not found"})
        except Exception as e:
            logger.exception(f"handler error: {path}")
            self._send_json(500, {"error": str(e)})

    def do_DELETE(self):
        parsed = urlparse(self.path)
        path = parsed.path
        try:
            if path.startswith("/session/"):
                session_id = path[len("/session/"):]
                result = close_work_session(session_id)
                self._send_json(200, result)
                return
            self._send_json(404, {"error": "not found"})
        except Exception as e:
            logger.exception(f"handler error: {path}")
            self._send_json(500, {"error": str(e)})

    def log_message(self, *args):
        # 静默默认访问日志，用 logger 控制输出
        pass


def main():
    import select as _select

    port = int(os.environ.get("QR_WORKER_PORT", "") or (sys.argv[1] if len(sys.argv) > 1 else 9010))
    # 启动时预热浏览器（避免首次请求慢）
    logger.info(f"Preheating browser...")
    with _pw_lock:
        _ensure_browser()
    # 必须用单线程 HTTPServer：sync_playwright 基于 greenlet，不能跨线程切换。
    # ThreadingHTTPServer 会导致 "Cannot switch to a different thread" 错误。
    # 所有 playwright 操作已用 _pw_lock 串行化，单线程不会让性能更差。
    server = HTTPServer(("127.0.0.1", port), Handler)
    logger.info(f"QR Worker listening on http://127.0.0.1:{port}")
    logger.info(
        "Endpoints: /qrcode, /status/{qr_id}, /status_detect/{qr_id}, "
        "/user_info/{qr_id}, "
        "/cookies/{qr_id}, /close/{qr_id}, /health, "
        "/session/create, /search/{sess}, /user_info_current/{sess}, "
        "/note_detail/{sess}, DELETE /session/{sess}"
    )
    try:
        while True:
            readable, _, _ = _select.select([server.socket], [], [], 0.05)
            if readable:
                server.handle_request()
            else:
                _background_detect_pending()
    except KeyboardInterrupt:
        logger.info("Shutting down...")
    finally:
        with _pw_lock:
            with _sessions_lock:
                for qr_id in list(_sessions.keys()):
                    _close_session(qr_id)
            if _browser:
                _browser.close()
            if _pw:
                _pw.stop()


if __name__ == "__main__":
    main()