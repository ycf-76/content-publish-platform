"""Video generation adapters.

设计依据：
  Easel ai_video.py 的三层架构（Provider 能力协议 + 异步任务统一流程 + 多 provider 可插拔），
  拓展为你项目的 Adapter 抽象基类模式（与 ImageGenAdapter / WanxAdapter 同构）。

拓展点（相比 Easel ai_video.py 的改进）：
  1. 异步 I/O：Easel 用 urllib.request 同步阻塞 → 本模块用 httpx.AsyncClient 异步非阻塞
     （与你项目 WanxAdapter 一致）
  2. 结构化错误：Easel fail() → sys.exit(1) 进程级退出 → 本模块返回结构化错误 +
     last_error_type 类变量（与 WanxAdapter 的欠费/限流分类模式一致）
  3. 配置来源：Easel os.environ + .env 手动读 → 本模块接受构造参数注入
     （由 Settings pydantic 提供，类型安全、IDE 可补全）
  4. 输出格式：Easel 写文件到 outputs/ → 本模块返回 bytes，由 Skill 层存 asset_library
     （你项目 asset_library 的用户级隔离模式）

Provider 能力协议（依据：Easel ai_video.py L83-109 PROVIDER_CAPABILITIES）：
  native_audio:     该 provider 能否在生成视频时同步产出音频
  dialogue:         能否按 prompt 尝试生成画内对白
  dialogue_faithful:能否逐字忠实生成指定台词（多数模型做不到，保守 False）
  audio_reference:  能否传入参考音频
  audio_field:      请求中控制音频的字段名（如 "generate_audio"）
  audio_location:   字段放在 "root" 还是 "parameters"
  audio_default:    是否默认开启音频（无需显式传字段）
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import logging
import time
from abc import ABC, abstractmethod
from typing import Any, Literal

import httpx

logger = logging.getLogger(__name__)

# P1-9/10/11 修复（2026-10-13，依据阿里云官方文档）：
# 万相 t2v 的 size 必须是具体分辨率数值（文档原话："必须设置为具体数值
# (如 1280720)，而不是 1:1 或 480P"），且可用档位依赖 model：
#   wan2.1-t2v-turbo：480P/720P 全部分辨率，默认 1280720(720P)
# 720P 档合法值：1280720(16:9) / 7201280(9:16) / 960960(1:1)
# 480P 档合法值：832480(16:9) / 480832(9:16) / 624624(1:1)
_RATIO_TO_DASHSCOPE_T2V_SIZE = {
    "9:16": "7201280",
    "16:9": "1280720",
    "1:1": "960960",
}

# 万相 i2v 不用 size——分辨率参数名是 resolution（档位字符串），
# 且宽高比自动跟随首帧图（文档：模型自动缩放至相近总像素）。
# wan2.1-i2v-turbo 可选 480P/720P；wan2.1-i2v-plus 仅 720P。
_DASHSCOPE_I2V_RESOLUTION = "720P"

DEFAULT_DASHSCOPE_BASE = "https://dashscope.aliyuncs.com/api/v1"
DEFAULT_KLING_BASE = "https://api.klingai.com"
DEFAULT_ARK_BASE = "https://ark.cn-beijing.volces.com/api/v3"


async def _poll(
    client: httpx.AsyncClient,
    url: str,
    headers: dict[str, str],
    poll_interval: float = 2.0,
    max_wait: float = 300.0,
    status_path: tuple[str, ...] = ("output", "task_status"),
    done: tuple[str, ...] = ("SUCCEEDED",),
    bad: tuple[str, ...] = ("FAILED", "CANCELED", "UNKNOWN"),
    payload: dict[str, Any] | None = None,
    on_progress: Any = None,
) -> dict[str, Any]:
    """异步轮询任务状态直到完成/失败/超时。

    依据：Easel _poll()（ai_video.py L371-397），参数化 status_path/done/bad。
    拓展：async + httpx 替代同步 urllib。
    on_progress: 可选回调 (elapsed, max_wait, status) → None，用于 SSE 进度推送。
    """
    elapsed = 0.0
    while elapsed < max_wait:
        await asyncio.sleep(poll_interval)
        elapsed += poll_interval
        try:
            if payload:
                resp = await client.get(url, headers=headers, params=payload)
            else:
                resp = await client.get(url, headers=headers)
            resp.raise_for_status()
        except httpx.HTTPStatusError as e:
            logger.warning(f"[video] poll HTTP {e.response.status_code}, retrying...")
            continue
        except httpx.HTTPError as e:
            logger.warning(f"[video] poll network error: {e}, retrying...")
            continue

        result = resp.json()
        node: Any = result
        for k in status_path:
            node = node.get(k, {}) if isinstance(node, dict) else {}
        status = str(node).upper() if isinstance(node, str) else ""

        logger.info(f"[video] polling: status={status or '?'}, elapsed={elapsed:.0f}s")

        if on_progress:
            try:
                await on_progress(elapsed, max_wait, status)
            except Exception:
                pass

        if status in done:
            return result
        if status in bad:
            raise VideoGenError(f"task_{status.lower()}", f"任务{status}：{json.dumps(result)[:300]}")

    raise VideoGenError("timeout", f"轮询超时 ({max_wait}s)")


def _find_video_url(data: dict[str, Any]) -> str | None:
    """从任务完成响应中提取视频 URL。

    依据：Easel _find_video_url()，按优先级搜索多种嵌套路径：
      output.video_url → output.video → content.video_url → data.url → url
    拓展：加 content.video_url（Ark/Seedance 响应格式）。
    """
    out = data.get("output", data.get("data", data.get("content", {})))
    for key in ("video_url", "video"):
        url = out.get(key)
        if isinstance(url, str) and url.startswith("http"):
            return url
    for key in ("url",):
        url = data.get(key)
        if isinstance(url, str) and url.startswith("http"):
            return url
    return None


async def _download_video(client: httpx.AsyncClient, url: str) -> bytes:
    """下载视频 URL → bytes。依据：Easel download_video()，拓展为异步。"""
    resp = await client.get(url, timeout=httpx.Timeout(120.0, connect=30.0))
    resp.raise_for_status()
    return resp.content


class VideoGenError(Exception):
    """视频生成错误，携带 error_type 供调用方分类处理。

    依据：Easel fail() → sys.exit()，拓展为结构化异常（与 WanxAdapter.last_error_type 同模式）。
    """
    def __init__(self, error_type: str, message: str):
        self.error_type = error_type
        self.message = message
        super().__init__(message)


class VideoGenAdapter(ABC):
    """视频生成适配器抽象基类。

    设计依据：与你项目 ImageGenAdapter(ABC) 同构（image_gen.py L67-82），
    拓展为视频场景（text2video / image2video）。
    """

    capabilities: dict[str, Any] = {
        "native_audio": False,
        "dialogue": False,
        "dialogue_faithful": False,
        "audio_reference": False,
    }

    last_error_type: str | None = None
    last_error_message: str = ""

    @abstractmethod
    async def text2video(
        self,
        prompt: str,
        *,
        ratio: str = "9:16",
        duration: float = 5.0,
        model: str | None = None,
        on_progress: Any = None,
    ) -> bytes:
        """文生视频，返回视频文件 bytes。"""
        ...

    @abstractmethod
    async def image2video(
        self,
        image: str,
        prompt: str = "",
        *,
        ratio: str = "9:16",
        duration: float = 5.0,
        model: str | None = None,
        last_frame_url: str | None = None,
        on_progress: Any = None,
    ) -> bytes:
        """图生视频，image 为 URL 或 base64 data URI。返回视频文件 bytes。

        last_frame_url：尾帧图片 URL（仅 Seedance i2v 支持），其他 provider 忽略。
        """
        ...

    async def check(self) -> dict[str, bool]:
        """离线校验配置（不发请求）。依据：Easel cmd_check()。"""
        return {"configured": True}


class DashScopeVideoAdapter(VideoGenAdapter):
    """通义万相视频生成（阿里云百炼）。

    依据：Easel generate_dashscope()（ai_video.py L399-432）。
    流程：POST video-synthesis → 轮询 /tasks/{id} → 下载 video_url。
    与你项目 WanxAdapter 同生态（复用 DASHSCOPE_API_KEY）。
    """

    capabilities = {
        "native_audio": False,
        "dialogue": False,
        "dialogue_faithful": False,
        "audio_reference": False,
    }

    def __init__(
        self,
        api_key: str,
        model: str = "wanx2.1-t2v-turbo",
        base_url: str = DEFAULT_DASHSCOPE_BASE,
        timeout: float = 30.0,
        poll_interval: float = 2.0,
        poll_max_wait: float = 300.0,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.poll_interval = poll_interval
        self.poll_max_wait = poll_max_wait

    async def _generate(
        self,
        endpoint: str,
        payload: dict[str, Any],
        client: httpx.AsyncClient,
        on_progress: Any = None,
    ) -> bytes:
        """通用提交 → 轮询 → 下载流程。依据：Easel generate_dashscope() L413-432。"""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "X-DashScope-Async": "enable",
        }

        logger.info(f"[dashscope-video] submitting to {endpoint}, model={self.model}")
        resp = await client.post(endpoint, headers=headers, json=payload)

        if resp.status_code == 400:
            body = resp.text[:500]
            self.__class__.last_error_type = "bad_request"
            self.__class__.last_error_message = f"参数错误: {body}"
            raise VideoGenError("bad_request", self.__class__.last_error_message)

        if resp.status_code == 429:
            self.__class__.last_error_type = "rate_limited"
            self.__class__.last_error_message = "通义万相限流，请稍后重试"
            raise VideoGenError("rate_limited", self.__class__.last_error_message)

        if resp.status_code in (401, 403):
            self.__class__.last_error_type = "auth_failed"
            self.__class__.last_error_message = "API Key 无效或无权限"
            raise VideoGenError("auth_failed", self.__class__.last_error_message)

        if resp.status_code >= 400:
            self.__class__.last_error_type = "api_error"
            self.__class__.last_error_message = f"HTTP {resp.status_code}: {resp.text[:300]}"
            raise VideoGenError("api_error", self.__class__.last_error_message)

        data = resp.json()
        task_id = (data.get("output") or {}).get("task_id")
        if not task_id:
            msg = data.get("message", json.dumps(data)[:300])
            self.__class__.last_error_type = "submit_failed"
            self.__class__.last_error_message = f"提交失败: {msg}"
            raise VideoGenError("submit_failed", self.__class__.last_error_message)

        logger.info(f"[dashscope-video] task submitted: {task_id}")

        task_url = f"{self.base_url}/tasks/{task_id}"
        poll_headers = {"Authorization": f"Bearer {self.api_key}"}
        try:
            task = await _poll(
                client, task_url, poll_headers,
                self.poll_interval, self.poll_max_wait,
                on_progress=on_progress,
            )
        except VideoGenError:
            raise
        except Exception as e:
            self.__class__.last_error_type = "poll_error"
            self.__class__.last_error_message = str(e)
            raise VideoGenError("poll_error", str(e))

        url = _find_video_url(task)
        if not url:
            self.__class__.last_error_type = "no_video_url"
            self.__class__.last_error_message = "任务完成但未找到视频 URL"
            raise VideoGenError("no_video_url", self.__class__.last_error_message)

        video_bytes = await _download_video(client, url)
        logger.info(f"[dashscope-video] downloaded: {len(video_bytes)} bytes")

        self.__class__.last_error_type = None
        self.__class__.last_error_message = ""
        return video_bytes

    async def text2video(
        self,
        prompt: str,
        *,
        ratio: str = "9:16",
        duration: float = 5.0,
        model: str | None = None,
        on_progress: Any = None,
    ) -> bytes:
        """文生视频。依据：Easel generate_dashscope() L399-432，text2video 分支。

        P1-9/11 修复（2026-10-13，官方文档）：
          - duration 是 integer；wan2.1-t2v-turbo/plus 固定 5s 不支持修改，
            旧代码传 float 5.0 有类型报错风险
          - size 必须是具体分辨率数值（7201280 等），旧代码传 "9*16" 非法
        """
        m = model or self.model
        endpoint = f"{self.base_url}/services/aigc/text2video/video-synthesis"
        params: dict[str, Any] = {}
        # wan2.1-t2v-turbo/plus 固定 5s；新模型（wan2.5/2.6）才支持其他时长，
        # 这里对已知模型钳到 5，未知模型按 int 传（由 API 侧校验）。
        fixed_5s = ("turbo" in m or "plus" in m)
        params["duration"] = 5 if fixed_5s else max(2, int(round(duration)))
        params["size"] = _RATIO_TO_DASHSCOPE_T2V_SIZE.get(ratio, "7201280")
        payload = {"model": m, "input": {"prompt": prompt}, "parameters": params}

        async with httpx.AsyncClient(
            timeout=httpx.Timeout(self.timeout),
            headers={"User-Agent": "multi-agent-xhs-platform/1.0"},
        ) as client:
            return await self._generate(endpoint, payload, client, on_progress=on_progress)

    async def image2video(
        self,
        image: str,
        prompt: str = "",
        *,
        ratio: str = "9:16",
        duration: float = 5.0,
        model: str | None = None,
        last_frame_url: str | None = None,
        on_progress: Any = None,
    ) -> bytes:
        """图生视频。依据：Easel generate_dashscope() L403-404，image2video 分支。

        P1-9/11 修复（2026-10-13，官方文档"万相-图生视频-基于首帧"）：
          - 分辨率参数名是 resolution（档位 "720P"），不是 size；
            宽高比自动跟随首帧图，旧代码传 size="9*16" 既错名又错值
          - duration 是 integer；wan2.1-i2v-plus 固定 5s，
            wan2.1-i2v-turbo 可选 3/4/5，钳到 [3,5]
        """
        m = model or self.model
        endpoint = f"{self.base_url}/services/aigc/image2video/video-synthesis"
        params: dict[str, Any] = {}
        params["resolution"] = _DASHSCOPE_I2V_RESOLUTION
        fixed_5s = "plus" in m
        params["duration"] = 5 if fixed_5s else max(3, min(5, int(round(duration))))
        input_block: dict[str, Any] = {"img_url": image}
        if prompt:
            input_block["prompt"] = prompt
        payload = {"model": m, "input": input_block, "parameters": params}

        async with httpx.AsyncClient(
            timeout=httpx.Timeout(self.timeout),
            headers={"User-Agent": "multi-agent-xhs-platform/1.0"},
        ) as client:
            return await self._generate(endpoint, payload, client, on_progress=on_progress)

    async def check(self) -> dict[str, bool]:
        return {"configured": bool(self.api_key)}


def _kling_duration(model: str, duration: float) -> str:
    """Kling duration → 字符串枚举 "5"/"10"（P1-10 修复，2026-10-13 官方文档）。

    duration 是字符串枚举而非数字。时长支持依赖模型：
      - kling-v1/1-5/1-6/v2-1-master/v2-5-turbo：仅 5s
      - kling-v2-6：5/10
      - kling-v3-0 系列：3-15s
    保守策略：仅 v2-6 / v3 系列放行 "10"（其余模型传 10 会被拒），
    v3 且要求 ≥6s 才给 "10"；其余一律 "5"。
    """
    m = model or ""
    long_ok = any(tag in m for tag in ("v3", "v2-6", "v2.6"))
    if long_ok and int(round(duration)) >= 6:
        return "10"
    return "5"


class KlingVideoAdapter(VideoGenAdapter):
    """快手可灵视频生成。

    依据：Easel generate_kling()（ai_video.py L538-571）+ _kling_jwt()（L529-535）。
    JWT 鉴权：access_key + secret_key → HS256 JWT → Bearer token。
    """

    capabilities = {
        "native_audio": False,
        "dialogue": False,
        "dialogue_faithful": False,
        "audio_reference": False,
    }

    def __init__(
        self,
        access_key: str,
        secret_key: str,
        model: str = "kling-v1",
        base_url: str = DEFAULT_KLING_BASE,
        timeout: float = 30.0,
        poll_interval: float = 2.0,
        poll_max_wait: float = 300.0,
    ) -> None:
        self.access_key = access_key
        self.secret_key = secret_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.poll_interval = poll_interval
        self.poll_max_wait = poll_max_wait

    @staticmethod
    def _jwt(access_key: str, secret_key: str) -> str:
        """生成 Kling JWT token。依据：Easel _kling_jwt()（ai_video.py L529-535）。"""
        def b64url(data: bytes) -> str:
            return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")

        header = b64url(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
        now = int(time.time())
        payload = b64url(json.dumps({"iss": access_key, "exp": now + 1800, "nbf": now - 5}).encode())
        signing_input = f"{header}.{payload}".encode()
        sig = hmac.new(secret_key.encode(), signing_input, hashlib.sha256).digest()
        return f"{header}.{payload}.{b64url(sig)}"

    async def _generate(
        self,
        endpoint: str,
        payload: dict[str, Any],
        client: httpx.AsyncClient,
        on_progress: Any = None,
    ) -> bytes:
        """通用提交 → 轮询 → 下载流程。依据：Easel generate_kling() L548-571。"""
        token = self._jwt(self.access_key, self.secret_key)
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

        logger.info(f"[kling] submitting to {endpoint}, model={self.model}")
        resp = await client.post(endpoint, headers=headers, json=payload)

        if resp.status_code >= 400:
            self.__class__.last_error_type = "api_error"
            self.__class__.last_error_message = f"HTTP {resp.status_code}: {resp.text[:300]}"
            raise VideoGenError("api_error", self.__class__.last_error_message)

        result = resp.json()
        data = result.get("data") or {}
        task_id = data.get("task_id") or result.get("task_id")
        if not task_id:
            self.__class__.last_error_type = "submit_failed"
            self.__class__.last_error_message = f"提交失败: {json.dumps(result)[:300]}"
            raise VideoGenError("submit_failed", self.__class__.last_error_message)

        logger.info(f"[kling] task submitted: {task_id}")

        poll_url = f"{endpoint}/{task_id}"
        try:
            task = await _poll(
                client, poll_url, headers,
                self.poll_interval, self.poll_max_wait,
                status_path=("data", "task_status"),
                done=("SUCCEED", "SUCCEEDED", "SUCCESS"),
                on_progress=on_progress,
            )
        except VideoGenError:
            raise
        except Exception as e:
            self.__class__.last_error_type = "poll_error"
            self.__class__.last_error_message = str(e)
            raise VideoGenError("poll_error", str(e))

        url = _find_video_url(task)
        if not url:
            self.__class__.last_error_type = "no_video_url"
            self.__class__.last_error_message = "任务完成但未找到视频 URL"
            raise VideoGenError("no_video_url", self.__class__.last_error_message)

        video_bytes = await _download_video(client, url)
        logger.info(f"[kling] downloaded: {len(video_bytes)} bytes")

        self.__class__.last_error_type = None
        self.__class__.last_error_message = ""
        return video_bytes

    async def text2video(
        self,
        prompt: str,
        *,
        ratio: str = "9:16",
        duration: float = 5.0,
        model: str | None = None,
        on_progress: Any = None,
    ) -> bytes:
        """文生视频。依据：Easel generate_kling() L543-544，text2video 分支。

        P1-10 修复（2026-10-13，官方接口文档）：duration 是**字符串枚举**
        "5"/"10"（旧代码 str(5.0)="5.0" 非法），且 kling-v1/1-5/1-6/v2-5-turbo
        仅支持 5s（kling-v3 才支持 3-15s）。
        """
        m = model or self.model
        endpoint = f"{self.base_url}/v1/videos/text2video"
        payload: dict[str, Any] = {"prompt": prompt}
        if m:
            payload["model_name"] = m
        payload["duration"] = _kling_duration(m, duration)
        if ratio:
            payload["aspect_ratio"] = ratio

        async with httpx.AsyncClient(
            timeout=httpx.Timeout(self.timeout),
            headers={"User-Agent": "multi-agent-xhs-platform/1.0"},
        ) as client:
            return await self._generate(endpoint, payload, client, on_progress=on_progress)

    async def image2video(
        self,
        image: str,
        prompt: str = "",
        *,
        ratio: str = "9:16",
        duration: float = 5.0,
        model: str | None = None,
        last_frame_url: str | None = None,
        on_progress: Any = None,
    ) -> bytes:
        """图生视频。依据：Easel generate_kling() L543，image2video 分支。

        duration 修同 text2video：字符串枚举 "5"/"10"，见 _kling_duration。
        """
        m = model or self.model
        endpoint = f"{self.base_url}/v1/videos/image2video"
        payload: dict[str, Any] = {"image": image, "prompt": prompt or ""}
        if m:
            payload["model_name"] = m
        payload["duration"] = _kling_duration(m, duration)
        if ratio:
            payload["aspect_ratio"] = ratio

        async with httpx.AsyncClient(
            timeout=httpx.Timeout(self.timeout),
            headers={"User-Agent": "multi-agent-xhs-platform/1.0"},
        ) as client:
            return await self._generate(endpoint, payload, client, on_progress=on_progress)

    async def check(self) -> dict[str, bool]:
        return {"configured": bool(self.access_key and self.secret_key)}


class ArkVideoAdapter(VideoGenAdapter):
    """火山引擎 Seedance 视频生成。

    依据：Easel generate_ark()（ai_video.py L435-468）。
    特点：content 数组格式（text + image_url），status_path=("status",)。
    """

    capabilities = {
        "native_audio": True,
        "dialogue": True,
        "dialogue_faithful": False,
        "audio_reference": False,
        "audio_field": "generate_audio",
        "audio_location": "root",
    }

    def __init__(
        self,
        api_key: str,
        model: str = "",
        base_url: str = DEFAULT_ARK_BASE,
        timeout: float = 30.0,
        poll_interval: float = 2.0,
        poll_max_wait: float = 300.0,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.poll_interval = poll_interval
        self.poll_max_wait = poll_max_wait

    async def _generate(
        self,
        payload: dict[str, Any],
        client: httpx.AsyncClient,
        on_progress: Any = None,
    ) -> bytes:
        """通用提交 → 轮询 → 下载流程。依据：Easel generate_ark() L448-468。"""
        endpoint = f"{self.base_url}/contents/generations/tasks"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        logger.info(f"[ark] submitting to {endpoint}, model={self.model}")
        resp = await client.post(endpoint, headers=headers, json=payload)

        if resp.status_code >= 400:
            self.__class__.last_error_type = "api_error"
            self.__class__.last_error_message = f"HTTP {resp.status_code}: {resp.text[:300]}"
            raise VideoGenError("api_error", self.__class__.last_error_message)

        result = resp.json()
        task_id = result.get("id") or (result.get("data") or {}).get("id")
        if not task_id:
            self.__class__.last_error_type = "submit_failed"
            self.__class__.last_error_message = f"提交失败: {json.dumps(result)[:300]}"
            raise VideoGenError("submit_failed", self.__class__.last_error_message)

        logger.info(f"[ark] task submitted: {task_id}")

        poll_url = f"{endpoint}/{task_id}"
        try:
            task = await _poll(
                client, poll_url, headers,
                self.poll_interval, self.poll_max_wait,
                status_path=("status",),
                on_progress=on_progress,
            )
        except VideoGenError:
            raise
        except Exception as e:
            self.__class__.last_error_type = "poll_error"
            self.__class__.last_error_message = str(e)
            raise VideoGenError("poll_error", str(e))

        url = _find_video_url(task)
        if not url:
            self.__class__.last_error_type = "no_video_url"
            self.__class__.last_error_message = "任务完成但未找到视频 URL"
            raise VideoGenError("no_video_url", self.__class__.last_error_message)

        video_bytes = await _download_video(client, url)
        logger.info(f"[ark] downloaded: {len(video_bytes)} bytes")

        self.__class__.last_error_type = None
        self.__class__.last_error_message = ""
        return video_bytes

    async def text2video(
        self,
        prompt: str,
        *,
        ratio: str = "9:16",
        duration: float = 5.0,
        model: str | None = None,
        on_progress: Any = None,
    ) -> bytes:
        """文生视频。依据：Easel generate_ark() L440-442，content 数组格式。"""
        m = model or self.model
        content: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
        payload: dict[str, Any] = {"model": m, "content": content}
        if ratio:
            payload["ratio"] = ratio
        if duration:
            payload["duration"] = int(duration)

        async with httpx.AsyncClient(
            timeout=httpx.Timeout(self.timeout),
            headers={"User-Agent": "multi-agent-xhs-platform/1.0"},
        ) as client:
            return await self._generate(payload, client, on_progress=on_progress)

    async def image2video(
        self,
        image: str,
        prompt: str = "",
        *,
        ratio: str = "9:16",
        duration: float = 5.0,
        model: str | None = None,
        last_frame_url: str | None = None,
        on_progress: Any = None,
    ) -> bytes:
        """图生视频。依据：Easel generate_ark() L441-442，content 数组含 image_url。

        Seedance i2v 要求 image_url 带 role 字段：
          - role="first_frame"：首帧图（必需）
          - role="last_frame"：尾帧图（可选，首尾帧模式增强跨镜连贯性）

        last_frame_url：尾帧图片 URL，仅 Seedance i2v 支持。
        传入后自动启用首尾帧模式，上一镜尾帧可作为下一镜首帧实现连贯过渡。
        """
        m = model or self.model
        content: list[dict[str, Any]] = [{"type": "text", "text": prompt or ""}]
        content.append({"type": "image_url", "image_url": {"url": image}, "role": "first_frame"})
        if last_frame_url:
            content.append({"type": "image_url", "image_url": {"url": last_frame_url}, "role": "last_frame"})
        payload: dict[str, Any] = {"model": m, "content": content}
        if ratio:
            payload["ratio"] = ratio
        if duration:
            payload["duration"] = int(duration)

        async with httpx.AsyncClient(
            timeout=httpx.Timeout(self.timeout),
            headers={"User-Agent": "multi-agent-xhs-platform/1.0"},
        ) as client:
            return await self._generate(payload, client, on_progress=on_progress)

    async def check(self) -> dict[str, bool]:
        return {"configured": bool(self.api_key)}


def create_video_adapter(
    provider: str,
    *,
    api_key: str = "",
    access_key: str = "",
    secret_key: str = "",
    model: str = "",
    base_url: str = "",
) -> VideoGenAdapter:
    """按 provider 名创建适配器实例。

    依据：Easel GENERATORS 字典分派模式（ai_video.py L624-630），
    拓展为面向对象工厂（与你项目 ImageGenAdapter 的使用模式一致）。
    """
    if provider == "dashscope":
        return DashScopeVideoAdapter(
            api_key=api_key,
            model=model or "wanx2.1-t2v-turbo",
            base_url=base_url or DEFAULT_DASHSCOPE_BASE,
        )
    elif provider == "kling":
        return KlingVideoAdapter(
            access_key=access_key,
            secret_key=secret_key,
            model=model or "kling-v1",
            base_url=base_url or DEFAULT_KLING_BASE,
        )
    elif provider == "ark":
        return ArkVideoAdapter(
            api_key=api_key,
            model=model or "",
            base_url=base_url or DEFAULT_ARK_BASE,
        )
    else:
        raise ValueError(f"未知的视频 provider: {provider}（支持: dashscope, kling, ark）")