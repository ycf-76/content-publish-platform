"""Image generation adapters.

通义万相 WanxAdapter（主力，阿里云百炼，国内直连）：
  - 异步任务模式：POST 提交 → 轮询 GET → 下载图片
  - 需要配置 DASHSCOPE_API_KEY
  - 模型：wanx-v1 / wanx2.1-t2i-turbo / wanx2.1-t2i-plus
  - 尺寸：1024*1024 / 720*1280 / 1280*720

PollinationsAdapter（备用，免费无 key，但国内可能需要代理）：
  - GET 请求直接返回图片 bytes
  - 无需 API key
"""

from __future__ import annotations

import asyncio
import logging
import random
from abc import ABC, abstractmethod
from urllib.parse import quote

import httpx

logger = logging.getLogger(__name__)


# ----------------------------------------------------------------------
# 尺寸映射工具
# ----------------------------------------------------------------------

# 通义万相支持的尺寸（用 * 分隔）
_WANX_SIZES = {"1024*1024", "720*1280", "1280*720"}

# 通义万相尺寸 → 小红书规格映射
# 通义万相支持的尺寸：1024*1024 / 720*1280 / 768*1152 / 1280*720
# 小红书 3:4 竖图 → 768*1152（3:4.5，最接近 3:4 的竖图规格）
# 小红书 1:1 方图 → 1024*1024
# 小红书 9:16 竖图 → 720*1280
_WANX_SIZE_MAP = {
    "1080x1440": "768*1152",  # 3:4 → 768*1152（最接近的竖图）
    "1080*1440": "768*1152",
    "768x1152": "768*1152",
    "768*1152": "768*1152",
    "720x1280": "720*1280",
    "720*1280": "720*1280",
    "1024x1024": "1024*1024",
    "1024*1024": "1024*1024",
    "1280x720": "1280*720",
    "1280*720": "1280*720",
}


def _to_wanx_size(size: str) -> str:
    """把通用 size 格式转成通义万相的格式。"""
    return _WANX_SIZE_MAP.get(size.lower(), "720*1280")


def _parse_pollinations_size(size: str) -> tuple[int, int]:
    """解析 size 字符串为 (width, height)（Pollinations 用）。"""
    try:
        w, h = size.lower().replace("*", "x").split("x")
        return int(w), int(h)
    except (ValueError, AttributeError):
        logger.warning(f"invalid size '{size}', fallback to 1024x1024")
        return 1024, 1024


# ----------------------------------------------------------------------
# 抽象基类
# ----------------------------------------------------------------------


class ImageGenAdapter(ABC):
    """Abstract base for all image generation adapters."""

    @abstractmethod
    async def generate(
        self, prompt: str, size: str = "1024x1024", count: int = 1
    ) -> list[bytes]:
        """Generate images and return image bytes.

        Args:
            prompt: Text prompt.
            size: "WIDTHxHEIGHT" e.g. "1080x1440" (3:4 portrait) / "1024x1024" (square).
            count: Number of images to generate.
        Returns:
            List of image bytes (JPEG/PNG, in-memory).
        """
        raise NotImplementedError


# ----------------------------------------------------------------------
# 通义万相 Adapter（主力）
# ----------------------------------------------------------------------


