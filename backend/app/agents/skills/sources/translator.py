"""免费翻译层：调 MyMemory API，无 key，国内可访问。

端点：https://api.mymemory.translated.net/get
参数：
- q=待翻译文本
- langpair=源语言|目标语言（如 en|zh-CN）

特点：
- 无需 API key
- 免费配额：每天 5000 词（匿名），注册后 50000 词
- 国内可直连，无需翻墙
- 译文质量稳定

缓存策略：
- 按 (text_hash, target_lang) 缓存到内存 dict
- 进程重启缓存失效（MVP 阶段够用，后续可换 SQLite）

注意：MyMemory 单次请求文本长度建议 < 500 字符，超长文本会被截断。
translator 内部会自动截断到 500 字符。
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_MYMEMORY_URL = "https://api.mymemory.translated.net/get"
_CACHE: dict[str, str] = {}
# 并发限制：MyMemory 免费 API 建议低并发，控制在 3 并发
_SEMAPHORE = asyncio.Semaphore(3)
# 单次翻译文本最大长度（MyMemory 建议值）
_MAX_TEXT_LEN = 500


def _hash_key(text: str, target_lang: str) -> str:
    """生成缓存 key。"""
    h = hashlib.md5(text.encode("utf-8")).hexdigest()
    return f"{h}:{target_lang}"


def _detect_source_lang(text: str) -> str:
    """简单源语言检测：含中文字符返回 zh，否则返回 en。

    MyMemory 要求显式指定源语言（不支持 auto），这里用简单启发式。
    HackerNews 内容基本都是英文，默认 en。
    """
    for ch in text:
        if "\u4e00" <= ch <= "\u9fff":
            return "zh"
    return "en"


async def translate_text(
    text: str,
    target_lang: str = "zh-CN",
    source_lang: str = "",
    client: httpx.AsyncClient | None = None,
) -> str:
    """翻译单条文本。

    Args:
        text: 待翻译文本（空字符串或纯数字直接返回原文）
        target_lang: 目标语言代码（默认 zh-CN）
        source_lang: 源语言（空则自动检测；MyMemory 不支持 auto，需显式指定）
        client: 复用 httpx.AsyncClient（不传则临时创建）

    Returns:
        译文。翻译失败时返回原文（降级，不抛异常）。
    """
    if not text or not text.strip():
        return text
    # 纯数字/标点/URL 不翻译
    stripped = text.strip()
    if all(c.isdigit() or c in ".,;:!?-_/ " for c in stripped):
        return text
    # URL 不翻译
    if stripped.startswith(("http://", "https://")):
        return text

    # 截断超长文本
    if len(stripped) > _MAX_TEXT_LEN:
        stripped = stripped[:_MAX_TEXT_LEN]

    # 源语言检测
    if not source_lang:
        source_lang = _detect_source_lang(stripped)
    # 目标语言对 MyMemory 用 zh-CN → zh-CN
    tl = "zh-CN" if target_lang in ("zh-CN", "zh", "zh_CN") else target_lang

    # 查缓存
    cache_key = _hash_key(text, target_lang)
    if cache_key in _CACHE:
        return _CACHE[cache_key]

    own_client = client is None
    if own_client:
        client = httpx.AsyncClient(
            timeout=httpx.Timeout(15.0),
            headers={"User-Agent": "multi-agent-xhs-platform/1.0"},
        )

    try:
        async with _SEMAPHORE:
            params = {
                "q": stripped,
                "langpair": f"{source_lang}|{tl}",
            }
            resp = await client.get(_MYMEMORY_URL, params=params)
            resp.raise_for_status()
            data: Any = resp.json()

        # MyMemory 返回格式：{"responseData": {"translatedText": "译文", ...}, ...}
        if isinstance(data, dict):
            response_data = data.get("responseData") or {}
            translated = (response_data.get("translatedText") or "").strip()
            # MyMemory 配额耗尽或异常时会返回 WARNING 或 QUOTA EXCEEDED 文本
            if translated and "QUOTA" not in translated.upper() and "WARNING" not in translated.upper():
                _CACHE[cache_key] = translated
                return translated
        # 解析失败，返回原文
        return text
    except Exception as e:
        logger.debug(f"[translate] failed (returning original): {e}")
        return text
    finally:
        if own_client and client is not None:
            await client.aclose()


async def translate_batch(
    texts: list[str],
    target_lang: str = "zh-CN",
    client: httpx.AsyncClient | None = None,
) -> list[str]:
    """批量翻译（并发 + 缓存 + 限流）。

    Args:
        texts: 待翻译文本列表
        target_lang: 目标语言
        client: 复用 httpx.AsyncClient

    Returns:
        译文列表（顺序与输入一致）
    """
    if not texts:
        return []
    tasks = [translate_text(t, target_lang=target_lang, client=client) for t in texts]
    return await asyncio.gather(*tasks)


def clear_cache() -> None:
    """清空翻译缓存（测试用）。"""
    _CACHE.clear()
