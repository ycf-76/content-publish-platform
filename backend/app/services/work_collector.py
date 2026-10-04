"""我的作品数据采集服务。

采集降级链：
1. page_ssr_parse：直接 HTTP GET 页面，解析 __INITIAL_STATE__（最轻量，无需 cookies/浏览器）
2. link_grabber：link-grabber MCP server（支持小红书/抖音/微信/Instagram，需 uv + link-grabber 已安装）
3. xhs_web_api：小红书 Web API 请求（需 cookies，更稳定但更重）
4. mcp_note_detail：MCP 浏览器 get_note_detail（最重，兜底）
5. creator_center_csv：创作者中心 CSV 导出（需用户手动导出）
"""
from __future__ import annotations

import asyncio
import csv
import io
import json
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

COLLECTION_FALLBACK_CHAIN = [
    "scrapling_fetcher",
    "page_ssr_parse",
    "link_grabber",
    "xhs_web_api",
    "mcp_note_detail",
    "creator_center_csv",
]

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

_collect_errors: list[str] = []


def get_last_collect_errors() -> list[str]:
    """获取最近一次采集的各降级环节失败原因。"""
    return list(_collect_errors)

# ──────────────────────────────────────────────
# 平台检测 & 链接解析
# ──────────────────────────────────────────────

PLATFORM_PATTERNS: dict[str, list[re.Pattern]] = {
    "xiaohongshu": [
        re.compile(r'(?:www\.)?xiaohongshu\.com'),
        re.compile(r'xhslink\.(?:com|cn)'),
    ],
    "douyin": [
        re.compile(r'(?:www\.)?douyin\.com'),
        re.compile(r'v\.douyin\.com'),
        re.compile(r'(?:www\.)?iesdouyin\.com'),
    ],
    "wechat_mp": [
        re.compile(r'mp\.weixin\.qq\.com'),
        re.compile(r'(?:www\.)?weixin\.qq\.com'),
    ],
    "bilibili": [
        re.compile(r'(?:www\.)?bilibili\.com'),
        re.compile(r'b23\.tv'),
    ],
    "instagram": [
        re.compile(r'(?:www\.)?instagram\.com'),
    ],
    "threads": [
        re.compile(r'(?:www\.)?threads\.net'),
    ],
}


def detect_platform(url: str) -> str:
    """从 URL 自动检测平台。

    Returns:
        平台标识：xiaohongshu / douyin / wechat_mp / bilibili / instagram / threads / unknown
    """
    url = url.strip()
    for platform, patterns in PLATFORM_PATTERNS.items():
        for pat in patterns:
            if pat.search(url):
                return platform
    return "unknown"


def extract_content_id_from_url(url: str, platform: str) -> str | None:
    """从 URL 中提取内容 ID（各平台格式不同）。

    Args:
        url: 原始 URL 或重定向后的真实 URL
        platform: 平台标识

    Returns:
        内容 ID（小红书 note_id / 抖音 aweme_id / B站 bvid 等），或 None
    """
    url = url.strip()

    if platform == "xiaohongshu":
        return _extract_xhs_note_id(url)
    elif platform == "douyin":
        return _extract_douyin_aweme_id(url)
    elif platform == "bilibili":
        return _extract_bilibili_bvid(url)
    elif platform == "wechat_mp":
        return _extract_wechat_msgid(url)
    elif platform in ("instagram", "threads"):
        return _extract_instagram_shortcode(url, platform)

    return None


def _extract_xhs_note_id(url: str) -> str | None:
    """从小红书 URL 中提取 note_id。"""
    url = url.strip()

    xhs_url_m = re.search(r'https?://(?:www\.)?xiaohongshu\.com/\S+', url)
    if xhs_url_m:
        url = xhs_url_m.group(0)
        url = re.sub(r'[^\w%&=?./:_-].*$', '', url)

    if re.match(r'^[0-9a-fA-F]{24}$', url):
        return url

    patterns = [
        r'xiaohongshu\.com/explore/([0-9a-fA-F]{24})',
        r'xiaohongshu\.com/discovery/item/([0-9a-fA-F]{24})',
        r'xiaohongshu\.com/user/profile/[0-9a-fA-F]+/([0-9a-fA-F]{24})',
        r'xiaohongshu\.com/note/([0-9a-fA-F]{24})',
        r'/note/([0-9a-fA-F]{24})',
    ]
    for pattern in patterns:
        m = re.search(pattern, url)
        if m:
            return m.group(1)
    return None


def _extract_douyin_aweme_id(url: str) -> str | None:
    """从抖音 URL 中提取 aweme_id（视频 ID）。

    支持格式：
    - https://www.douyin.com/video/7xxxxxxxxxxxxx
    - https://www.douyin.com/note/7xxxxxxxxxxxxx（图文）
    - https://v.douyin.com/xxxxxx/（短链接）
    """
    patterns = [
        r'douyin\.com/video/(\d+)',
        r'douyin\.com/note/(\d+)',
        r'douyin\.com/user/\w+\?previous_page=web_code_link.*?modal_id=(\d+)',
        r'[?&]modal_id=(\d+)',
    ]
    for pattern in patterns:
        m = re.search(pattern, url)
        if m:
            return m.group(1)
    return None


def _extract_bilibili_bvid(url: str) -> str | None:
    """从 B 站 URL 中提取 bvid。

    支持格式：
    - https://www.bilibili.com/video/BV1xxxxxxxx
    - https://www.bilibili.com/video/avxxxxxxxx
    - https://b23.tv/BV1xxxxxxxx（短链接）
    """
    bv_m = re.search(r'(BV1[\w]+)', url)
    if bv_m:
        return bv_m.group(1)
    av_m = re.search(r'/av(\d+)', url)
    if av_m:
        return f"av{av_m.group(1)}"
    return None


def _extract_wechat_msgid(url: str) -> str | None:
    """从微信公众号文章 URL 中提取 msgid（文章唯一标识）。

    格式：https://mp.weixin.qq.com/s?__biz=xxx&mid=xxx&idx=1&sn=xxx
    用 biz+mid+idx 组合作为唯一标识。
    """
    biz_m = re.search(r'__biz=([^&]+)', url)
    mid_m = re.search(r'&mid=(\d+)', url)
    idx_m = re.search(r'&idx=(\d+)', url)
    if biz_m and mid_m:
        biz = biz_m.group(1)
        mid = mid_m.group(1)
        idx = idx_m.group(1) if idx_m else "1"
        return f"wx_{biz}_{mid}_{idx}"
    return None


def _extract_instagram_shortcode(url: str, platform: str) -> str | None:
    """从 Instagram/Threads URL 中提取 shortcode。

    格式：
    - https://www.instagram.com/p/Cxxxxxxxx/
    - https://www.instagram.com/reel/Cxxxxxxxx/
    - https://www.threads.net/post/Cxxxxxxxx/
    """
    domain = "instagram" if platform == "instagram" else "threads"
    if platform == "instagram":
        m = re.search(r'instagram\.com/(?:p|reel|tv)/([\w-]+)', url)
    else:
        m = re.search(r'threads\.net/(?:post|p)/([\w-]+)', url)
    if m:
        return m.group(1)
    return None


# ──────────────────────────────────────────────
# 短链接解析（各平台）
# ──────────────────────────────────────────────

SHORT_URL_DOMAINS = {
    "xhslink.com": "xiaohongshu",
    "xhslink.cn": "xiaohongshu",
    "v.douyin.com": "douyin",
    "b23.tv": "bilibili",
}


def is_short_url(url: str) -> bool:
    """判断是否短链接。"""
    for domain in SHORT_URL_DOMAINS:
        if domain in url:
            return True
    return False


def extract_xsec_token(url: str) -> str | None:
    """从 URL 中提取 xsec_token 参数。

    手机分享链接通常带 xsec_token，有效期约 5 分钟。
    带 token 请求 SSR 页面可以拿到笔记数据。
    """
    m = re.search(r'[?&]xsec_token=([^&\s]+)', url)
    if m:
        return m.group(1)
    return None