class WanxAdapter(ImageGenAdapter):
    """通义万相图片生成（阿里云百炼）。

    API 流程（异步任务模式）：
    1. POST /api/v1/services/aigc/text2image/image-synthesis 提交任务
    2. GET /api/v1/tasks/{task_id} 轮询任务状态
    3. 任务 SUCCEEDED 后下载图片 URL

    需要配置 DASHSCOPE_API_KEY 环境变量。
    """

    _SUBMIT_URL = "https://dashscope.aliyuncs.com/api/v1/services/aigc/text2image/image-synthesis"
    _TASK_URL = "https://dashscope.aliyuncs.com/api/v1/tasks/{task_id}"

    # 类变量：最近一次错误类型（供调用方读取，决定前端通知策略）
    # 取值：None / "arrearage" / "rate_limited" / "bad_request" / "api_error" / "timeout"
    last_error_type: str | None = None
    last_error_message: str = ""
    _last_submit_ts: float = 0.0

    def __init__(
        self,
        api_key: str,
        model: str = "wanx-v1",
        timeout: float = 30.0,
        poll_interval: float = 2.0,
        poll_max_wait: float = 120.0,
        submit_interval: float = 3.0,
        max_retries: int = 2,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self.poll_interval = poll_interval
        self.poll_max_wait = poll_max_wait
        # 提交任务最小间隔（秒），避免触发通义万相 QPS 限流（429）
        self.submit_interval = submit_interval
        self.max_retries = max_retries

    async def _submit_with_rate_limit(
        self,
        client: httpx.AsyncClient,
        headers: dict,
        payload: dict,
    ) -> dict:
        """带频率限制和重试的任务提交。

        - submit_interval：两次提交最小间隔 3 秒
        - 429 限流时：等待 5 秒后重试，最多 max_retries 次
        - 400 错误：打印响应体，不重试（参数问题）
        """
        import time

        for attempt in range(self.max_retries + 1):
            # 频率控制：距离上次提交至少 submit_interval 秒
            now = time.time()
            wait = self.submit_interval - (now - self.__class__._last_submit_ts)
            if wait > 0:
                logger.info(f"[wanx] rate-limit wait {wait:.1f}s before submit")
                await asyncio.sleep(wait)

            self.__class__._last_submit_ts = time.time()

            try:
                resp = await client.post(self._SUBMIT_URL, headers=headers, json=payload)
            except httpx.HTTPError as e:
                logger.warning(f"[wanx] submit network error (attempt {attempt+1}): {e}")
                if attempt < self.max_retries:
                    await asyncio.sleep(3.0)
                    continue
                raise

            if resp.status_code == 429:
                # 限流：等待后重试
                retry_after = float(resp.headers.get("Retry-After", "5"))
                logger.warning(
                    f"[wanx] 429 rate limited (attempt {attempt+1}/{self.max_retries+1}), "
                    f"waiting {retry_after}s"
                )
                if attempt < self.max_retries:
                    await asyncio.sleep(retry_after)
                    continue
                logger.error(f"[wanx] 429 exhausted retries, body={resp.text[:300]}")
                self.__class__.last_error_type = "rate_limited"
                self.__class__.last_error_message = "通义万相限流，请稍后重试"
                return {}

            if resp.status_code == 400:
                # 解析响应体，区分欠费 / 参数错误
                body_text = resp.text[:500]
                try:
                    body_json = resp.json()
                    err_code = str(body_json.get("code", ""))
                    err_msg = str(body_json.get("message", ""))
                except Exception:
                    err_code = ""
                    err_msg = body_text

                if err_code == "Arrearage" or "arrearage" in err_msg.lower() or "余额" in err_msg:
                    # 欠费：不重试，标记错误类型供前端通知
                    logger.error(
                        f"[wanx] 400 Arrearage (账号欠费): code={err_code}, "
                        f"message={err_msg}"
                    )
                    self.__class__.last_error_type = "arrearage"
                    self.__class__.last_error_message = f"通义万相账号欠费: {err_msg}"
                    return {}

                # 其他参数错误：不重试
                logger.error(
                    f"[wanx] 400 Bad Request, code={err_code}, body={body_text}, "
                    f"prompt[:100]={payload.get('input', {}).get('prompt', '')[:100]}"
                )
                self.__class__.last_error_type = "bad_request"
                self.__class__.last_error_message = f"参数错误: {err_msg or body_text}"
                return {}

            if resp.status_code == 401 or resp.status_code == 403:
                # 认证失败 / 无权限
                logger.error(
                    f"[wanx] HTTP {resp.status_code} (认证/权限错误), body={resp.text[:300]}"
                )
                self.__class__.last_error_type = "auth_failed"
                self.__class__.last_error_message = "API Key 无效或无权限"
                return {}

            if resp.status_code >= 400:
                logger.error(
                    f"[wanx] HTTP {resp.status_code}, body={resp.text[:500]}"
                )
                self.__class__.last_error_type = "api_error"
                self.__class__.last_error_message = f"HTTP {resp.status_code}"
                return {}

            data = resp.json()
            if data.get("code"):
                err_code = str(data.get("code", ""))
                err_msg = str(data.get("message", ""))
                logger.error(
                    f"[wanx] API error: code={err_code}, message={err_msg}"
                )
                self.__class__.last_error_type = "api_error"
                self.__class__.last_error_message = f"{err_code}: {err_msg}"
                return {}

            # 成功：清空错误标记
            self.__class__.last_error_type = None
            self.__class__.last_error_message = ""
            return data

        return {}

    async def generate(
        self, prompt: str, size: str = "1080x1440", count: int = 1
    ) -> list[bytes]:
        """生成图片：提交任务 → 轮询 → 下载。

        通义万相单次任务支持 n=1~4，直接一次提交。
        一次任务可生成多张图片，避免并发提交触发限流。
        """
        wanx_size = _to_wanx_size(size)

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "X-DashScope-Async": "enable",
        }
        payload = {
            "model": self.model,
            "input": {"prompt": prompt},
            "parameters": {"n": count, "size": wanx_size},
        }

        async with httpx.AsyncClient(
            timeout=httpx.Timeout(self.timeout),
            headers={"User-Agent": "multi-agent-xhs-platform/1.0"},
        ) as client:
            # ① 提交任务（带频率限制和重试）
            logger.info(
                f"[wanx] submitting task: model={self.model}, size={wanx_size}, "
                f"n={count}, prompt[:60]={prompt[:60]}"
            )
            data = await self._submit_with_rate_limit(client, headers, payload)

            if not data:
                return []

            task_id = data.get("output", {}).get("task_id")
            if not task_id:
                logger.error(f"[wanx] no task_id in response: {data}")
                return []

            logger.info(f"[wanx] task submitted: {task_id}")

            # ② 轮询任务状态
            task_url = self._TASK_URL.format(task_id=task_id)
            elapsed = 0.0
            while elapsed < self.poll_max_wait:
                await asyncio.sleep(self.poll_interval)
                elapsed += self.poll_interval

                try:
                    task_resp = await client.get(
                        task_url,
                        headers={"Authorization": f"Bearer {self.api_key}"},
                    )
                    task_resp.raise_for_status()
                except httpx.HTTPStatusError as e:
                    logger.warning(
                        f"[wanx] poll failed: {e.response.status_code}, "
                        f"retrying..."
                    )
                    continue

                task_data = task_resp.json()
                status = task_data.get("output", {}).get("task_status", "")

                logger.info(
                    f"[wanx] polling task {task_id}: status={status}, "
                    f"elapsed={elapsed:.1f}s"
                )

                if status == "SUCCEEDED":
                    results = task_data.get("output", {}).get("results", [])
                    image_urls = [r.get("url") for r in results if r.get("url")]
                    logger.info(
                        f"[wanx] task {task_id} succeeded: "
                        f"{len(image_urls)} images"
                    )
                    # ③ 下载图片
                    images = await self._download_images(client, image_urls)
                    return images

                elif status in ("FAILED", "CANCELED", "UNKNOWN"):
                    error = task_data.get("output", {}).get("message", "unknown")
                    logger.error(f"[wanx] task {task_id} {status}: {error}")
                    self.__class__.last_error_type = "task_failed"
                    self.__class__.last_error_message = f"任务{status}: {error}"
                    return []

            logger.warning(
                f"[wanx] task {task_id} timeout after {self.poll_max_wait}s"
            )
            self.__class__.last_error_type = "timeout"
            self.__class__.last_error_message = f"任务轮询超时 ({self.poll_max_wait}s)"
            return []

    async def _download_images(
        self, client: httpx.AsyncClient, urls: list[str]
    ) -> list[bytes]:
        """并发下载图片 URL → bytes。"""
        async def _download_one(url: str) -> bytes | None:
            try:
                resp = await client.get(url, timeout=httpx.Timeout(60.0))
                resp.raise_for_status()
                img_bytes = resp.content
                logger.info(
                    f"[wanx] downloaded: {len(img_bytes)} bytes from {url[:60]}..."
                )
                return img_bytes
            except Exception as e:
                logger.error(f"[wanx] download failed for {url[:60]}: {e}")
                return None

        results = await asyncio.gather(*[_download_one(u) for u in urls])
        return [img for img in results if img is not None]


