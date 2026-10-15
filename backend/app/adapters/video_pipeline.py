"""统一视频生成流水线框架。

设计原则：
  1. Provider 能力协议：每个 provider 声明自己支持什么，流水线自动适配
  2. 步骤可插拔：每个步骤是独立函数，可替换/跳过/降级
  3. 音频一体化：native_audio / bgm / subtitle 全在流水线内处理
  4. 零件可缺：任何步骤失败不中断，自动降级
  5. 不改旧代码：VideoGenAdapter 保持不动，本框架在上层编排

架构：
  VideoProvider（能力协议）
    ├── DashScopeProvider  (wan2.1)
    ├── KlingProvider      (kling-v1/v2)
    └── ArkProvider        (Seedance)

  VideoPipeline（编排引擎）
    ├── plan()    → 分镜草稿（VL + LLM，快，便宜）
    ├── render()  → 从分镜生成视频（text2image + image2video + compose，慢，贵）
    ├── refine()  → 微调后重新生成（跳过 VL+LLM）
    └── enhance() → 后处理（音频 + 字幕 + 水印）

  PipelineResult（统一输出）
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol, runtime_checkable

from app.adapters.video_gen import VideoGenError

logger = logging.getLogger(__name__)


# ── 1. 能力协议 ──────────────────────────────────────────

class VideoCapability(Enum):
    TEXT_TO_VIDEO = "text2video"
    IMAGE_TO_VIDEO = "image2video"
    FIRST_LAST_FRAME = "first_last_frame"
    NATIVE_AUDIO = "native_audio"
    DIALOGUE = "dialogue"
    AUDIO_REFERENCE = "audio_reference"
    MULTI_IMAGE_INPUT = "multi_image_input"
    HIGH_RESOLUTION = "high_resolution"
    LONG_DURATION = "long_duration"


@runtime_checkable
class VideoProvider(Protocol):
    """视频生成 Provider 能力协议。

    每个 provider 实现此协议，声明自己支持的能力。
    流水线根据能力自动选择最优路径。
    """

    name: str
    capabilities: set[VideoCapability]

    async def text2video(
        self,
        prompt: str,
        *,
        ratio: str = "9:16",
        duration: float = 5.0,
        model: str | None = None,
        native_audio: bool = False,
        on_progress: Any = None,
    ) -> bytes: ...

    async def image2video(
        self,
        image: str,
        prompt: str = "",
        *,
        ratio: str = "9:16",
        duration: float = 5.0,
        model: str | None = None,
        last_frame_url: str | None = None,
        native_audio: bool = False,
        on_progress: Any = None,
    ) -> bytes: ...

    def supports(self, cap: VideoCapability) -> bool:
        return cap in self.capabilities

    async def check(self) -> dict[str, bool]:
        ...


# ── 2. Provider 适配器（桥接旧 VideoGenAdapter） ─────────

class DashScopeProvider:
    """通义万相 (wan2.1)：t2v + i2v，无首尾帧，无原生音频。"""

    def __init__(self, adapter: Any) -> None:
        self._adapter = adapter
        self.name = "dashscope"
        self.capabilities = {
            VideoCapability.TEXT_TO_VIDEO,
            VideoCapability.IMAGE_TO_VIDEO,
        }

    async def text2video(self, prompt: str, *, ratio: str = "9:16", duration: float = 5.0, model: str | None = None, native_audio: bool = False, on_progress: Any = None) -> bytes:
        return await self._adapter.text2video(prompt, ratio=ratio, duration=duration, model=model, on_progress=on_progress)

    async def image2video(self, image: str, prompt: str = "", *, ratio: str = "9:16", duration: float = 5.0, model: str | None = None, last_frame_url: str | None = None, native_audio: bool = False, on_progress: Any = None) -> bytes:
        return await self._adapter.image2video(image, prompt, ratio=ratio, duration=duration, model=model, on_progress=on_progress)

    def supports(self, cap: VideoCapability) -> bool:
        return cap in self.capabilities

    async def check(self) -> dict[str, bool]:
        return await self._adapter.check()


class KlingProvider:
    """可灵 (kling-v1/v2)：t2v + i2v，无首尾帧，无原生音频。"""

    def __init__(self, adapter: Any) -> None:
        self._adapter = adapter
        self.name = "kling"
        self.capabilities = {
            VideoCapability.TEXT_TO_VIDEO,
            VideoCapability.IMAGE_TO_VIDEO,
        }

    async def text2video(self, prompt: str, *, ratio: str = "9:16", duration: float = 5.0, model: str | None = None, native_audio: bool = False, on_progress: Any = None) -> bytes:
        return await self._adapter.text2video(prompt, ratio=ratio, duration=duration, model=model, on_progress=on_progress)

    async def image2video(self, image: str, prompt: str = "", *, ratio: str = "9:16", duration: float = 5.0, model: str | None = None, last_frame_url: str | None = None, native_audio: bool = False, on_progress: Any = None) -> bytes:
        return await self._adapter.image2video(image, prompt, ratio=ratio, duration=duration, model=model, on_progress=on_progress)

    def supports(self, cap: VideoCapability) -> bool:
        return cap in self.capabilities

    async def check(self) -> dict[str, bool]:
        return await self._adapter.check()


class ArkProvider:
    """火山引擎 Seedance：t2v + i2v + 首尾帧 + 原生音频 + 对白。"""

    def __init__(self, adapter: Any) -> None:
        self._adapter = adapter
        self.name = "ark"
        self.capabilities = {
            VideoCapability.TEXT_TO_VIDEO,
            VideoCapability.IMAGE_TO_VIDEO,
            VideoCapability.FIRST_LAST_FRAME,
            VideoCapability.NATIVE_AUDIO,
            VideoCapability.DIALOGUE,
            VideoCapability.MULTI_IMAGE_INPUT,
        }

    async def text2video(self, prompt: str, *, ratio: str = "9:16", duration: float = 5.0, model: str | None = None, native_audio: bool = False, on_progress: Any = None) -> bytes:
        kwargs: dict[str, Any] = {"ratio": ratio, "duration": duration, "model": model, "on_progress": on_progress}
        if native_audio and self.supports(VideoCapability.NATIVE_AUDIO):
            kwargs["generate_audio"] = True
        return await self._adapter.text2video(prompt, **kwargs)

    async def image2video(self, image: str, prompt: str = "", *, ratio: str = "9:16", duration: float = 5.0, model: str | None = None, last_frame_url: str | None = None, native_audio: bool = False, on_progress: Any = None) -> bytes:
        kwargs: dict[str, Any] = {"ratio": ratio, "duration": duration, "model": model, "on_progress": on_progress}
        if last_frame_url and self.supports(VideoCapability.FIRST_LAST_FRAME):
            kwargs["last_frame_url"] = last_frame_url
        if native_audio and self.supports(VideoCapability.NATIVE_AUDIO):
            kwargs["generate_audio"] = True
        return await self._adapter.image2video(image, prompt, **kwargs)

    def supports(self, cap: VideoCapability) -> bool:
        return cap in self.capabilities

    async def check(self) -> dict[str, bool]:
        return await self._adapter.check()


# ── 3. Provider 工厂 ─────────────────────────────────────

_PROVIDER_MAP: dict[str, type[DashScopeProvider | KlingProvider | ArkProvider]] = {
    "dashscope": DashScopeProvider,
    "kling": KlingProvider,
    "ark": ArkProvider,
}


def create_provider(name: str, adapter: Any) -> VideoProvider:
    """从旧 adapter 创建新 Provider 包装。"""
    cls = _PROVIDER_MAP.get(name)
    if cls is None:
        raise ValueError(f"未知 provider: {name}，可选: {list(_PROVIDER_MAP)}")
    return cls(adapter)


def resolve_provider(provider_name: str | None = None) -> VideoProvider:
    """按名称解析 provider，返回 VideoProvider 协议对象。

    自动桥接旧的 _resolve_adapter + create_provider。
    """
    from app.skills.produce.video_gen import _resolve_adapter
    adapter, name = _resolve_adapter(provider_name)
    return create_provider(name, adapter)


# ── 4. 流水线步骤结果 ────────────────────────────────────

@dataclass
class Shot:
    """单个镜头。"""
    shot_index: int = 0
    caption: str = ""
    image_prompt: str = ""
    motion_prompt: str = ""
    reference_images: list[int] = field(default_factory=list)
    duration: float = 5.0
    transition: str = "cut"
    frame_url: str = ""
    frame_source: str = ""
    clip_url: str = ""
    clip_asset_id: str = ""
    clip_mode: str = ""
    clip_coherence: str = ""
    clip_error: str = ""

    def to_dict(self) -> dict[str, Any]:
        # P2-16 修复（2026-10-13）：旧版过滤 v != 0 会把 shot_index=0 的
        # 首镜和 duration=0 的字段整个丢掉，preview 回给用户编辑时字段消失。
        # 只丢空字符串和空列表，数字 0 保留。
        return {k: v for k, v in self.__dict__.items() if v != "" and v != []}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Shot:
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class PipelineResult:
    """流水线统一输出。"""
    success: bool = False
    mode: str = "full"
    title: str = ""
    shots: list[Shot] = field(default_factory=list)
    scene_description: dict[str, Any] | None = None
    image_urls: list[str] = field(default_factory=list)
    asset_id: str = ""
    asset_url: str = ""
    video_bytes: bytes | None = None
    degradation: list[str] = field(default_factory=list)
    error: str = ""

    @property
    def video_clips(self) -> int:
        return sum(1 for s in self.shots if s.clip_mode == "video")

    @property
    def ken_burns_clips(self) -> int:
        return sum(1 for s in self.shots if s.clip_mode == "ken_burns")

    @property
    def estimated_duration(self) -> float:
        return sum(s.duration for s in self.shots)

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "success": self.success,
            "mode": self.mode,
            "title": self.title,
            "shots_count": len(self.shots),
            "video_clips": self.video_clips,
            "ken_burns_clips": self.ken_burns_clips,
            "estimated_duration": self.estimated_duration,
            "degradation": self.degradation,
        }
        if self.asset_id:
            d["asset_id"] = self.asset_id
        if self.asset_url:
            d["asset_url"] = self.asset_url
        if self.error:
            d["error"] = self.error
        if self.mode == "preview":
            d["shots"] = [s.to_dict() for s in self.shots]
            d["scene_description"] = self.scene_description
            d["image_urls"] = self.image_urls
            d["hint"] = (
                "编辑 shots 中任意镜的 image_prompt/motion_prompt/duration/transition 后，"
                "通过 refine_shots 参数传回即可生成视频。"
                "也可增删镜头（shots 列表长度可变）。"
            )
        return d


# ── 5. 流水线编排引擎 ────────────────────────────────────

@dataclass
class PipelineConfig:
    """流水线配置。"""
    ratio: str = "9:16"
    target_duration: float = 15.0
    shot_duration: float = 5.0
    style: str = "电影感"
    provider_name: str | None = None
    native_audio: bool = True
    first_last_frame: bool = True
    bgm_url: str | None = None
    subtitle_srt: str | None = None


class VideoPipeline:
    """统一视频生成流水线。

    三种调用模式：
      1. plan()    → 仅分镜预览（快，便宜）
      2. render()  → 完整生成（慢，贵）
      3. refine()  → 微调后重新生成（跳过 VL+LLM）

    每步自动根据 provider 能力选择最优路径：
      - provider 支持 FIRST_LAST_FRAME → 启用首尾帧连贯
      - provider 支持 NATIVE_AUDIO → 生成时自带音效
      - provider 不支持 → 自动跳过，不报错
    """

    def __init__(self, config: PipelineConfig) -> None:
        self.config = config
        self._provider: VideoProvider | None = None
        self._degradation: list[str] = []

    @property
    def provider(self) -> VideoProvider:
        if self._provider is None:
            self._provider = resolve_provider(self.config.provider_name)
        return self._provider

    @property
    def degradation(self) -> list[str]:
        return self._degradation

    def _should_use_first_last_frame(self) -> bool:
        return self.config.first_last_frame and self.provider.supports(VideoCapability.FIRST_LAST_FRAME)

    def _should_use_native_audio(self) -> bool:
        return self.config.native_audio and self.provider.supports(VideoCapability.NATIVE_AUDIO)

    async def plan(
        self,
        image_asset_ids: list[str],
        user_id: str,
        prompt: str,
        *,
        workflow_id: str | None = None,
        emit_step: Any = None,
    ) -> PipelineResult:
        """阶段 1：仅分镜预览。

        执行：VL 理解 → LLM 编排 → 返回分镜草稿。
        不消耗视频生成配额。
        """
        from app.skills.produce.multi_image_video import (
            _resolve_image_urls,
            _vl_understand_images,
            _generate_storyboard,
        )

        self._degradation = []

        if emit_step:
            await emit_step(1, 2, "VL理解参考图", f"分析{len(image_asset_ids)}张参考图...")

        try:
            image_urls = await _resolve_image_urls(image_asset_ids, user_id)
        except ValueError as e:
            return PipelineResult(success=False, error=str(e))

        scene_description = await _vl_understand_images(image_urls)
        if scene_description is None:
            self._degradation.append("VL理解：不可用，跳过，直接用用户描述编排")

        if emit_step:
            await emit_step(2, 2, "编排分镜脚本", "LLM 生成逐镜头脚本...")

        storyboard = await _generate_storyboard(
            scene_description=scene_description,
            user_prompt=prompt,
            target_duration=self.config.target_duration,
            shot_duration=self.config.shot_duration,
            style=self.config.style,
            num_reference_images=len(image_urls),
        )

        shots_data = storyboard.get("shots", [])
        title = storyboard.get("title", prompt[:30])

        if not shots_data:
            return PipelineResult(success=False, error="分镜脚本为空")

        shots = [Shot.from_dict(s) for s in shots_data]

        if emit_step:
            await emit_step(2, 2, "分镜预览就绪", "请编辑分镜后确认生成")

        return PipelineResult(
            success=True,
            mode="preview",
            title=title,
            shots=shots,
            scene_description=scene_description,
            image_urls=image_urls,
            degradation=self._degradation,
        )

    async def render(
        self,
        image_asset_ids: list[str],
        user_id: str,
        prompt: str,
        *,
        workflow_id: str | None = None,
        emit_step: Any = None,
    ) -> PipelineResult:
        """完整生成：plan + render。"""
        plan_result = await self.plan(
            image_asset_ids=image_asset_ids,
            user_id=user_id,
            prompt=prompt,
            workflow_id=workflow_id,
            emit_step=emit_step,
        )
        if not plan_result.success:
            return plan_result

        return await self.refine(
            shots=plan_result.shots,
            image_asset_ids=image_asset_ids,
            user_id=user_id,
            prompt=prompt,
            title=plan_result.title,
            image_urls=plan_result.image_urls,
            workflow_id=workflow_id,
            emit_step=emit_step,
        )

    async def refine(
        self,
        shots: list[Shot],
        image_asset_ids: list[str],
        user_id: str,
        prompt: str,
        title: str = "",
        image_urls: list[str] | None = None,
        *,
        workflow_id: str | None = None,
        emit_step: Any = None,
    ) -> PipelineResult:
        """从分镜生成视频（Step 3→6）。

        自动根据 provider 能力：
          - FIRST_LAST_FRAME → 首尾帧连贯
          - NATIVE_AUDIO → 生成时自带音效
        """
        from app.skills.produce.multi_image_video import (
            _resolve_image_urls,
            _generate_shot_frames,
            _generate_shot_clips,
            _compose_final,
        )

        self._degradation = []
        shots_data = [s.to_dict() for s in shots]

        if image_urls is None:
            try:
                image_urls = await _resolve_image_urls(image_asset_ids, user_id)
            except ValueError as e:
                return PipelineResult(success=False, error=str(e))

        use_flf = self._should_use_first_last_frame()
        use_audio = self._should_use_native_audio()

        if use_flf:
            logger.info(f"[pipeline] {self.provider.name} 首尾帧连贯模式：启用")
        if use_audio:
            logger.info(f"[pipeline] {self.provider.name} 原生音频模式：启用")

        # Step 3: text2image
        if emit_step:
            await emit_step(3, 6, "生成分镜关键帧", f"共{len(shots)}镜...")
        shots_data = await _generate_shot_frames(shots_data, self.config.ratio, user_id, image_urls)

        # Step 4: image2video（带能力感知）
        if emit_step:
            await emit_step(4, 6, "逐镜生成视频", f"第1/{len(shots)}镜...")
        shots_data = await _generate_shot_clips(
            shots=shots_data,
            ratio=self.config.ratio,
            shot_duration=self.config.shot_duration,
            user_id=user_id,
            provider=self.config.provider_name,
            on_progress=None,
        )

        # Step 5: compose
        if emit_step:
            await emit_step(5, 6, "拼接成片", "ffmpeg 拼接视频片段...")
        final_bytes, compose_deg = await _compose_final(
            shots=shots_data, ratio=self.config.ratio, user_id=user_id, title=title,
        )
        self._degradation.extend(compose_deg)

        if not final_bytes:
            clip_urls = [s["clip_url"] for s in shots_data if s.get("clip_url")]
            return PipelineResult(
                success=False,
                error="成片拼接失败",
                shots=[Shot.from_dict(s) for s in shots_data],
                degradation=self._degradation,
            )

        # Step 6: save + enhance
        if emit_step:
            await emit_step(6, 6, "保存交付", "存储视频素材...")

        from app.services.asset_library import save_video_asset
        asset = await save_video_asset(
            user_id=user_id,
            filename=f"{title[:20]}_pipeline.mp4",
            content_type="video/mp4",
            data=final_bytes,
            source="ai",
            metadata={
                "source": "video_pipeline",
                "provider": self.provider.name,
                "prompt": prompt[:200],
                "ratio": self.config.ratio,
                "shots_count": len(shots_data),
                "first_last_frame": use_flf,
                "native_audio": use_audio,
                "degradation": self._degradation,
            },
        )

        video_url = asset["original_url"]

        # BGM 叠加（如果配置了）
        if self.config.bgm_url:
            final_bytes, video_url = await self._overlay_bgm(
                final_bytes, video_url, self.config.bgm_url, user_id, title,
            )

        # 字幕叠加（如果配置了）
        if self.config.subtitle_srt:
            final_bytes, video_url = await self._overlay_subtitle(
                final_bytes, video_url, self.config.subtitle_srt, user_id, title,
            )

        # SSE 交付
        if workflow_id:
            from app.services.sse_bus import sse_bus
            await sse_bus.publish(workflow_id, "card_draft_ready", {
                "card_draft": {
                    "title": f"视频 - {title}",
                    "template": "video",
                    "pages": [{
                        "id": "page_video",
                        "type": "content",
                        "mediaType": "video",
                        "title": title,
                        "videoUrl": video_url,
                        "width": 1280,
                        "height": 720,
                    }],
                    "pngUrls": [],
                    "htmlUrls": [],
                },
                "png_urls": [],
                "html_urls": [],
            })

        return PipelineResult(
            success=True,
            mode="refine" if image_urls is not None else "full",
            title=title,
            shots=[Shot.from_dict(s) for s in shots_data],
            asset_id=asset.get("asset_id") or asset.get("id"),
            asset_url=video_url,
            video_bytes=final_bytes,
            degradation=self._degradation,
        )

    async def enhance(
        self,
        video_bytes: bytes,
        video_url: str,
        user_id: str,
        title: str,
        *,
        bgm_url: str | None = None,
        subtitle_srt: str | None = None,
    ) -> tuple[bytes, str]:
        """后处理：叠加 BGM + 字幕。可独立调用，对已有视频增强。"""
        result_bytes, result_url = video_bytes, video_url

        if bgm_url or self.config.bgm_url:
            result_bytes, result_url = await self._overlay_bgm(
                result_bytes, result_url, bgm_url or self.config.bgm_url, user_id, title,
            )

        if subtitle_srt or self.config.subtitle_srt:
            result_bytes, result_url = await self._overlay_subtitle(
                result_bytes, result_url, subtitle_srt or self.config.subtitle_srt, user_id, title,
            )

        return result_bytes, result_url

    async def _overlay_bgm(
        self,
        video_bytes: bytes,
        video_url: str,
        bgm_url: str,
        user_id: str,
        title: str,
    ) -> tuple[bytes, str]:
        """叠加 BGM：ffmpeg amix 混合原视频音轨 + BGM。"""
        try:
            import tempfile
            from pathlib import Path
            from app.adapters.video_compose import _ensure_ffmpeg, _subtitle_vf

            ffmpeg_path = await _ensure_ffmpeg()
            if not ffmpeg_path:
                self._degradation.append("BGM 叠加：ffmpeg 不可用，跳过")
                return video_bytes, video_url

            tmp_dir = Path(tempfile.mkdtemp(prefix="pipeline_bgm_"))
            video_path = tmp_dir / "input.mp4"
            bgm_path = tmp_dir / "bgm.mp3"
            output_path = tmp_dir / "output.mp4"

            video_path.write_bytes(video_bytes)

            import httpx
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.get(bgm_url)
                resp.raise_for_status()
                bgm_path.write_bytes(resp.content)

            import asyncio
            cmd = [
                str(ffmpeg_path), "-y",
                "-i", str(video_path),
                "-i", str(bgm_path),
                "-filter_complex", "[1:a]volume=0.3[bgm];[0:a][bgm]amix=inputs=2:duration_shortest=1[aout]",
                "-map", "0:v", "-map", "[aout]",
                "-c:v", "copy", "-c:a", "aac", "-b:a", "128k",
                "-shortest",
                str(output_path),
            ]
            proc = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await proc.communicate()
            if proc.returncode != 0:
                raise RuntimeError(f"ffmpeg amix 失败: {stderr.decode()[:200]}")

            result_bytes = output_path.read_bytes()

            from app.services.asset_library import save_video_asset
            asset = await save_video_asset(
                user_id=user_id,
                filename=f"{title[:20]}_bgm.mp4",
                content_type="video/mp4",
                data=result_bytes,
                source="ai",
                metadata={"source": "video_pipeline_bgm"},
            )
            return result_bytes, asset["original_url"]

        except Exception as e:
            self._degradation.append(f"BGM 叠加失败：{e}")
            return video_bytes, video_url

    async def _overlay_subtitle(
        self,
        video_bytes: bytes,
        video_url: str,
        srt_content: str,
        user_id: str,
        title: str,
    ) -> tuple[bytes, str]:
        """叠加字幕：ffmpeg drawtext / subtitles 滤镜。"""
        try:
            import tempfile
            from pathlib import Path
            from app.adapters.video_compose import _ensure_ffmpeg, _subtitle_vf

            ffmpeg_path = await _ensure_ffmpeg()
            if not ffmpeg_path:
                self._degradation.append("字幕叠加：ffmpeg 不可用，跳过")
                return video_bytes, video_url

            tmp_dir = Path(tempfile.mkdtemp(prefix="pipeline_sub_"))
            video_path = tmp_dir / "input.mp4"
            srt_path = tmp_dir / "sub.srt"
            output_path = tmp_dir / "output.mp4"

            video_path.write_bytes(video_bytes)
            srt_path.write_text(srt_content, encoding="utf-8")

            import asyncio
            # Windows ffmpeg 的 subtitles 滤镜吃不了绝对路径（2026-10-13 真机实测：
            # Linux 式 \: + 引号、正斜杠 + \:、filename= 三种写法全挂）。
            # 唯一可靠：cwd 切到 srt 所在目录，滤镜里只传纯文件名。
            # force_style 含单引号，包在整体单引号外会有问题，改用 sub.ass 中转：
            # srt 先转成 ass 再烧，规避 force_style 引号嵌套。
            from app.adapters.video_compose import _srt_to_ass
            ass_path = tmp_dir / "sub.ass"
            _srt_to_ass(srt_path, ass_path, 1280, 720)
            sub_vf, sub_cwd = _subtitle_vf(ass_path)
            cmd = [
                str(ffmpeg_path), "-y",
                "-i", str(video_path),
                "-vf", sub_vf,
                "-c:a", "copy",
                str(output_path),
            ]
            proc = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE,
                cwd=sub_cwd,
            )
            _, stderr = await proc.communicate()
            if proc.returncode != 0:
                raise RuntimeError(f"ffmpeg subtitles 失败: {stderr.decode()[:200]}")

            result_bytes = output_path.read_bytes()

            from app.services.asset_library import save_video_asset
            asset = await save_video_asset(
                user_id=user_id,
                filename=f"{title[:20]}_sub.mp4",
                content_type="video/mp4",
                data=result_bytes,
                source="ai",
                metadata={"source": "video_pipeline_subtitle"},
            )
            return result_bytes, asset["original_url"]

        except Exception as e:
            self._degradation.append(f"字幕叠加失败：{e}")
            return video_bytes, video_url


# ── 6. 能力报告 ──────────────────────────────────────────

def provider_capability_report(provider_name: str | None = None) -> dict[str, Any]:
    """生成 provider 能力报告，供前端展示和调试。"""
    try:
        p = resolve_provider(provider_name)
    except Exception as e:
        return {"error": str(e)}

    caps = {c.value: p.supports(c) for c in VideoCapability}
    return {
        "provider": p.name,
        "capabilities": caps,
        "features": {
            "首尾帧连贯": caps.get("first_last_frame", False),
            "原生音频": caps.get("native_audio", False),
            "对白生成": caps.get("dialogue", False),
            "参考音频": caps.get("audio_reference", False),
            "多图输入": caps.get("multi_image_input", False),
            "高分辨率": caps.get("high_resolution", False),
            "长时长": caps.get("long_duration", False),
        },
    }


# ── 7. 算力调度器 ────────────────────────────────────────

import asyncio
import time as _time


@dataclass
class ProviderSlot:
    """单个 provider 的算力槽位。"""
    name: str
    weight: float = 1.0
    max_concurrent: int = 2
    priority: int = 0
    _active: int = 0
    _total_dispatched: int = 0
    _total_failures: int = 0
    _last_failure_time: float = 0.0
    _avg_latency: float = 0.0
    _cooldown_until: float = 0.0

    @property
    def available(self) -> int:
        return max(0, self.max_concurrent - self._active)

    @property
    def is_cooled_down(self) -> bool:
        return _time.monotonic() >= self._cooldown_until

    @property
    def effective_weight(self) -> float:
        if not self.is_cooled_down:
            return 0.0
        if self._active >= self.max_concurrent:
            return 0.0
        latency_factor = 1.0 / max(self._avg_latency, 0.1) if self._avg_latency > 0 else 1.0
        failure_factor = 1.0 / (1.0 + self._total_failures)
        return self.weight * latency_factor * failure_factor * self.available

    def record_start(self) -> None:
        self._active += 1
        self._total_dispatched += 1

    def record_success(self, latency: float) -> None:
        self._active = max(0, self._active - 1)
        if self._avg_latency == 0:
            self._avg_latency = latency
        else:
            self._avg_latency = 0.7 * self._avg_latency + 0.3 * latency

    def record_failure(self, cooldown: float = 30.0) -> None:
        self._active = max(0, self._active - 1)
        self._total_failures += 1
        self._last_failure_time = _time.monotonic()
        self._cooldown_until = _time.monotonic() + cooldown

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "weight": self.weight,
            "max_concurrent": self.max_concurrent,
            "priority": self.priority,
            "active": self._active,
            "available": self.available,
            "total_dispatched": self._total_dispatched,
            "total_failures": self._total_failures,
            "avg_latency": round(self._avg_latency, 2),
            "is_cooled_down": self.is_cooled_down,
            "effective_weight": round(self.effective_weight, 4),
        }


class ComputeScheduler:
    """多 provider 算力均衡调度器。

    调度策略：加权最可用优先（Weighted-Most-Available-First）
      1. 过滤：排除冷却中、满载的 provider
      2. 排序：effective_weight 降序（权重 × 延迟因子 × 失败因子 × 可用槽位）
      3. 选择：最高 effective_weight 的 provider
      4. 兜底：全部不可用时，选冷却最早结束的

    特性：
      - 自适应：延迟低、失败少的 provider 自动获得更多流量
      - 熔断：连续失败触发冷却，冷却期不分配
      - 优先级：priority 越高越优先（同 weight 时）
      - 并发控制：每个 provider 独立 max_concurrent 限制
      - 全局并发：总 Semaphore 控制整体并发上限
    """

    def __init__(
        self,
        slots: list[ProviderSlot] | None = None,
        global_max_concurrent: int = 6,
    ) -> None:
        self._slots: dict[str, ProviderSlot] = {}
        if slots:
            for s in slots:
                self._slots[s.name] = s
        self._global_sem = asyncio.Semaphore(global_max_concurrent)
        self._global_max = global_max_concurrent

    @classmethod
    def from_config(cls, config: dict[str, Any] | None = None) -> ComputeScheduler:
        """从配置创建调度器。

        配置格式：
        {
            "providers": {
                "ark": {"weight": 2.0, "max_concurrent": 3, "priority": 10},
                "dashscope": {"weight": 1.0, "max_concurrent": 2, "priority": 5},
                "kling": {"weight": 1.0, "max_concurrent": 2, "priority": 5},
            },
            "global_max_concurrent": 6
        }
        """
        if config is None:
            config = {}
        providers_cfg = config.get("providers", {})
        slots = []
        for name, cfg in providers_cfg.items():
            slots.append(ProviderSlot(
                name=name,
                weight=cfg.get("weight", 1.0),
                max_concurrent=cfg.get("max_concurrent", 2),
                priority=cfg.get("priority", 0),
            ))
        global_max = config.get("global_max_concurrent", 6)
        return cls(slots=slots, global_max_concurrent=global_max)

    def add_provider(self, name: str, weight: float = 1.0, max_concurrent: int = 2, priority: int = 0) -> None:
        self._slots[name] = ProviderSlot(name=name, weight=weight, max_concurrent=max_concurrent, priority=priority)

    def select(self, required_caps: set[VideoCapability] | None = None) -> ProviderSlot | None:
        """选择最优 provider。

        required_caps: 如果指定，只从满足这些能力的 provider 中选。
        """
        candidates = list(self._slots.values())

        if required_caps:
            qualified_names = []
            for slot in candidates:
                try:
                    p = resolve_provider(slot.name)
                    if all(p.supports(c) for c in required_caps):
                        qualified_names.append(slot.name)
                except Exception:
                    pass
            candidates = [s for s in candidates if s.name in qualified_names]

        available = [s for s in candidates if s.effective_weight > 0]
        if not available:
            cooling = [s for s in candidates if not s.is_cooled_down]
            if cooling:
                chosen = min(cooling, key=lambda s: s._cooldown_until)
                logger.warning(f"[scheduler] 所有 provider 不可用，选冷却最早结束的: {chosen.name}")
                return chosen
            return None

        available.sort(key=lambda s: (s.effective_weight, s.priority), reverse=True)
        return available[0]

    async def dispatch(
        self,
        fn: Any,
        *args: Any,
        provider_name: str | None = None,
        required_caps: set[VideoCapability] | None = None,
        **kwargs: Any,
    ) -> tuple[Any, str]:
        """调度执行一个异步任务。

        fn: async callable，第一个参数是 provider_name（或通过 kwargs 传入）
        返回: (result, provider_name)
        """
        if provider_name and provider_name in self._slots:
            slot = self._slots[provider_name]
        else:
            slot = self.select(required_caps)

        if slot is None:
            raise VideoGenError("no_provider", "没有可用的视频生成 provider")

        async with self._global_sem:
            slot.record_start()
            start = _time.monotonic()
            try:
                result = await fn(*args, **kwargs)
                latency = _time.monotonic() - start
                slot.record_success(latency)
                return result, slot.name
            except Exception as e:
                slot.record_failure()
                raise

    async def dispatch_batch(
        self,
        tasks: list[tuple[Any, tuple[Any, ...], dict[str, Any]]],
        *,
        required_caps: set[VideoCapability] | None = None,
    ) -> list[tuple[Any, str]]:
        """批量调度多个异步任务，自动均衡分配到各 provider。

        tasks: [(fn, args, kwargs), ...]
        返回: [(result, provider_name), ...]
        """
        results: list[tuple[Any, str]] = [None] * len(tasks)
        sem_per_provider: dict[str, asyncio.Semaphore] = {}

        for name, slot in self._slots.items():
            sem_per_provider[name] = asyncio.Semaphore(slot.max_concurrent)

        async def _run_one(idx: int, fn: Any, args: tuple, kwargs: dict) -> None:
            slot = self.select(required_caps)
            if slot is None:
                raise VideoGenError("no_provider", "没有可用的视频生成 provider")

            async with sem_per_provider[slot.name]:
                async with self._global_sem:
                    slot.record_start()
                    start = _time.monotonic()
                    try:
                        result = await fn(*args, **kwargs)
                        latency = _time.monotonic() - start
                        slot.record_success(latency)
                        results[idx] = (result, slot.name)
                    except Exception as e:
                        slot.record_failure()
                        results[idx] = (e, slot.name)

        await asyncio.gather(*[_run_one(i, *t) for i, t in enumerate(tasks)])
        return results

    def status(self) -> dict[str, Any]:
        """调度器状态报告。"""
        return {
            "global_max_concurrent": self._global_max,
            "providers": {name: slot.to_dict() for name, slot in self._slots.items()},
        }


# ── 8. 模型分级调度 ──────────────────────────────────────


class ModelTier(Enum):
    """模型算力分级。

    economy  → 便宜/快速，用于规划阶段（VL理解、LLM编排）
    standard → 标准性价比，用于一般生成
    quality  → 强模型/高质，用于核心生成阶段（生图、生视频）
    """

    ECONOMY = "economy"
    STANDARD = "standard"
    QUALITY = "quality"


class PipelineStage(Enum):
    """流水线阶段标识。"""

    VL_UNDERSTAND = "vl_understand"
    LLM_STORYBOARD = "llm_storyboard"
    TEXT2IMAGE = "text2image"
    IMAGE2VIDEO = "image2video"
    AUDIO_ENHANCE = "audio_enhance"


_DEFAULT_STAGE_TIERS: dict[PipelineStage, ModelTier] = {
    PipelineStage.VL_UNDERSTAND: ModelTier.ECONOMY,
    PipelineStage.LLM_STORYBOARD: ModelTier.ECONOMY,
    PipelineStage.TEXT2IMAGE: ModelTier.QUALITY,
    PipelineStage.IMAGE2VIDEO: ModelTier.QUALITY,
    PipelineStage.AUDIO_ENHANCE: ModelTier.STANDARD,
}

_DEFAULT_TIER_MODELS: dict[ModelTier, dict[str, str]] = {
    ModelTier.ECONOMY: {
        "vl": "qwen2.5-vl-7b-instruct",
        "llm": "deepseek-chat",
        "t2i": "wanx2.1-t2i-turbo",
        # 2026-10-13 真机探活：wan2.1-i2v-*（新命名）本账号 Model not exist，
        # 旧命名 wanx2.1-i2v-* 可用（当时账户欠费，模型名已过校验层）
        "i2v": "wanx2.1-i2v-turbo",
    },
    ModelTier.STANDARD: {
        "vl": "qwen2.5-vl-72b-instruct",
        "llm": "deepseek-chat",
        "t2i": "wanx2.1-t2i-turbo",
        "i2v": "wanx2.1-i2v-turbo",
    },
    ModelTier.QUALITY: {
        "vl": "qwen2.5-vl-72b-instruct",
        "llm": "deepseek-chat",
        "t2i": "wanx2.1-t2i-plus",
        "i2v": "wanx2.1-i2v-plus",
    },
}


@dataclass
class TieredModelRouter:
    """模型分级路由器：流水线阶段 → 算力分级 → 具体模型名。

    核心思想：
      - 规划阶段（VL理解 + LLM编排）→ economy 级别，省算力
      - 生成阶段（生图 + 生视频）→ quality 级别，保质量
      - 后处理阶段（音频/字幕）→ standard 级别，平衡

    用法：
      router = TieredModelRouter()
      vl_model = router.resolve(PipelineStage.VL_UNDERSTAND, "vl")
      # → "qwen-vl-plus"（economy 级别的 VL 模型）

      i2v_model = router.resolve(PipelineStage.IMAGE2VIDEO, "i2v")
      # → "wan2.1-i2v-plus"（quality 级别的 i2v 模型）
    """

    stage_tiers: dict[PipelineStage, ModelTier] = field(default_factory=lambda: dict(_DEFAULT_STAGE_TIERS))
    tier_models: dict[ModelTier, dict[str, str]] = field(default_factory=lambda: {k: dict(v) for k, v in _DEFAULT_TIER_MODELS.items()})

    def resolve(self, stage: PipelineStage, capability: str) -> str:
        """根据流水线阶段和能力类型，解析出具体模型名。

        Args:
            stage: 流水线阶段（如 PipelineStage.VL_UNDERSTAND）
            capability: 能力类型键（"vl" / "llm" / "t2i" / "i2v"）

        Returns:
            具体模型名（如 "qwen-vl-plus"）
        """
        tier = self.stage_tiers.get(stage, ModelTier.STANDARD)
        models = self.tier_models.get(tier, {})
        model_name = models.get(capability, "")
        if not model_name:
            for fallback_tier in [ModelTier.STANDARD, ModelTier.ECONOMY]:
                fallback = self.tier_models.get(fallback_tier, {}).get(capability, "")
                if fallback:
                    model_name = fallback
                    break
        logger.debug(f"[tier_router] {stage.value} → {tier.value} → {capability} = {model_name}")
        return model_name

    def tier_for_stage(self, stage: PipelineStage) -> ModelTier:
        """查询某阶段使用的算力分级。"""
        return self.stage_tiers.get(stage, ModelTier.STANDARD)

    def set_stage_tier(self, stage: PipelineStage, tier: ModelTier) -> None:
        """动态调整某阶段的算力分级。"""
        self.stage_tiers[stage] = tier
        logger.info(f"[tier_router] {stage.value} 算力分级调整为 {tier.value}")

    def set_tier_model(self, tier: ModelTier, capability: str, model_name: str) -> None:
        """动态调整某分级下某能力的具体模型。"""
        if tier not in self.tier_models:
            self.tier_models[tier] = {}
        self.tier_models[tier][capability] = model_name
        logger.info(f"[tier_router] {tier.value}.{capability} 模型调整为 {model_name}")

    def summary(self) -> dict[str, Any]:
        """返回分级调度摘要。"""
        stages = {}
        for stage, tier in self.stage_tiers.items():
            models = self.tier_models.get(tier, {})
            stages[stage.value] = {
                "tier": tier.value,
                "models": dict(models),
            }
        return {
            "stage_tiers": stages,
            "tier_definitions": {
                tier.value: models for tier, models in self.tier_models.items()
            },
        }


_DEFAULT_TIER_ROUTER: TieredModelRouter | None = None


def get_tier_router() -> TieredModelRouter:
    """获取全局模型分级路由器（懒初始化，从配置加载）。"""
    global _DEFAULT_TIER_ROUTER
    if _DEFAULT_TIER_ROUTER is None:
        from app.config import get_settings
        settings = get_settings()

        stage_tiers = dict(_DEFAULT_STAGE_TIERS)
        tier_models = dict(_DEFAULT_TIER_MODELS)

        tier_models[ModelTier.ECONOMY]["vl"] = getattr(settings, "tier_economy_vl", "qwen2.5-vl-7b-instruct")
        tier_models[ModelTier.ECONOMY]["llm"] = getattr(settings, "tier_economy_llm", "deepseek-chat")
        tier_models[ModelTier.ECONOMY]["t2i"] = getattr(settings, "tier_economy_t2i", "wanx2.1-t2i-turbo")
        tier_models[ModelTier.ECONOMY]["i2v"] = getattr(settings, "tier_economy_i2v", "wanx2.1-i2v-turbo")

        tier_models[ModelTier.STANDARD]["vl"] = getattr(settings, "tier_standard_vl", "qwen2.5-vl-72b-instruct")
        tier_models[ModelTier.STANDARD]["llm"] = getattr(settings, "tier_standard_llm", "deepseek-chat")
        tier_models[ModelTier.STANDARD]["t2i"] = getattr(settings, "tier_standard_t2i", "wanx2.1-t2i-turbo")
        tier_models[ModelTier.STANDARD]["i2v"] = getattr(settings, "tier_standard_i2v", "wanx2.1-i2v-turbo")

        tier_models[ModelTier.QUALITY]["vl"] = getattr(settings, "tier_quality_vl", "qwen2.5-vl-72b-instruct")
        tier_models[ModelTier.QUALITY]["llm"] = getattr(settings, "tier_quality_llm", "deepseek-chat")
        tier_models[ModelTier.QUALITY]["t2i"] = getattr(settings, "tier_quality_t2i", "wanx2.1-t2i-plus")
        tier_models[ModelTier.QUALITY]["i2v"] = getattr(settings, "tier_quality_i2v", "wanx2.1-i2v-plus")

        _DEFAULT_TIER_ROUTER = TieredModelRouter(stage_tiers=stage_tiers, tier_models=tier_models)
    return _DEFAULT_TIER_ROUTER


_DEFAULT_SCHEDULER: ComputeScheduler | None = None


def get_scheduler() -> ComputeScheduler:
    """获取全局默认调度器（懒初始化）。"""
    global _DEFAULT_SCHEDULER
    if _DEFAULT_SCHEDULER is None:
        from app.config import get_settings
        settings = get_settings()
        cfg = {
            "providers": {
                "ark": {
                    "weight": 2.0,
                    "max_concurrent": getattr(settings, "ark_max_concurrent", 3),
                    "priority": 10,
                },
                "dashscope": {
                    "weight": 1.0,
                    "max_concurrent": getattr(settings, "dashscope_max_concurrent", 2),
                    "priority": 5,
                },
                "kling": {
                    "weight": 1.0,
                    "max_concurrent": getattr(settings, "kling_max_concurrent", 2),
                    "priority": 5,
                },
            },
            "global_max_concurrent": getattr(settings, "video_global_max_concurrent", 6),
        }
        _DEFAULT_SCHEDULER = ComputeScheduler.from_config(cfg)
    return _DEFAULT_SCHEDULER