def extract_xsec_source(url: str) -> str | None:
    """从 URL 中提取 xsec_source 参数。"""
    m = re.search(r'[?&]xsec_source=([^&\s]+)', url)
    if m:
        return m.group(1)
    return None


def _clean_share_text(raw: str) -> str:
    """从分享口令混合文本中提取纯 URL。

    抖音分享格式：https://v.douyin.com/xxx/ 复制此链接，打开抖音搜索...
    小红书分享格式：https://xhslink.cn/xxx 复制此链接，打开小红书查看...
    通用格式：URL 后面跟空格和口令文字
    """
    raw = raw.strip()
    url_pattern = re.compile(r'(https?://[^\s<>"{}|\\^`\[\]]+)')
    m = url_pattern.search(raw)
    if m:
        url = m.group(1)
        if url.endswith('/'):
            url = url
        return url
    return raw


async def collect_from_url(note_url: str, platform: str | None = None) -> dict | None:
    """通过 URL 采集内容数据（多平台）。

    自动检测平台，按降级链采集：
    - 小红书：SSR(xsec_token) → SSR(cookies) → link-grabber → Web API → MCP
    - 抖音/B站/微信/Instagram：link-grabber → SSR → 通用 HTTP 解析

    Returns:
        成功时返回数据 dict（含 source 字段），失败时返回 None。
        调用方可通过 get_last_collect_errors() 获取各降级环的失败原因。
    """
    _collect_errors.clear()

    note_url = _clean_share_text(note_url)

    # 1. 自动检测平台
    if not platform or platform == "auto":
        platform = detect_platform(note_url)
    if platform == "unknown":
        # 短链接可能检测不到，先尝试重定向
        if is_short_url(note_url):
            real_url = await _resolve_short_url(note_url)
            if real_url:
                platform = detect_platform(real_url)
        if platform == "unknown":
            msg = f"无法识别链接所属平台，请确认链接格式正确（支持小红书/抖音/B站/微信/Instagram）"
            logger.warning(f"[work_collector] {msg}: {note_url}")
            _collect_errors.append(msg)
            return None

    logger.info(f"[work_collector] Detected platform: {platform}")

    # 2. 提取平台特有参数
    xsec_token = extract_xsec_token(note_url)
    xsec_source = extract_xsec_source(note_url)

    # 3. 提取内容 ID
    content_id = None

    # 短链接优先走 HTTP 重定向解析
    if is_short_url(note_url):
        real_url = await _resolve_short_url(note_url)
        if real_url:
            content_id = extract_content_id_from_url(real_url, platform)
            if not xsec_token:
                xsec_token = extract_xsec_token(real_url)
            if not xsec_source:
                xsec_source = extract_xsec_source(real_url)

        # 抖音短链接特殊处理：重定向到首页时，尝试从短链接本身提取ID
        if not content_id and platform == "douyin":
            content_id = await _extract_douyin_id_from_short_url(note_url)

    # 非短链接，直接提取
    if not content_id:
        content_id = extract_content_id_from_url(note_url, platform)

    if not content_id:
        msg = f"无法从链接中提取内容ID（platform={platform}），请确认链接格式正确"
        logger.warning(f"[work_collector] {msg}: {note_url}")
        _collect_errors.append(msg)
        return None

    # 4. 按平台分发采集
    if platform == "xiaohongshu":
        return await _collect_xhs(content_id, note_url, xsec_token, xsec_source)
    elif platform == "douyin":
        return await _collect_douyin(content_id, note_url)
    elif platform == "bilibili":
        return await _collect_bilibili(content_id, note_url)
    elif platform == "wechat_mp":
        return await _collect_wechat(content_id, note_url)
    elif platform in ("instagram", "threads"):
        return await _collect_instagram(content_id, note_url, platform)
    else:
        # 未知平台，尝试 link-grabber 兜底
        return await _collect_via_link_grabber(note_url, platform)


async def _collect_xhs(note_id: str, note_url: str, xsec_token: str | None, xsec_source: str | None) -> dict | None:
    """小红书采集降级链。"""
    platform = "xiaohongshu"

    # 降级链 0：Scrapling StealthyFetcher（反检测浏览器，需 scrapling 已安装）
    try:
        stats = await _collect_via_scrapling(note_id, note_url, platform)
        if stats:
            stats["source"] = "scrapling_fetcher"
            return stats
        _collect_errors.append("Scrapling：未安装或采集失败（pip install scrapling）")
    except Exception as e:
        _collect_errors.append(f"Scrapling失败：{e}")
        logger.warning(f"[work_collector] Scrapling fetcher failed for {note_id}: {e}")

    # 降级链 1：SSR 解析（带 xsec_token / cookies / 裸请求）
    try:
        stats = await _collect_via_ssr(note_id, platform, xsec_token=xsec_token, xsec_source=xsec_source)
        if stats:
            stats["source"] = "page_ssr_parse"
            return stats
        _collect_errors.append("SSR解析：页面数据为空（需要xsec_token或登录cookies）")
    except Exception as e:
        _collect_errors.append(f"SSR解析失败：{e}")
        logger.warning(f"[work_collector] SSR parse failed for {note_id}: {e}")

    # 降级链 2：link-grabber MCP
    try:
        stats = await _collect_via_link_grabber(note_url, platform)
        if stats:
            stats["source"] = "link_grabber"
            return stats
        _collect_errors.append("link-grabber：未安装或不可用（需安装Phat-Po/link-grabber）")
    except Exception as e:
        _collect_errors.append(f"link-grabber失败：{e}")
        logger.warning(f"[work_collector] link-grabber failed for {note_id}: {e}")

    # 降级链 3：XHS Web API
    try:
        stats = await _collect_via_web_api(note_id, platform)
        if stats:
            stats["source"] = "xhs_web_api"
            return stats
        _collect_errors.append("Web API：无可用cookies（需浏览器扩展已连接且登录小红书）")
    except Exception as e:
        _collect_errors.append(f"Web API失败：{e}")
        logger.warning(f"[work_collector] Web API collect failed for {note_id}: {e}")

    # 降级链 4：MCP get_note_detail
    try:
        stats = await _collect_via_mcp(note_id, platform)
        if stats:
            stats["source"] = "mcp_note_detail"
            return stats
        _collect_errors.append("MCP浏览器扩展：未连接或未登录")
    except Exception as e:
        _collect_errors.append(f"MCP采集失败：{e}")
        logger.warning(f"[work_collector] MCP collect failed for {note_id}: {e}")

    logger.info(f"[work_collector] All XHS collect methods failed for {note_id}")
    return None


async def _collect_douyin(aweme_id: str, note_url: str) -> dict | None:
    """抖音采集降级链。"""
    platform = "douyin"

    # 降级链 1：抖音 Web API（含4种策略：API/旧API/分享页/页面SSR）
    try:
        stats = await _collect_douyin_via_api(aweme_id, platform)
        if stats:
            stats["source"] = "douyin_web_api"
            return stats
    except Exception as e:
        _collect_errors.append(f"抖音API失败：{e}")
        logger.warning(f"[work_collector] Douyin API failed for {aweme_id}: {e}")

    # 降级链 2：link-grabber（支持视频+语音转录）
    try:
        stats = await _collect_via_link_grabber(note_url, platform)
        if stats:
            stats["source"] = "link_grabber"
            return stats
    except Exception as e:
        _collect_errors.append(f"link-grabber失败：{e}")
        logger.warning(f"[work_collector] link-grabber failed for douyin {aweme_id}: {e}")

    logger.info(f"[work_collector] All Douyin collect methods failed for {aweme_id}")
    return None


async def _collect_bilibili(bvid: str, note_url: str) -> dict | None:
    """B 站采集降级链。"""
    platform = "bilibili"

    # 降级链 1：B 站 Web API（公开，无需登录）
    try:
        stats = await _collect_bilibili_via_api(bvid, platform)
        if stats:
            stats["source"] = "bilibili_api"
            return stats
    except Exception as e:
        logger.warning(f"[work_collector] Bilibili API failed for {bvid}: {e}")

    # 降级链 2：link-grabber
    try:
        stats = await _collect_via_link_grabber(note_url, platform)
        if stats:
            stats["source"] = "link_grabber"
            return stats
    except Exception as e:
        logger.warning(f"[work_collector] link-grabber failed for bilibili {bvid}: {e}")

    logger.info(f"[work_collector] All Bilibili collect methods failed for {bvid}")
    return None