# ----------------------------------------------------------------------
# Pollinations Adapter（备用，国内可能需要代理）
# ----------------------------------------------------------------------


_POLLINATIONS_BASE = "https://image.pollinations.ai/prompt"
_DEFAULT_MODEL = "z-image-turbo"


class PollinationsAdapter(ImageGenAdapter):
    """Pollinations.ai 免费图片生成（无需 API key）。

    注意：国内网络可能无法直接访问，需要配置 HTTP 代理。
    """

    def __init__(
        self,
        model: str = _DEFAULT_MODEL,
        timeout: float = 60.0,
        nologo: bool = True,
        proxy: str | None = None,
    ) -> None:
        self.model = model
        self.timeout = timeout
        self.nologo = nologo
        self.proxy = proxy

    async def generate(
        self, prompt: str, size: str = "1080x1440", count: int = 1
    ) -> list[bytes]:
        """生成图片，返回 JPEG bytes 列表。"""
        width, height = _parse_pollinations_size(size)
        client_kwargs = {
            "timeout": httpx.Timeout(self.timeout),
            "headers": {"User-Agent": "multi-agent-xhs-platform/1.0"},
        }
        if self.proxy:
            client_kwargs["proxy"] = self.proxy

        client = httpx.AsyncClient(**client_kwargs)

        async def _fetch_one(idx: int) -> bytes | None:
            seed = random.randint(1, 999999999)
            encoded_prompt = quote(prompt, safe="")
            params = {
                "width": str(width),
                "height": str(height),
                "seed": str(seed),
                "model": self.model,
            }
            if self.nologo:
                params["nologo"] = "true"

            url = f"{_POLLINATIONS_BASE}/{encoded_prompt}"
            try:
                resp = await client.get(url, params=params, follow_redirects=True)
                resp.raise_for_status()
                content_type = resp.headers.get("content-type", "")
                if not content_type.startswith("image/"):
                    logger.error(
                        f"[pollinations] idx={idx} unexpected content-type: {content_type}"
                    )
                    return None
                img_bytes = resp.content
                logger.info(
                    f"[pollinations] idx={idx} generated: {len(img_bytes)} bytes"
                )
                return img_bytes
            except Exception as e:
                logger.error(f"[pollinations] idx={idx} failed: {e}")
                return None

        try:
            tasks = [_fetch_one(i) for i in range(count)]
            results = await asyncio.gather(*tasks)
            images = [img for img in results if img is not None]
            return images
        finally:
            await client.aclose()