async def _collect_wechat(content_id: str, note_url: str) -> dict | None:
    """微信公众号采集降级链。"""
    platform = "wechat_mp"

    # 降级链 1：link-grabber（微信首选）
    try:
        stats = await _collect_via_link_grabber(note_url, platform)
        if stats:
            stats["source"] = "link_grabber"
            return stats
    except Exception as e:
        logger.warning(f"[work_collector] link-grabber failed for wechat: {e}")

    # 降级链 2：HTTP 直接解析微信文章 HTML
    try:
        stats = await _collect_wechat_via_http(note_url, platform)
        if stats:
            stats["source"] = "page_http_parse"
            return stats
    except Exception as e:
        logger.warning(f"[work_collector] WeChat HTTP parse failed: {e}")

    logger.info(f"[work_collector] All WeChat collect methods failed for {content_id}")
    return None


async def _collect_instagram(content_id: str, note_url: str, platform: str) -> dict | None:
    """Instagram/Threads 采集降级链。"""
    # link-grabber 是唯一可行方案（需登录态）
    try:
        stats = await _collect_via_link_grabber(note_url, platform)
        if stats:
            stats["source"] = "link_grabber"
            return stats
    except Exception as e:
        logger.warning(f"[work_collector] link-grabber failed for {platform}: {e}")

    logger.info(f"[work_collector] All {platform} collect methods failed for {content_id}")
    return None


async def _resolve_short_url(url: str) -> str | None:
    """解析短链接，跟随重定向拿到真实 URL。

    支持：xhslink.com/cn / v.douyin.com / b23.tv
    抖音短链接需要移动端 UA 才能正确重定向。
    """
    if not is_short_url(url):
        return None
    import httpx

    domain = ""
    for d in SHORT_URL_DOMAINS:
        if d in url:
            domain = d
            break

    if "douyin" in domain:
        ua = (
            "Mozilla/5.0 (Linux; Android 13; Pixel 7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/131.0.0.0 Mobile Safari/537.36"
        )
    else:
        ua = _UA

    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            resp = await client.get(url, headers={
                "User-Agent": ua,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            })
            real_url = str(resp.url)

            if "douyin" in domain:
                html = resp.text
                # 抖音短链接302到首页时，尝试从HTML中提取视频ID
                if real_url.rstrip("/") == "https://www.douyin.com":
                    aweme_id = _extract_douyin_aweme_id_from_html(html)
                    if aweme_id:
                        return f"https://www.douyin.com/video/{aweme_id}"

                # 抖音短链接有时重定向到中间页而非最终页
                if "douyin.com" in real_url:
                    meta_refresh = re.search(r'content="0;url=([^"]+)"', html)
                    if meta_refresh:
                        redirect_url = meta_refresh.group(1)
                        if "douyin.com" in redirect_url:
                            return redirect_url
                    js_redirect = re.search(r"location\.(?:href|replace)\s*[=\(]\s*['\"]([^'\"]+)['\"]", html)
                    if js_redirect:
                        redirect_url = js_redirect.group(1)
                        if "douyin.com" in redirect_url:
                            return redirect_url

            return real_url
    except Exception as e:
        logger.warning(f"[work_collector] Short URL resolve failed: {e}")
        return None


async def _extract_douyin_id_from_short_url(short_url: str) -> str | None:
    """抖音短链接重定向到首页时，用多种策略提取 aweme_id。

    策略1：不跟随重定向，检查302 Location头（有时包含视频ID）
    策略2：访问 iesdouyin.com 对应的分享页，从HTML中提取
    策略3：用桌面端UA访问短链接，检查中间页HTML
    """
    import httpx

    mobile_ua = (
        "Mozilla/5.0 (Linux; Android 13; Pixel 7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Mobile Safari/537.36"
    )

    # 策略1：不跟随重定向，检查302 Location头
    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=False) as client:
            resp = await client.get(short_url, headers={
                "User-Agent": mobile_ua,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            })
            location = resp.headers.get("location", "")
            if location and "douyin.com" in location:
                aweme_id = _extract_douyin_aweme_id(location)
                if aweme_id:
                    logger.info(f"[work_collector] Extracted douyin aweme_id from 302 Location: {aweme_id}")
                    return aweme_id
            # 检查302响应体
            if resp.text:
                aweme_id = _extract_douyin_aweme_id_from_html(resp.text)
                if aweme_id:
                    logger.info(f"[work_collector] Extracted douyin aweme_id from 302 body: {aweme_id}")
                    return aweme_id
    except Exception as e:
        logger.warning(f"[work_collector] Douyin short URL 302 check failed: {e}")

    # 策略2：尝试从短链接路径中提取ID（某些格式包含编码的ID）
    try:
        # v.douyin.com/iRNBho6m/ 格式，路径中的编码可能是base62
        # 尝试用桌面端UA访问，看是否能拿到不同的重定向
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            resp = await client.get(short_url, headers={
                "User-Agent": _UA,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Cookie": "msToken=; ttwid=;",
            })
            html = resp.text
            aweme_id = _extract_douyin_aweme_id_from_html(html)
            if aweme_id:
                logger.info(f"[work_collector] Extracted douyin aweme_id from desktop UA page: {aweme_id}")
                return aweme_id
    except Exception as e:
        logger.warning(f"[work_collector] Douyin short URL desktop UA check failed: {e}")

    # 策略3：尝试 iesdouyin.com 的分享页（需要先从短链接路径提取标识）
    # 短链接路径如 /iRNBho6m/ 可能对应 iesdouyin.com 的某个视频
    # 但我们不知道 aweme_id，所以这个策略有限
    logger.warning(f"[work_collector] All douyin short URL ID extraction methods failed for: {short_url}")
    return None


def _extract_douyin_aweme_id_from_html(html: str) -> str | None:
    """从抖音页面HTML中提取aweme_id。

    抖音短链接重定向到首页时，页面HTML中可能包含原始视频ID的线索：
    - URL路径中的 /video/{id}
    - meta标签中的视频ID
    - JS数据中的aweme_id
    - 分享文本中的链接
    """
    patterns = [
        r'douyin\.com/video/(\d{15,})',
        r'douyin\.com/note/(\d{15,})',
        r'"aweme_id"\s*:\s*"?(\d{15,})"',
        r'"itemId"\s*:\s*"?(\d{15,})"',
        r'modal_id=(\d{15,})',
        r'/video/(\d{15,})',
        r'/note/(\d{15,})',
    ]
    for pattern in patterns:
        m = re.search(pattern, html)
        if m:
            return m.group(1)
    return None


async def _collect_via_link_grabber(note_url: str, platform: str) -> dict | None:
    """通过 link-grabber MCP server 采集笔记数据。

    link-grabber 底层用 XHS-Downloader 引擎，支持：
    - 小红书图文笔记 + 视频
    - 抖音视频 + 语音转录
    - 微信公众号文章
    - Instagram / Threads

    需要 uv 和 link-grabber 已安装（uv run grab --setup）。
    """
    from app.tools.mcp.link_grabber_client import link_grabber_client

    result = await link_grabber_client.grab(note_url)
    if not result:
        return None

    # link-grabber 返回的格式可能是 JSON dict 或纯文本
    if isinstance(result, dict):
        # 尝试从小红书结果中提取结构化数据
        return _normalize_link_grabber_result(result, platform)

    return None


def _normalize_link_grabber_result(result: dict, platform: str) -> dict:
    """将 link-grabber 返回值标准化为内部格式。

    link-grabber 返回结构因平台而异，这里做通用提取。
    小红书典型返回：
    {
      "title": "...",
      "desc": "...",
      "tags": ["..."],
      "images": [{"url": "..."}],
      "likes": 123,
      "collects": 45,
      "comments": 6,
      "shares": 7,
      "author": {"nickname": "...", "fans": 1000},
      "note_type": "normal"
    }
    """
    author = result.get("author", {}) or {}

    def _safe_int(val: Any) -> int:
        if val is None:
            return 0
        try:
            return int(str(val).replace(",", "").replace("万", "0000"))
        except (ValueError, TypeError):
            return 0

    # 提取封面图
    images = result.get("images", []) or []
    cover_url = ""
    image_urls = []
    if images and isinstance(images, list):
        for img in images:
            if isinstance(img, dict):
                url = img.get("url", "") or img.get("urlDefault", "")
                if url:
                    image_urls.append(url)
        cover_url = image_urls[0] if image_urls else ""

    # 提取标签
    tags = result.get("tags", []) or []
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.split("#") if t.strip()]

    return {
        "note_id": result.get("note_id", "") or result.get("noteId", ""),
        "title": result.get("title", ""),
        "content_text": result.get("desc", "") or result.get("content", "") or result.get("text", ""),
        "tags": tags,
        "cover_img_url": cover_url,
        "image_urls": image_urls,
        "likes": _safe_int(result.get("likes") or result.get("likedCount")),
        "collects": _safe_int(result.get("collects") or result.get("collectedCount")),
        "comments": _safe_int(result.get("comments") or result.get("commentCount")),
        "shares": _safe_int(result.get("shares") or result.get("shareCount")),
        "author_fans": _safe_int(author.get("fans")) or 1,
        "author_nickname": author.get("nickname", ""),
        "note_type": result.get("note_type", "") or result.get("type", ""),
        "platform": platform,
    }


async def _collect_via_ssr(
    note_id: str, platform: str, *, xsec_token: str | None = None, xsec_source: str | None = None
) -> dict | None:
    """直接 HTTP GET 页面 HTML，解析 __INITIAL_STATE__ 拿笔记数据。

    小红书 SSR 页面数据获取策略（2024 年后反爬升级）：
    1. 带 xsec_token 请求：手机分享链接自带，有效期约 5 分钟
    2. 带 cookies 请求：用户已登录小红书，SSR 会返回数据
    3. 裸请求：noteDetailMap 为空，快速失败

    本函数会自动尝试：先带 token → 再带 cookies → 最后裸请求
    """
    import httpx

    page_url = f"https://www.xiaohongshu.com/explore/{note_id}"
    headers = {
        "User-Agent": _UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Referer": "https://www.xiaohongshu.com/",
    }

    # 构建请求参数列表：按优先级尝试
    request_attempts: list[tuple[dict, dict, str]] = []  # (params, cookies, label)

    # 1. 带 xsec_token（手机分享链接）
    if xsec_token:
        params = {"xsec_token": xsec_token}
        if xsec_source:
            params["xsec_source"] = xsec_source
        request_attempts.append((params, {}, "xsec_token"))

    # 2. 裸请求（大概率空，但试试）
    request_attempts.append(({}, {}, "bare"))

    for params, cookies, label in request_attempts:
        try:
            async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
                resp = await client.get(page_url, headers=headers, params=params, cookies=cookies)
                resp.raise_for_status()
                html = resp.text

            result = _parse_ssr_html(html, note_id, platform)
            if result:
                logger.info(f"[work_collector] SSR success via {label} for {note_id}")
                return result
            else:
                logger.debug(f"[work_collector] SSR noteDetailMap empty via {label} for {note_id}")
        except Exception as e:
            logger.debug(f"[work_collector] SSR request failed via {label}: {e}")

    logger.warning(f"[work_collector] All SSR attempts failed for {note_id}")
    return None


def _parse_ssr_html(html: str, note_id: str, platform: str) -> dict | None:
    """从 SSR HTML 中解析 __INITIAL_STATE__ 提取笔记数据。"""
    m = re.search(
        r'<script[^>]*>\s*window\.__INITIAL_STATE__\s*=\s*({.+?})\s*</script>',
        html,
        re.DOTALL,
    )
    if not m:
        return None

    raw_json = re.sub(r'\bundefined\b', 'null', m.group(1))

    try:
        state = json.loads(raw_json)
    except json.JSONDecodeError:
        return None

    note_detail = state.get("note", {}).get("noteDetailMap", {}).get(note_id, {}).get("note", {})
    if not note_detail:
        for nid, nobj in state.get("note", {}).get("noteDetailMap", {}).items():
            if isinstance(nobj, dict) and nobj.get("note"):
                note_detail = nobj["note"]
                break

    if not note_detail:
        return None

    interact_info = note_detail.get("interactInfo", {})
    user_info = note_detail.get("user", {})

    def _safe_int(val: Any) -> int:
        if val is None:
            return 0
        try:
            return int(str(val).replace(",", "").replace("万", "0000"))
        except (ValueError, TypeError):
            return 0

    tag_list = note_detail.get("tagList", [])
    tags = [t.get("name", "") for t in tag_list if isinstance(t, dict) and t.get("name")]

    image_list = note_detail.get("imageList", [])
    cover_url = ""
    image_urls = []
    if image_list and isinstance(image_list, list):
        for img in image_list:
            if isinstance(img, dict):
                url = img.get("urlDefault", "") or img.get("url", "")
                if url:
                    image_urls.append(url)
        cover_url = image_urls[0] if image_urls else ""

    title = note_detail.get("title", "")
    desc = note_detail.get("desc", "")
    note_type = note_detail.get("type", "")

    return {
        "note_id": note_id,
        "title": title,
        "content_text": desc,
        "tags": tags,
        "cover_img_url": cover_url,
        "image_urls": image_urls,
        "likes": _safe_int(interact_info.get("likedCount")),
        "collects": _safe_int(interact_info.get("collectedCount")),
        "comments": _safe_int(interact_info.get("commentCount")),
        "shares": _safe_int(interact_info.get("shareCount")),
        "author_fans": _safe_int(user_info.get("fans")) or 1,
        "author_nickname": user_info.get("nickname", ""),
        "note_type": note_type,
        "platform": platform,
    }


async def _collect_via_web_api(note_id: str, platform: str) -> dict | None:
    """通过小红书 Web API 直接请求笔记数据。

    需要 cookies，作为 SSR 解析失败时的降级方案。
    """
    import httpx

    try:
        from app.tools.mcp.xhs_client import mcp_manager
    except ImportError:
        mcp_manager = None

    cookies_dict: dict[str, str] = {}
    if mcp_manager and mcp_manager._local_client and mcp_manager._local_client._cookies:
        for c in mcp_manager._local_client._cookies:
            cookies_dict[c["name"]] = c["value"]

    if not cookies_dict:
        logger.debug("[work_collector] No cookies available for Web API")
        return None

    url = "https://edith.xiaohongshu.com/api/sns/web/v1/feed"
    payload = {
        "source_note_id": note_id,
        "image_formats": ["jpg", "webp", "png"],
        "extra": {"need_body_topic": 1},
    }
    headers = {
        "Content-Type": "application/json",
        "User-Agent": _UA,
        "Origin": "https://www.xiaohongshu.com",
        "Referer": f"https://www.xiaohongshu.com/explore/{note_id}",
    }

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(url, json=payload, headers=headers, cookies=cookies_dict)
            resp.raise_for_status()
            data = resp.json()

        items = data.get("data", {}).get("items", [])
        if not items:
            return None

        note_card = items[0].get("note_card", {})
        if not note_card:
            return None

        interact_info = note_card.get("interact_info", {})
        user_info = note_card.get("user", {})

        img_list = note_card.get("image_list", [])
        image_urls = []
        for img in (img_list if isinstance(img_list, list) else []):
            if isinstance(img, dict):
                url = img.get("url_default", "") or img.get("url", "")
                if url:
                    image_urls.append(url)
        cover_url = image_urls[0] if image_urls else ""

        return {
            "note_id": note_id,
            "title": note_card.get("title", ""),
            "content_text": note_card.get("desc", ""),
            "tags": [t.get("name", "") for t in note_card.get("tag_list", []) if t.get("name")],
            "cover_img_url": cover_url,
            "image_urls": image_urls,
            "likes": int(interact_info.get("liked_count", "0")),
            "collects": int(interact_info.get("collected_count", "0")),
            "comments": int(interact_info.get("comment_count", "0")),
            "shares": int(interact_info.get("share_count", "0")),
            "author_fans": int(user_info.get("fans", "1")),
            "author_nickname": user_info.get("nickname", ""),
            "platform": platform,
        }
    except Exception as e:
        logger.warning(f"[work_collector] Web API request failed: {e}")
        return None