# ----------------------------------------------------------------------
# 工厂函数：根据配置自动选择 adapter
# ----------------------------------------------------------------------


def get_default_adapter() -> ImageGenAdapter | None:
    """根据环境变量自动选择可用的图片生成 adapter。

    优先级：
    1. DASHSCOPE_API_KEY 已配置 → WanxAdapter（国内直连）
    2. HTTP_PROXY/HTTPS_PROXY 已配置 → PollinationsAdapter（走代理）
    3. 都没配置 → 返回 None（调用方需处理）

    Key 读取顺序：
    - 先从 app.config.Settings（pydantic-settings 会自动读 .env）
    - 再从 os.getenv（兜底）
    """
    import os

    # ① 优先从 Settings 读取（pydantic-settings 自动加载 .env）
    dashscope_key = ""
    try:
        from app.config import get_settings
        dashscope_key = get_settings().dashscope_api_key or ""
    except Exception:
        pass

    # ② 兜底从 os.getenv 读取
    if not dashscope_key:
        dashscope_key = os.getenv("DASHSCOPE_API_KEY", "").strip()

    if dashscope_key:
        # 从配置读取模型名称（默认 wanx2.1-t2i-turbo，性价比最高）
        wanx_model = "wanx2.1-t2i-turbo"
        try:
            from app.config import get_settings
            wanx_model = get_settings().wanx_model or "wanx2.1-t2i-turbo"
        except Exception:
            pass
        logger.info(
            f"[image_gen] using WanxAdapter (dashscope, model={wanx_model}, "
            f"key={dashscope_key[:8]}...)"
        )
        return WanxAdapter(api_key=dashscope_key, model=wanx_model)

    # ③ Pollinations + 代理
    proxy = os.getenv("HTTPS_PROXY") or os.getenv("HTTP_PROXY") or ""
    if proxy:
        logger.info(f"[image_gen] using PollinationsAdapter with proxy: {proxy}")
        return PollinationsAdapter(proxy=proxy)

    # ④ Pollinations 无代理（国内可能超时）
    logger.warning(
        "[image_gen] no DASHSCOPE_API_KEY and no proxy, "
        "falling back to Pollinations (may timeout in China)"
    )
    return PollinationsAdapter()