async def _collect_via_mcp(note_id: str, platform: str) -> dict | None:
    """通过 MCP client 采集笔记详情（最重，兜底）。"""
    try:
        from app.tools.mcp.xhs_client import mcp_manager
    except ImportError:
        mcp_manager = None

    if not mcp_manager:
        logger.debug("[work_collector] MCP manager not available, skipping mcp_note_detail")
        return None

    detail = await mcp_manager.get_note_detail(note_id)
    if not detail:
        return None

    return _normalize_mcp_detail(detail, platform)


def _normalize_mcp_detail(detail: dict, platform: str) -> dict:
    """将 MCP get_note_detail 返回值标准化。

    浏览器扩展返回格式（含互动数据）：
    {
      "note_id": "...", "title": "...", "content": "...",
      "likes": 123, "collects": 45, "comments": 6, "shares": 7,
      "author_nickname": "...", "author_fans": 1000,
      "note_type": "normal", "cover_url": "...",
      "tags": [...], "images": [...]
    }
    """
    def _safe_int(val: Any) -> int:
        if val is None:
            return 0
        try:
            return int(str(val).replace(",", "").replace("万", "0000"))
        except (ValueError, TypeError):
            return 0

    cover_url = detail.get("cover_url", "")
    image_urls = []
    images = detail.get("images", [])
    if images and isinstance(images, list):
        for img in images:
            if isinstance(img, dict):
                url = img.get("url", "") or img.get("urlDefault", "")
                if url:
                    image_urls.append(url)
    if not cover_url:
        cover_url = image_urls[0] if image_urls else ""

    return {
        "note_id": detail.get("note_id", ""),
        "title": detail.get("title", ""),
        "content_text": detail.get("content", "") or detail.get("desc", ""),
        "tags": detail.get("tags", []),
        "cover_img_url": cover_url,
        "image_urls": image_urls,
        "likes": _safe_int(detail.get("likes")),
        "collects": _safe_int(detail.get("collects")),
        "comments": _safe_int(detail.get("comments")),
        "shares": _safe_int(detail.get("shares")),
        "author_fans": _safe_int(detail.get("author_fans")) or 1,
        "author_nickname": detail.get("author_nickname", ""),
        "note_type": detail.get("note_type", ""),
        "platform": platform,
    }


def parse_creator_center_csv(csv_content: str, platform: str = "xiaohongshu") -> list[dict]:
    """解析创作者中心导出的 CSV 数据。

    支持小红书创作者中心导出的数据格式。
    返回标准化的记录列表，可直接用于 csv-import API。
    """
    records = []
    try:
        reader = csv.DictReader(io.StringIO(csv_content))
        for row in reader:
            record = _normalize_csv_row(row, platform)
            if record:
                records.append(record)
    except Exception as e:
        logger.warning(f"[work_collector] CSV parse failed: {e}")

    return records


def _normalize_csv_row(row: dict, platform: str) -> dict | None:
    """将 CSV 行标准化为内部格式。"""
    title = row.get("笔记标题") or row.get("标题") or row.get("title") or ""
    if not title:
        return None

    def _int(val: str | None) -> int:
        if not val:
            return 0
        try:
            return int(str(val).strip().replace(",", "").replace("，", ""))
        except (ValueError, TypeError):
            return 0

    published_at = row.get("发布时间") or row.get("published_at") or ""
    note_id = row.get("笔记ID") or row.get("note_id") or ""

    return {
        "title": title.strip(),
        "note_id": note_id.strip(),
        "topic": (row.get("笔记类型") or row.get("topic") or "")[:255],
        "published_at": published_at.strip() if published_at else None,
        "likes": _int(row.get("点赞数") or row.get("赞") or row.get("likes")),
        "collects": _int(row.get("收藏数") or row.get("collects")),
        "comments": _int(row.get("评论数") or row.get("comments")),
        "shares": _int(row.get("分享数") or row.get("shares")),
        "author_fans": _int(row.get("粉丝数") or row.get("author_fans")) or 1,
        "platform": platform,
    }


# ──────────────────────────────────────────────
# 抖音采集
# ──────────────────────────────────────────────

async def _collect_douyin_via_api(aweme_id: str, platform: str) -> dict | None:
    """抖音 Web API 采集视频数据。

    策略1：douyin.com/aweme/{id} Web API（需 cookies）
    策略2：iesdouyin.com 旧版 iteminfo API（已被封，兜底）
    策略3：移动端 UA 访问 iesdouyin.com 分享页，解析 meta 标签
    策略4：访问 douyin.com/video/{id} 页面，从 SSR/RENDER_DATA 中提取
    """
    import httpx
    import random
    import urllib.parse

    def _safe_int(val: Any) -> int:
        if val is None:
            return 0
        try:
            return int(str(val).replace(",", "").replace("万", "0000"))
        except (ValueError, TypeError):
            return 0

    # 策略1：douyin.com Web API（带 cookies）
    try:
        api_url = "https://www.douyin.com/aweme/v1/web/aweme/detail/"
        params = {
            "aweme_id": aweme_id,
            "aid": "6383",
            "channel": "channel_pc_web",
            "pc_client_type": "1",
            "version_code": "170400",
            "version_name": "17.4.0",
            "cookie_enabled": "true",
            "platform": "PC",
            "downlink": "10",
        }
        api_headers = {
            "User-Agent": _UA,
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Referer": f"https://www.douyin.com/video/{aweme_id}",
            "Origin": "https://www.douyin.com",
        }

        dy_cookies = _get_douyin_cookies()
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            resp = await client.get(api_url, params=params, headers=api_headers, cookies=dy_cookies)
            if resp.status_code == 200 and resp.text.strip():
                data = resp.json()
                aweme_detail = data.get("aweme_detail", {})
                if aweme_detail:
                    desc = aweme_detail.get("desc", "")
                    author = aweme_detail.get("author", {}) or {}
                    stats = aweme_detail.get("statistics", {}) or aweme_detail.get("stats", {}) or {}
                    video = aweme_detail.get("video", {}) or {}
                    cover = video.get("cover", {}) or video.get("origin_cover", {}) or {}

                    cover_url = ""
                    image_urls = []
                    if isinstance(cover, dict):
                        url_list = cover.get("url_list", [])
                        if url_list:
                            cover_url = url_list[-1] if len(url_list) > 1 else url_list[0]
                            image_urls = [u for u in url_list if u]

                    images = aweme_detail.get("images", [])
                    if images and isinstance(images, list):
                        for img in images:
                            if isinstance(img, dict):
                                img_url_list = img.get("url_list", [])
                                if img_url_list:
                                    img_url = img_url_list[-1] if len(img_url_list) > 1 else img_url_list[0]
                                    image_urls.append(img_url)
                        if image_urls and not cover_url:
                            cover_url = image_urls[0]

                    note_type = "video"
                    if aweme_detail.get("images"):
                        note_type = "image_text"

                    return {
                        "note_id": aweme_id,
                        "title": desc[:50] if desc else "",
                        "content_text": desc,
                        "tags": re.findall(r'#(\S+?)#', desc),
                        "cover_img_url": cover_url,
                        "image_urls": image_urls,
                        "likes": _safe_int(stats.get("digg_count") or stats.get("likeCount")),
                        "collects": _safe_int(stats.get("collect_count") or stats.get("collectCount")),
                        "comments": _safe_int(stats.get("comment_count") or stats.get("commentCount")),
                        "shares": _safe_int(stats.get("share_count") or stats.get("shareCount")),
                        "author_fans": _safe_int(author.get("follower_count", 1)),
                        "author_nickname": author.get("nickname", ""),
                        "note_type": note_type,
                        "platform": platform,
                    }
                else:
                    status_code = data.get("status_code", "")
                    if status_code:
                        logger.warning(f"[work_collector] Douyin Web API returned status_code={status_code}: {data.get('status_msg', '')}")
            else:
                logger.warning(f"[work_collector] Douyin Web API returned status={resp.status_code}, body_len={len(resp.text)}")
    except Exception as e:
        logger.warning(f"[work_collector] Douyin Web API failed: {e}")

    # 策略2：iesdouyin.com 旧版 API（可能已被封）
    api_url = "https://www.iesdouyin.com/web/api/v2/aweme/iteminfo/"
    params = {
        "item_ids": aweme_id,
        "aid": "1128",
    }
    headers = {
        "User-Agent": _UA,
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Referer": "https://www.iesdouyin.com/",
    }

    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            resp = await client.get(api_url, params=params, headers=headers)
            if resp.status_code == 200 and resp.text.strip():
                try:
                    data = resp.json()
                    items = data.get("item_list", [])
                    if items:
                        item = items[0]
                        desc = item.get("desc", "")
                        author = item.get("author", {}) or {}
                        stats = item.get("statistics", {}) or {}
                        video = item.get("video", {}) or {}
                        cover = video.get("cover", {}) or video.get("origin_cover", {}) or {}

                        cover_url = ""
                        image_urls = []
                        if isinstance(cover, dict):
                            url_list = cover.get("url_list", [])
                            if url_list:
                                cover_url = url_list[0]
                                image_urls = [u for u in url_list if u]

                        return {
                            "note_id": aweme_id,
                            "title": desc[:50] if desc else "",
                            "content_text": desc,
                            "tags": re.findall(r'#(\S+?)#', desc),
                            "cover_img_url": cover_url,
                            "image_urls": image_urls,
                            "likes": _safe_int(stats.get("digg_count")),
                            "collects": _safe_int(stats.get("collect_count")),
                            "comments": _safe_int(stats.get("comment_count")),
                            "shares": _safe_int(stats.get("share_count")),
                            "author_fans": _safe_int(author.get("follower_count", 1)),
                            "author_nickname": author.get("nickname", ""),
                            "note_type": "video",
                            "platform": platform,
                        }
                except (json.JSONDecodeError, ValueError):
                    pass
            logger.warning(f"[work_collector] Douyin iesdouyin API no data")
    except Exception as e:
        logger.warning(f"[work_collector] Douyin iesdouyin API failed: {e}")

    # 策略3：移动端 UA 访问 iesdouyin.com 分享页，解析 meta 标签
    mobile_ua = (
        "Mozilla/5.0 (Linux; Android 13; Pixel 7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Mobile Safari/537.36"
    )
    share_url = f"https://www.iesdouyin.com/share/video/{aweme_id}/"
    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            resp = await client.get(share_url, headers={
                "User-Agent": mobile_ua,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            })
            if resp.status_code == 200:
                html = resp.text
                result = _parse_douyin_share_html(html, aweme_id, platform, _safe_int)
                if result:
                    return result
    except Exception as e:
        logger.warning(f"[work_collector] Douyin iesdouyin share page failed: {e}")

    # 策略4：访问 douyin.com/video/{id} 页面，从 SSR/RENDER_DATA 中提取
    try:
        page_url = f"https://www.douyin.com/video/{aweme_id}"
        page_headers = {
            "User-Agent": _UA,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Referer": "https://www.douyin.com/",
        }
        dy_cookies = _get_douyin_cookies()
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            resp = await client.get(page_url, headers=page_headers, cookies=dy_cookies)
            if resp.status_code == 200:
                html = resp.text
                result = _parse_douyin_page_html(html, aweme_id, platform, _safe_int)
                if result:
                    return result
    except Exception as e:
        logger.warning(f"[work_collector] Douyin page HTML parse failed: {e}")

    return None


def _parse_douyin_share_html(html: str, aweme_id: str, platform: str, _safe_int: Any) -> dict | None:
    """解析 iesdouyin.com 分享页 HTML，提取视频数据。"""
    import base64

    meta_desc = re.search(
        r'<meta[^>]+name="description"[^>]+content="([^"]*)"[^>]*/?\s*>',
        html,
    )
    if not meta_desc:
        meta_desc = re.search(
            r'<meta[^>]+content="([^"]*)"[^>]+name="description"[^>]*/?\s*>',
            html,
        )

    og_image = re.search(
        r'<meta[^>]+property="og:image"[^>]+content="([^"]*)"[^>]*/?\s*>',
        html,
    )
    if not og_image:
        og_image = re.search(
            r'<meta[^>]+content="([^"]*)"[^>]+property="og:image"[^>]*/?\s*>',
            html,
        )

    og_title = re.search(
        r'<meta[^>]+property="og:title"[^>]+content="([^"]*)"[^>]*/?\s*>',
        html,
    )
    if not og_title:
        og_title = re.search(
            r'<meta[^>]+content="([^"]*)"[^>]+property="og:title"[^>]*/?\s*>',
            html,
        )

    og_video = re.search(
        r'<meta[^>]+property="og:video"[^>]+content="([^"]*)"[^>]*/?\s*>',
        html,
    )
    if not og_video:
        og_video = re.search(
            r'<meta[^>]+content="([^"]*)"[^>]+property="og:video"[^>]*/?\s*>',
            html,
        )

    desc_text = meta_desc.group(1) if meta_desc else ""
    likes = 0
    likes_match = re.search(r'收获了(\d+)个喜欢', desc_text)
    if likes_match:
        likes = int(likes_match.group(1))

    comments = 0
    comments_match = re.search(r'(\d+)条评论', desc_text)
    if comments_match:
        comments = int(comments_match.group(1))

    real_desc = ""
    publish_marker = re.search(r'于\d{8}发布在抖音', desc_text)
    if publish_marker:
        before = desc_text[:publish_marker.start()].strip()
        if before:
            real_desc = before

    title_text = og_title.group(1) if og_title else ""
    if not title_text:
        title_match = re.search(r'<title[^>]*>([^<]+)</title>', html)
        title_text = title_match.group(1) if title_match else ""

    if title_text.endswith(" - 抖音"):
        title_text = title_text[:-5].strip()

    if re.match(r'^在抖音记录美好生活\d+$', title_text) and real_desc:
        title_text = real_desc[:50]

    content_text = real_desc if real_desc else desc_text

    cover_url = og_image.group(1) if og_image else ""
    image_urls = [cover_url] if cover_url else []

    # 尝试从 SSR 数据中提取更多数据
    render_data = re.search(r'<script[^>]*id="RENDER_DATA"[^>]*>(.+?)</script>', html, re.DOTALL)
    if render_data:
        try:
            decoded = base64.b64decode(render_data.group(1)).decode("utf-8")
            data = json.loads(decoded)
            video_detail = data.get("videoDetail", {}) or data.get("props", {}).get("pageProps", {}).get("videoDetail", {})
            if video_detail:
                if not content_text:
                    content_text = video_detail.get("desc", "")
                if not title_text:
                    title_text = content_text[:50] if content_text else ""
                stats = video_detail.get("stats", {}) or video_detail.get("interactionSticker", {}).get("stats", {}) or {}
                if stats:
                    likes = _safe_int(stats.get("diggCount")) or likes
                    comments = _safe_int(stats.get("commentCount")) or comments
                author = video_detail.get("authorInfo", {}) or video_detail.get("author", {}) or {}
                if author and not cover_url:
                    author_nickname = author.get("nickname", "")
                else:
                    author_nickname = ""
                cover_obj = video_detail.get("cover", {})
                if isinstance(cover_obj, dict) and not cover_url:
                    url_list = cover_obj.get("urlList", [])
                    if url_list:
                        cover_url = url_list[0]
                        image_urls = [u for u in url_list if u]
                return {
                    "note_id": aweme_id,
                    "title": title_text[:50] if title_text else "",
                    "content_text": content_text,
                    "tags": re.findall(r'#(\S+?)#', content_text + title_text),
                    "cover_img_url": cover_url,
                    "image_urls": image_urls,
                    "likes": likes,
                    "collects": _safe_int(stats.get("collectCount")) if stats else 0,
                    "comments": comments,
                    "shares": _safe_int(stats.get("shareCount")) if stats else 0,
                    "author_fans": _safe_int(author.get("fansCount")) if author else 1,
                    "author_nickname": author_nickname if author else "",
                    "note_type": "video",
                    "platform": platform,
                }
        except Exception:
            pass

    if content_text or title_text:
        return {
            "note_id": aweme_id,
            "title": title_text[:50] if title_text else "",
            "content_text": content_text,
            "tags": re.findall(r'#(\S+?)#', content_text + title_text),
            "cover_img_url": cover_url,
            "image_urls": image_urls,
            "likes": likes,
            "collects": 0,
            "comments": comments,
            "shares": 0,
            "author_fans": 1,
            "author_nickname": "",
            "note_type": "video",
            "platform": platform,
        }
    return None


def _parse_douyin_page_html(html: str, aweme_id: str, platform: str, _safe_int: Any) -> dict | None:
    """解析 douyin.com/video/{id} 页面 HTML，从 SSR/RENDER_DATA 中提取数据。"""
    import base64

    # 尝试 RENDER_DATA（base64 编码的 JSON）
    m = re.search(r'<script[^>]*id="RENDER_DATA"[^>]*>(.+?)</script>', html, re.DOTALL)
    if not m:
        m = re.search(r'<script[^>]*id="__NEXT_DATA__"[^>]*>(.+?)</script>', html, re.DOTALL)
    if not m:
        # 尝试从内联 script 中搜索 aweme_detail 数据
        aweme_match = re.search(r'"aweme_detail"\s*:\s*\{', html)
        if aweme_match:
            # 尝试提取完整的 aweme_detail JSON 对象
            start = aweme_match.start() + len('"aweme_detail":')
            try:
                obj = json.loads(html[start:])
                if isinstance(obj, dict):
                    desc = obj.get("desc", "")
                    author = obj.get("author", {}) or {}
                    stats = obj.get("statistics", {}) or obj.get("stats", {}) or {}
                    video = obj.get("video", {}) or {}
                    cover = video.get("cover", {}) or video.get("origin_cover", {}) or {}

                    cover_url = ""
                    image_urls = []
                    if isinstance(cover, dict):
                        url_list = cover.get("url_list", [])
                        if url_list:
                            cover_url = url_list[-1] if len(url_list) > 1 else url_list[0]
                            image_urls = [u for u in url_list if u]

                    images = obj.get("images", [])
                    if images and isinstance(images, list):
                        for img in images:
                            if isinstance(img, dict):
                                img_url_list = img.get("url_list", [])
                                if img_url_list:
                                    img_url = img_url_list[-1] if len(img_url_list) > 1 else img_url_list[0]
                                    image_urls.append(img_url)
                        if image_urls and not cover_url:
                            cover_url = image_urls[0]

                    note_type = "video"
                    if obj.get("images"):
                        note_type = "image_text"

                    return {
                        "note_id": aweme_id,
                        "title": desc[:50] if desc else "",
                        "content_text": desc,
                        "tags": re.findall(r'#(\S+?)#', desc),
                        "cover_img_url": cover_url,
                        "image_urls": image_urls,
                        "likes": _safe_int(stats.get("digg_count") or stats.get("likeCount")),
                        "collects": _safe_int(stats.get("collect_count") or stats.get("collectCount")),
                        "comments": _safe_int(stats.get("comment_count") or stats.get("commentCount")),
                        "shares": _safe_int(stats.get("share_count") or stats.get("shareCount")),
                        "author_fans": _safe_int(author.get("follower_count", 1)),
                        "author_nickname": author.get("nickname", ""),
                        "note_type": note_type,
                        "platform": platform,
                    }
            except (json.JSONDecodeError, ValueError):
                pass

        logger.warning(f"[work_collector] No RENDER_DATA or __NEXT_DATA__ for douyin page {aweme_id}")
        return None

    try:
        raw = m.group(1)
        decoded = base64.b64decode(raw).decode("utf-8")
        data = json.loads(decoded)
    except Exception:
        try:
            data = json.loads(m.group(1))
        except json.JSONDecodeError as e:
            logger.warning(f"[work_collector] Douyin page data parse failed: {e}")
            return None

    video_detail = data.get("videoDetail", {}) or data.get("props", {}).get("pageProps", {}).get("videoDetail", {})
    if not video_detail:
        logger.warning(f"[work_collector] No video detail in SSR data for douyin {aweme_id}")
        return None

    desc = video_detail.get("desc", "")
    author = video_detail.get("authorInfo", {}) or video_detail.get("author", {}) or {}
    stats = video_detail.get("stats", {}) or video_detail.get("interactionSticker", {}).get("stats", {}) or {}

    cover_obj = video_detail.get("cover", {})
    cover_url = cover_obj.get("urlList", [""])[0] if isinstance(cover_obj, dict) else ""
    image_urls = [u for u in (cover_obj.get("urlList", []) if isinstance(cover_obj, dict) else []) if u]

    return {
        "note_id": aweme_id,
        "title": desc[:50] if desc else "",
        "content_text": desc,
        "tags": re.findall(r'#(\S+?)#', desc),
        "cover_img_url": cover_url,
        "image_urls": image_urls,
        "likes": _safe_int(stats.get("diggCount")),
        "collects": _safe_int(stats.get("collectCount")),
        "comments": _safe_int(stats.get("commentCount")),
        "shares": _safe_int(stats.get("shareCount")),
        "author_fans": _safe_int(author.get("fansCount")) or 1,
        "author_nickname": author.get("nickname", ""),
        "note_type": "video",
        "platform": platform,
    }


def _get_douyin_cookies() -> dict[str, str]:
    """获取抖音 cookies（来自浏览器扩展/本地 client）。"""
    try:
        from app.tools.mcp.xhs_client import mcp_manager
        if mcp_manager and mcp_manager._local_client and hasattr(mcp_manager._local_client, "_cookies"):
            raw_cookies = mcp_manager._local_client._cookies or []
            if raw_cookies:
                return {c["name"]: c["value"] for c in raw_cookies if isinstance(c, dict) and "name" in c and "value" in c}
    except Exception:
        pass
    return {}


# ──────────────────────────────────────────────
# B 站采集
# ──────────────────────────────────────────────

async def _collect_bilibili_via_api(bvid: str, platform: str) -> dict | None:
    """B 站 Web API 采集（公开接口，无需登录）。"""
    import httpx

    api_url = "https://api.bilibili.com/x/web-interface/view"
    params = {"bvid": bvid} if bvid.startswith("BV") else {"aid": bvid[2:]}
    headers = {
        "User-Agent": _UA,
        "Referer": "https://www.bilibili.com/",
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(api_url, params=params, headers=headers)
            resp.raise_for_status()
            data = resp.json()
    except Exception as e:
        logger.warning(f"[work_collector] Bilibili API request failed: {e}")
        return None

    if data.get("code") != 0:
        logger.warning(f"[work_collector] Bilibili API error: {data.get('message')}")
        return None

    info = data.get("data", {})
    stat = info.get("stat", {})
    owner = info.get("owner", {})

    def _safe_int(val: Any) -> int:
        if val is None:
            return 0
        try:
            return int(str(val).replace(",", "").replace("万", "0000"))
        except (ValueError, TypeError):
            return 0

    cover_url = info.get("pic", "")
    return {
        "note_id": bvid,
        "title": info.get("title", ""),
        "content_text": info.get("desc", ""),
        "tags": [t.get("tag_name", "") for t in (info.get("tag_list") or []) if isinstance(t, dict)],
        "cover_img_url": cover_url,
        "image_urls": [cover_url] if cover_url else [],
        "likes": _safe_int(stat.get("like")),
        "collects": _safe_int(stat.get("favorite")),
        "comments": _safe_int(stat.get("reply")),
        "shares": _safe_int(stat.get("share")),
        "author_fans": _safe_int(owner.get("fans")) or 1,
        "author_nickname": owner.get("name", ""),
        "note_type": "video",
        "platform": platform,
    }


# ──────────────────────────────────────────────
# 微信公众号采集
# ──────────────────────────────────────────────

async def _collect_wechat_via_http(url: str, platform: str) -> dict | None:
    """微信公众号文章 HTTP 解析。

    微信文章是 SSR 渲染，标题/正文/阅读数都在 HTML 里。
    阅读数需要通过 mp.weixin.qq.com 的接口获取（需 cookies）。
    """
    import httpx

    headers = {
        "User-Agent": _UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    }

    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            html = resp.text
    except Exception as e:
        logger.warning(f"[work_collector] WeChat page fetch failed: {e}")
        return None

    # 提取标题
    title_m = re.search(r'<h1[^>]*class="rich_media_title"[^>]*>(.*?)</h1>', html, re.DOTALL)
    title = title_m.group(1).strip() if title_m else ""
    if not title:
        title_m = re.search(r'var msg_title = "(.*?)";', html)
        title = title_m.group(1) if title_m else ""

    # 提取正文
    content_m = re.search(r'<div[^>]*class="rich_media_content"[^>]*>(.*?)</div>\s*<script', html, re.DOTALL)
    content_text = content_m.group(1) if content_m else ""
    content_text = re.sub(r'<[^>]+>', '', content_text).strip()

    # 提取作者
    author_m = re.search(r'var nickname = "(.*?)";', html)
    author = author_m.group(1) if author_m else ""

    # 提取封面图
    cover_m = re.search(r'var msg_cdn_url = "(.*?)";', html)
    cover_url = cover_m.group(1) if cover_m else ""
    image_urls = [cover_url] if cover_url else []

    # 提取正文中的图片
    img_tags = re.findall(r'<img[^>]+data-src="(https?://mmbiz\.qpic\.cn/[^"]+)"', html)
    if img_tags:
        if not cover_url:
            cover_url = img_tags[0]
        image_urls = list(dict.fromkeys(image_urls + img_tags))

    return {
        "note_id": url,
        "title": title[:200],
        "content_text": content_text[:5000],
        "tags": [],
        "cover_img_url": cover_url,
        "image_urls": image_urls,
        "likes": 0,
        "collects": 0,
        "comments": 0,
        "shares": 0,
        "author_fans": 1,
        "author_nickname": author,
        "note_type": "article",
        "platform": platform,
    }


# ──────────────────────────────────────────────
# Scrapling 采集（降级链头部增强）
# ──────────────────────────────────────────────

def _scrapling_safe_int(val: Any) -> int:
    """Scrapling 解析用的安全整数转换。"""
    if isinstance(val, int):
        return val
    if isinstance(val, (float, str)):
        try:
            text = str(val).strip().replace(",", "")
            if "w" in text or "万" in text:
                return int(float(text.replace("w", "").replace("万", "")) * 10000)
            if "k" in text:
                return int(float(text.replace("k", "")) * 1000)
            return int(float(text))
        except (ValueError, TypeError):
            return 0
    return 0

async def _collect_via_scrapling(note_id: str, note_url: str, platform: str) -> dict | None:
    """通过 Scrapling StealthyFetcher 采集单条内容详情。

    作为降级链头部增强，优先尝试 Scrapling 反检测浏览器采集。
    需 scrapling 已安装（pip install scrapling），否则跳过。
    """
    try:
        from scrapling.fetchers import StealthyFetcher
    except ImportError:
        logger.debug("[work_collector] Scrapling not installed, skipping scrapling_fetcher")
        return None

    if platform == "xiaohongshu":
        detail_url = f"https://www.xiaohongshu.com/explore/{note_id}"
    elif platform == "douyin":
        detail_url = f"https://www.douyin.com/video/{note_id}"
    elif platform == "bilibili":
        detail_url = f"https://www.bilibili.com/video/{note_id}"
    else:
        detail_url = note_url

    try:
        page = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: StealthyFetcher.fetch(
                detail_url,
                headless=True,
                network_idle=True,
                timeout=30000,
            ),
        )
    except Exception as e:
        logger.warning(f"[work_collector] Scrapling fetch failed: {e}")
        return None

    if platform == "xiaohongshu":
        return _parse_scrapling_xhs(page, note_id, platform)
    elif platform == "douyin":
        return _parse_scrapling_douyin(page, note_id, platform)
    elif platform == "bilibili":
        return _parse_scrapling_bilibili(page, note_id, platform)

    return None


def _parse_scrapling_xhs(page: Any, note_id: str, platform: str) -> dict | None:
    """解析 Scrapling 爬取的小红书详情页。"""
    result: dict[str, Any] = {
        "note_id": note_id,
        "platform": platform,
        "note_type": "normal",
    }

    try:
        title_els = page.css(".note-content .title, .title, [class*='title']")
        title_el = title_els[0] if title_els else None
        if title_el and hasattr(title_el, "text"):
            result["title"] = title_el.text.strip()[:200]
    except Exception:
        pass

    try:
        desc_els = page.css(".note-content .desc, .desc, [class*='desc']")
        desc_el = desc_els[0] if desc_els else None
        if desc_el and hasattr(desc_el, "text"):
            result["content_text"] = desc_el.text.strip()[:5000]
    except Exception:
        pass

    try:
        like_els = page.css(".like-count, [class*='like-count']")
        like_el = like_els[0] if like_els else None
        if like_el and hasattr(like_el, "text"):
            result["likes"] = _scrapling_safe_int(like_el.text.strip())
    except Exception:
        pass

    try:
        collect_els = page.css(".collect-count, [class*='collect-count']")
        collect_el = collect_els[0] if collect_els else None
        if collect_el and hasattr(collect_el, "text"):
            result["collects"] = _scrapling_safe_int(collect_el.text.strip())
    except Exception:
        pass

    try:
        comment_els = page.css(".comment-count, [class*='comment-count']")
        comment_el = comment_els[0] if comment_els else None
        if comment_el and hasattr(comment_el, "text"):
            result["comments"] = _scrapling_safe_int(comment_el.text.strip())
    except Exception:
        pass

    try:
        cover_els = page.css(".note-image img, .swiper-slide img")
        cover_el = cover_els[0] if cover_els else None
        if cover_el:
            result["cover_img_url"] = cover_el.attrib.get("src", "")
    except Exception:
        pass

    try:
        tags = []
        for t in page.css(".tag, [class*='tag'], .hash-tag"):
            if hasattr(t, "text"):
                txt = t.text.strip()
                if txt:
                    tags.append(txt)
        result["tags"] = tags
    except Exception:
        pass

    try:
        images = []
        for img in page.css(".note-image img, .swiper-slide img, [class*='note-image'] img"):
            src = img.attrib.get("src", "")
            if src:
                images.append(src)
        result["image_urls"] = images
    except Exception:
        pass

    return result if result.get("title") or result.get("content_text") else None


def _parse_scrapling_douyin(page: Any, note_id: str, platform: str) -> dict | None:
    """解析 Scrapling 爬取的抖音详情页。"""
    result: dict[str, Any] = {
        "note_id": note_id,
        "platform": platform,
        "note_type": "video",
    }

    try:
        desc_els = page.css("[class*='desc'], [class*='description']")
        desc_el = desc_els[0] if desc_els else None
        if desc_el and hasattr(desc_el, "text"):
            result["content_text"] = desc_el.text.strip()[:5000]
    except Exception:
        pass

    try:
        title_els = page.css("[class*='title']")
        title_el = title_els[0] if title_els else None
        if title_el and hasattr(title_el, "text"):
            result["title"] = title_el.text.strip()[:200]
    except Exception:
        pass

    return result if result.get("title") or result.get("content_text") else None


def _parse_scrapling_bilibili(page: Any, note_id: str, platform: str) -> dict | None:
    """解析 Scrapling 爬取的B站详情页。"""
    result: dict[str, Any] = {
        "note_id": note_id,
        "platform": platform,
        "note_type": "video",
    }

    try:
        title_els = page.css("h1.video-title, [class*='video-title']")
        title_el = title_els[0] if title_els else None
        if title_el and hasattr(title_el, "text"):
            result["title"] = title_el.text.strip()[:200]
    except Exception:
        pass

    try:
        desc_els = page.css("[class*='desc'], [class*='description']")
        desc_el = desc_els[0] if desc_els else None
        if desc_el and hasattr(desc_el, "text"):
            result["content_text"] = desc_el.text.strip()[:5000]
    except Exception:
        pass

    return result if result.get("title") or result.get("content_text") else None