"""多图参考视频生成流水线 Skill：多张参考图 + 描述 → 逐镜头编排 → 分镜关键帧 → image2video → 拼接成片。

设计依据：
  - 小加同学"手持跟拍日常vlog"技能的 3 阶段流水线：
    LLM 看图编排 → text2image 分镜关键帧 → image2video 逐镜生成 → 拼接
  - 与 auto_short_video 同构，但核心差异：
    1. 输入含多张参考图（非纯文字主题）
    2. Step 1 用 VL 理解参考图语义
    3. Step 4 用 image2video 真视频（非 ken-burns 图片缓动）
    4. Step 5 用 video_concat 拼接视频片段（非图片序列）

编排流程（6 步）：
  1. VL 理解参考图：QwenVL 多图 → 场景/角色/道具/色彩结构化描述
  2. LLM 编排分镜脚本：场景描述 + 用户 prompt → 逐镜头脚本
  3. text2image 生成分镜关键帧：逐镜 image_prompt → WanxAdapter.generate()
  4. image2video 逐镜生视频：关键帧 + motion_prompt → DashScopeVideoAdapter.image2video()
  5. ffmpeg 拼接成片：视频片段 xfade concat → final.mp4
  6. 存 asset_library + 发 SSE card_draft_ready

降级策略（零件可缺）：
  - VL 不可用 → 跳过 Step 1，直接用 prompt 编排
  - LLM 不可用 → 默认分镜（每图一镜 + prompt）
  - text2image 失败 → 用参考图原片作为关键帧
  - image2video 失败 → 该镜退化为 ken-burns 图片缓动
  - compose 失败 → 返回各片段 URL 列表
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.core.skill_base import Skill
from app.core.skill_registry import register

logger = logging.getLogger(__name__)

_OUTPUT_DIR = Path(__file__).resolve().parent.parent.parent.parent / "outputs"


class MultiImageVideoInput(BaseModel):
    image_asset_ids: list[str] = Field(
        min_length=1,
        max_length=10,
        description="参考图 asset_id 列表（1-10 张）",
    )
    prompt: str = Field(
        min_length=5,
        max_length=2000,
        description="视频画面描述（镜头运动、角色动作、场景转换等）",
    )
    target_duration: float = Field(
        default=15.0,
        ge=5.0,
        le=60.0,
        description="目标时长（秒），5-60s",
    )
    ratio: Literal["9:16", "16:9", "1:1"] = Field(
        default="9:16",
        description="画幅比：9:16 竖屏 / 16:9 横屏 / 1:1 方形",
    )
    style: str = Field(
        default="电影感",
        description="风格：电影感/纪实/动画/广告",
    )
    shot_duration: float = Field(
        default=5.0,
        ge=2.0,
        le=10.0,
        description="每镜头时长（秒），2-10s",
    )
    provider: Literal["dashscope", "kling", "ark"] | None = Field(
        default=None,
        description="视频生成 provider（None 时用系统默认）",
    )
    preview_only: bool = Field(
        default=False,
        description="仅预览模式：只执行 VL+LLM 编排，返回分镜草稿供用户编辑，不生成视频",
    )
    refine_shots: list[dict[str, Any]] | None = Field(
        default=None,
        description="微调模式：传入编辑后的分镜列表（从预览结果修改而来），跳过 VL+LLM 直接从 Step 3 开始生成",
    )
    refine_image_asset_ids: list[str] | None = Field(
        default=None,
        description="微调模式的参考图 ID（若与首次不同则更新）",
    )


_VL_SCENE_PROMPT = """你是一个专业的视频策划师。请仔细观察以下参考图片，分析并输出 JSON（不要 markdown 代码块，直接输出 JSON）：

{
  "scenes": [
    {
      "image_index": 1,
      "location": "场景地点",
      "subjects": ["主体1", "主体2"],
      "props": ["道具1", "道具2"],
      "lighting": "光线描述",
      "color_tone": "色调",
      "composition": "构图描述",
      "mood": "情绪氛围"
    }
  ],
  "cross_scene": {
    "shared_subjects": ["跨场景出现的主体"],
    "visual_style": "统一视觉风格",
    "color_system": "色彩体系"
  }
}

要求：
- 每张图单独分析，image_index 从 1 开始
- cross_scene 描述多图之间的关联（重复出现的角色/道具/场景）
- 描述要具体到可用于 AI 生图的提示词
"""

_STORYBOARD_PROMPT = """你是一个专业的短视频导演。根据以下参考图分析和用户描述，编排逐镜头脚本。

参考图分析：
{scene_description}

用户描述：{user_prompt}
目标时长：{duration}秒
风格：{style}
每镜头时长：{shot_duration}秒

请输出 JSON（不要 markdown 代码块，直接输出 JSON）：
{{
  "title": "视频标题",
  "total_shots": 5,
  "shots": [
    {{
      "shot_index": 1,
      "caption": "这镜头的口播或字幕文案",
      "image_prompt": "关键帧画面描述（英文，用于 AI 生图，要具体有画面感，保持与参考图的角色场景道具一致）",
      "motion_prompt": "镜头运动描述（如：缓慢推进、从左摇到右、俯拍拉远、人物转身）",
      "reference_images": [1],
      "duration": 5.0,
      "transition": "cut"
    }}
  ]
}}

要求：
- reference_images 引用参考图的编号（1开始），表示这镜参考哪张图
- image_prompt 要保持与参考图的角色/场景/道具一致，英文描述
- motion_prompt 描述镜头运动和角色动作，中文即可
- 分镜数 = 目标时长 / 每镜时长（向上取整）
- transition: cut / dissolve / wipe
- 第一个镜头要有 hook（3秒内抓住注意力）
- 每句 caption 15-30 字，口语化
"""


async def _resolve_image_urls(
    image_asset_ids: list[str],
    user_id: str,
) -> list[str]:
    """从 asset_id 列表解析图片 URL 列表。"""
    from app.db.models import ImageAsset
    from sqlalchemy import select
    from app.db.session import AsyncSessionLocal

    urls: list[str] = []
    async with AsyncSessionLocal() as session:
        for aid in image_asset_ids:
            stmt = select(ImageAsset).where(
                ImageAsset.id == aid,
                ImageAsset.user_id == user_id,
            )
            result = await session.execute(stmt)
            asset = result.scalar_one_or_none()
            if asset is None:
                raise ValueError(f"未找到 asset_id={aid} 的图片素材")
            urls.append(asset.original_url)
    return urls


async def _vl_understand_images(
    image_urls: list[str],
) -> dict[str, Any] | None:
    """Step 1: 用 QwenVL 理解多张参考图的场景语义。

    降级：VL 不可用时返回 None，调用方跳过此步。
    """
    from app.config import get_settings

    settings = get_settings()
    api_key = (settings.dashscope_api_key or "").strip()
    if not api_key:
        logger.info("[multi_image_video] 未配置 DASHSCOPE_API_KEY，跳过 VL 理解")
        return None

    try:
        from app.adapters.qwen_vl import QwenVLAdapter
        from app.adapters.video_pipeline import PipelineStage, get_tier_router

        router = get_tier_router()
        vl_model = router.resolve(PipelineStage.VL_UNDERSTAND, "vl")
        logger.info(f"[multi_image_video] VL 理解使用分级模型: {vl_model}")
        adapter = QwenVLAdapter(api_key=api_key, model=vl_model)

        from app.services.asset_library import url_to_base64

        content: list[dict[str, Any]] = [{"text": _VL_SCENE_PROMPT}]
        for i, url in enumerate(image_urls, 1):
            if url.startswith("http"):
                image_src = url
            else:
                image_src = url_to_base64(url) or f"http://localhost:8000{url}"
            content.append({"image": image_src})

        messages = [{"role": "user", "content": content}]
        result = await adapter.chat(messages)

        # 防御（2026-10-13）：DashScope 多模态返回的 content 可能是
        # list[{"text": ...}]（多图输入时常见），统一拉平成字符串再解析，
        # 否则 text.find("{") 会 AttributeError 把 VL 步骤意外降级。
        raw = result.get("content", "")
        if isinstance(raw, list):
            text = "".join(
                item.get("text", "") if isinstance(item, dict) else str(item)
                for item in raw
            )
        else:
            text = str(raw or "")
        json_start = text.find("{")
        json_end = text.rfind("}") + 1
        if json_start >= 0 and json_end > json_start:
            scene_desc = json.loads(text[json_start:json_end])
            logger.info(f"[multi_image_video] VL 理解完成：{len(scene_desc.get('scenes', []))} 个场景")
            return scene_desc

        logger.warning(f"[multi_image_video] VL 返回非 JSON，跳过：{text[:200]}")
        return None

    except Exception as e:
        logger.warning(f"[multi_image_video] VL 理解失败，降级跳过：{e}")
        return None


async def _generate_storyboard(
    scene_description: dict[str, Any] | None,
    user_prompt: str,
    target_duration: float,
    shot_duration: float,
    style: str,
    num_reference_images: int,
) -> dict[str, Any]:
    """Step 2: LLM 编排分镜脚本。

    降级：LLM 不可用或 JSON 解析失败时，生成默认分镜。
    """
    if scene_description:
        scene_text = json.dumps(scene_description, ensure_ascii=False, indent=2)
    else:
        scene_text = (
            f"（VL 未分析，但有 {num_reference_images} 张不同的参考图，每张图对应一个镜头，"
            f"共 {num_reference_images} 镜。请根据用户描述，为每张图想象不同的画面场景，"
            f"确保每镜的 image_prompt 各不相同——例如第1张可能是大堂/入口，"
            f"第2张可能是室内/泳池，第3张可能是露台/景观……按度假动线编排，"
            f"不要7镜用同一个描述复制7遍。）"
        )

    prompt = _STORYBOARD_PROMPT.format(
        scene_description=scene_text,
        user_prompt=user_prompt,
        duration=int(target_duration),
        style=style,
        shot_duration=int(shot_duration),
    )

    try:
        from app.engine.factory import get_deepseek_llm
        from app.adapters.video_pipeline import PipelineStage, get_tier_router

        router = get_tier_router()
        llm_model = router.resolve(PipelineStage.LLM_STORYBOARD, "llm")
        logger.info(f"[multi_image_video] LLM 编排使用分级模型: {llm_model}")
        llm = get_deepseek_llm(model=llm_model)
        if llm is None:
            raise ValueError("LLM 不可用（熔断器开启或未配置 API Key）")
        response = await llm.ainvoke(prompt)
        text = response.content if hasattr(response, "content") else str(response)

        json_start = text.find("{")
        json_end = text.rfind("}") + 1
        if json_start >= 0 and json_end > json_start:
            storyboard = json.loads(text[json_start:json_end])
            if "shots" in storyboard and storyboard["shots"]:
                logger.info(f"[multi_image_video] 分镜脚本生成：{len(storyboard['shots'])} 镜")
                return storyboard

        raise ValueError("脚本缺少 shots 字段")

    except Exception as e:
        logger.warning(f"[multi_image_video] LLM 编排失败，使用默认分镜：{e}")
        num_shots = max(1, int(target_duration / shot_duration))
        _default_motions = ["缓慢推进", "横向跟移", "微俯缓推", "低机位跟拍", "静物微动", "匀速横移", "拉远", "环绕", "仰拍推进", "手持晃动"]
        _default_captions = ["开场引入", "场景展开", "细节特写", "人物互动", "氛围营造", "情绪推进", "转折过渡", "高潮呈现", "收束回味", "离场留白"]
        return {
            "title": user_prompt[:30],
            "total_shots": num_shots,
            "shots": [
                {
                    "shot_index": i + 1,
                    "caption": f"第{i + 1}镜：{_default_captions[i % len(_default_captions)]}，{user_prompt[:15]}",
                    "image_prompt": f"{user_prompt}, shot {i + 1} of {num_shots}, {_default_captions[i % len(_default_captions)]}, cinematic, high quality, detailed, varied composition",
                    "motion_prompt": _default_motions[i % len(_default_motions)],
                    "reference_images": [min(i + 1, num_reference_images)],
                    "duration": shot_duration,
                    "transition": "cut",
                }
                for i in range(num_shots)
            ],
        }


async def _generate_shot_frames(
    shots: list[dict[str, Any]],
    ratio: str,
    user_id: str,
    image_urls: list[str],
) -> list[dict[str, Any]]:
    """Step 3: text2image 生成分镜关键帧。

    降级：生图失败时用参考图原片作为关键帧。
    """
    from app.config import get_settings

    settings = get_settings()
    api_key = (settings.dashscope_api_key or "").strip()
    if not api_key:
        logger.info("[multi_image_video] 未配置图像 API key，用参考图作为关键帧")
        for i, shot in enumerate(shots):
            ref_idx = min(i, len(image_urls) - 1)
            shot["frame_url"] = image_urls[ref_idx]
            shot["frame_source"] = "reference"
        return shots

    try:
        from app.adapters.image_gen import WanxAdapter
        from app.adapters.video_pipeline import PipelineStage, get_tier_router
        from app.services.asset_library import save_asset

        router = get_tier_router()
        t2i_model = router.resolve(PipelineStage.TEXT2IMAGE, "t2i")
        logger.info(f"[multi_image_video] 文生图使用分级模型: {t2i_model}")
        adapter = WanxAdapter(api_key=api_key, model=t2i_model)
        size_map = {"9:16": "720x1280", "16:9": "1280x720", "1:1": "1024x1024"}
        size = size_map.get(ratio, "720x1280")
        max_concurrent = settings.multi_image_video_max_concurrent_frames

        sem = asyncio.Semaphore(max_concurrent)

        async def _gen_one(shot: dict, idx: int) -> None:
            prompt_text = shot.get("image_prompt", "")
            if not prompt_text:
                ref_idx = min(idx, len(image_urls) - 1)
                shot["frame_url"] = image_urls[ref_idx]
                shot["frame_source"] = "reference"
                return

            async with sem:
                try:
                    img_bytes = await adapter.generate(prompt=prompt_text, size=size, count=1)
                    if img_bytes:
                        asset = await save_asset(
                            user_id=user_id,
                            filename=f"frame_{idx:03d}.png",
                            content_type="image/png",
                            data=img_bytes[0] if isinstance(img_bytes, list) else img_bytes,
                            source="ai",
                        )
                        shot["frame_url"] = asset["original_url"]
                        shot["frame_asset_id"] = asset["id"]
                        shot["frame_source"] = "ai_generated"
                        logger.info(f"[multi_image_video] 关键帧 {idx + 1} 生成成功")
                        return
                except Exception as e:
                    logger.warning(f"[multi_image_video] 关键帧 {idx + 1} 生成失败：{e}")

            ref_idx = min(idx, len(image_urls) - 1)
            shot["frame_url"] = image_urls[ref_idx]
            shot["frame_source"] = "reference_fallback"

        await asyncio.gather(*[_gen_one(shot, i) for i, shot in enumerate(shots)])
        return shots

    except Exception as e:
        logger.warning(f"[multi_image_video] 图像适配器初始化失败，用参考图：{e}")
        for i, shot in enumerate(shots):
            ref_idx = min(i, len(image_urls) - 1)
            shot["frame_url"] = image_urls[ref_idx]
            shot["frame_source"] = "reference_fallback"
        return shots


async def _generate_shot_clips(
    shots: list[dict[str, Any]],
    ratio: str,
    shot_duration: float,
    user_id: str,
    provider: str | None = None,
    on_progress: Any = None,
    total_timeout: float | None = None,
) -> list[dict[str, Any]]:
    """Step 4: image2video 逐镜生成视频片段。

    首尾帧连贯策略（Seedance i2v 独有）：
      - provider=ark 时，下一镜的首帧 = 上一镜的关键帧（frame_url）
      - 即 shot[i+1] 的 last_frame_url = shot[i].frame_url
      - 这样 Seedance 会以首尾帧约束生成，跨镜视觉连贯

    降级：某镜 image2video 失败时标记为 ken-burns 退回。
    串行执行（避免同时占多个 API 配额）。

    总体超时（P1-14 修复，2026-10-13）：total_timeout>0 时在镜头边界
    检查 deadline，超时后剩余镜头全部标 ken_burns 兜底——旧版 3 镜
    最坏 15 分钟无任何中断机制，用户侧表现为永久转圈。
    注意单镜内部轮询上限另有 300s，最坏耗时约为 total_timeout + 300s。
    """
    import time as _time

    from app.skills.produce.video_gen import _resolve_adapter, VideoGenError

    try:
        adapter, provider_name = _resolve_adapter(provider)
    except VideoGenError as e:
        logger.warning(f"[multi_image_video] 视频适配器不可用：{e.message}")
        for shot in shots:
            shot["clip_mode"] = "ken_burns"
            shot["clip_error"] = e.message
        return shots

    from app.config import get_settings
    from app.adapters.video_pipeline import PipelineStage, get_tier_router

    settings = get_settings()
    router = get_tier_router()
    i2v_model = router.resolve(PipelineStage.IMAGE2VIDEO, "i2v")
    logger.info(f"[multi_image_video] 图生视频使用分级模型: {i2v_model}")

    deadline = _time.monotonic() + total_timeout if total_timeout and total_timeout > 0 else None
    if deadline:
        logger.info(f"[multi_image_video] 逐镜生成总体超时预算：{total_timeout:.0f}s")

    use_last_frame = provider_name == "ark"
    if use_last_frame:
        logger.info("[multi_image_video] Seedance 首尾帧连贯模式：启用")

    from app.services.asset_library import save_video_asset

    for i, shot in enumerate(shots):
        # P1-14：镜头边界检查总体超时。超时后剩余镜头全部 ken-burns 兜底，
        # 保证流程能走到拼接出片，而不是无限卡在轮询上。
        if deadline is not None and _time.monotonic() > deadline:
            remaining = len(shots) - i
            logger.warning(
                f"[multi_image_video] 总体超时 {total_timeout:.0f}s 已到，"
                f"剩余 {remaining} 镜退化为 ken-burns"
            )
            for s in shots[i:]:
                s["clip_mode"] = "ken_burns"
                s["clip_error"] = f"总体超时熔断（预算 {total_timeout:.0f}s）"
            break

        frame_url = shot.get("frame_url", "")
        if not frame_url:
            shot["clip_mode"] = "ken_burns"
            shot["clip_error"] = "无关键帧"
            continue

        from app.services.asset_library import url_to_base64

        full_url = frame_url if frame_url.startswith("http") else (url_to_base64(frame_url) or f"http://localhost:8000{frame_url}")
        motion_prompt = shot.get("motion_prompt", "")

        last_frame_url = None
        if use_last_frame and i > 0:
            prev_frame = shots[i - 1].get("frame_url", "")
            if prev_frame:
                last_frame_url = prev_frame if prev_frame.startswith("http") else (url_to_base64(prev_frame) or f"http://localhost:8000{prev_frame}")

        try:
            video_bytes = await adapter.image2video(
                image=full_url,
                prompt=motion_prompt,
                ratio=ratio,
                duration=shot_duration,
                model=i2v_model,
                last_frame_url=last_frame_url,
                on_progress=on_progress,
            )

            if video_bytes:
                clip_asset = await save_video_asset(
                    user_id=user_id,
                    filename=f"clip_{i:03d}.mp4",
                    content_type="video/mp4",
                    data=video_bytes,
                    source="ai",
                    metadata={
                        "source": "multi_image_video",
                        "shot_index": i + 1,
                        "motion_prompt": motion_prompt,
                        "last_frame_used": bool(last_frame_url),
                    },
                )
                shot["clip_url"] = clip_asset["original_url"]
                shot["clip_asset_id"] = clip_asset["asset_id"]
                shot["clip_mode"] = "video"
                if last_frame_url:
                    shot["clip_coherence"] = "first_last_frame"
                logger.info(f"[multi_image_video] 第 {i + 1}/{len(shots)} 镜视频生成成功")
                continue

        except Exception as e:
            logger.warning(f"[multi_image_video] 第 {i + 1} 镜 image2video 失败：{e}")

        shot["clip_mode"] = "ken_burns"
        shot["clip_error"] = "image2video 失败"

    return shots


async def _compose_final(
    shots: list[dict[str, Any]],
    ratio: str,
    user_id: str,
    title: str,
) -> tuple[bytes | None, list[str]]:
    """Step 5: 拼接成片。

    优先用 video_concat 拼接视频片段。
    如果全部是 ken_burns，退回现有 compose_video 图片模式。
    返回 (final_bytes, degradation_notes)。
    """
    from app.services.asset_library import _path_from_url

    degradation: list[str] = []

    video_clips = [s for s in shots if s.get("clip_mode") == "video" and s.get("clip_url")]
    ken_burns_shots = [s for s in shots if s.get("clip_mode") != "video"]

    if ken_burns_shots:
        degradation.append(f"{len(ken_burns_shots)} 镜退化为 ken-burns 图片缓动")

    if not video_clips:
        degradation.append("无视频片段，尝试图片 ken-burns 合成")
        try:
            size_map = {"9:16": "1080x1920", "16:9": "1920x1080", "1:1": "1080x1080"}
            # P0-4 修复（2026-10-13）：frame_url 是 /uploads/... URL，
            # compose_video 的 image 字段只认文件系统路径（Path.is_file()）。
            # 旧代码直接把 URL 传进去，全 ken-burns 场景必然 missing_file。
            # 先统一转本地路径，转不了的跳过该镜并记 degradation。
            kb_shots: list[dict[str, Any]] = []
            for s in shots:
                frame_url = s.get("frame_url", "")
                if not frame_url:
                    continue
                local = _path_from_url(frame_url)
                if local is None or not local.exists():
                    degradation.append(f"关键帧无法转本地路径，跳过：{frame_url[:60]}")
                    continue
                kb_shots.append({
                    "caption": s.get("caption", ""),
                    "image": str(local),
                    "duration": s.get("duration", 5.0),
                    "motion": "ken-burns",
                })
            if not kb_shots:
                degradation.append("无可用的本地关键帧，ken-burns 合成取消")
                return None, degradation
            storyboard = {
                "size": size_map.get(ratio, "1080x1920"),
                "image_motion": "ken-burns",
                "shots": kb_shots,
            }
            from app.adapters.video_compose import compose_video
            output_dir = _OUTPUT_DIR / user_id / "multi_image_video"
            output_dir.mkdir(parents=True, exist_ok=True)
            final_path = output_dir / f"{title[:20]}_kenburns.mp4"
            result_path = await compose_video(storyboard=storyboard, output_path=str(final_path), pad_mode="auto")
            return result_path.read_bytes(), degradation
        except Exception as e:
            degradation.append(f"ken-burns 合成也失败：{e}")
            return None, degradation

    try:
        from app.adapters.video_compose import compose_video_concat

        clip_urls = []
        transitions = []
        for s in video_clips:
            url = s["clip_url"]
            local_path = _path_from_url(url)
            clip_urls.append(str(local_path) if local_path and local_path.exists() else (url if url.startswith("http") else f"http://localhost:8000{url}"))
            transitions.append(s.get("transition", "cut"))

        output_dir = _OUTPUT_DIR / user_id / "multi_image_video"
        output_dir.mkdir(parents=True, exist_ok=True)
        final_path = output_dir / f"{title[:20]}_final.mp4"

        result_path = await compose_video_concat(
            clip_urls=clip_urls,
            transitions=transitions,
            output_path=str(final_path),
        )
        return result_path.read_bytes(), degradation

    except Exception as e:
        logger.warning(f"[multi_image_video] video_concat 失败，尝试简单拼接：{e}")
        degradation.append(f"xfade 拼接失败：{e}，尝试简单 concat")

        try:
            from app.adapters.video_compose import compose_video_concat_simple

            clip_urls = []
            for s in video_clips:
                url = s["clip_url"]
                local_path = _path_from_url(url)
                clip_urls.append(str(local_path) if local_path and local_path.exists() else (url if url.startswith("http") else f"http://localhost:8000{url}"))

            output_dir = _OUTPUT_DIR / user_id / "multi_image_video"
            output_dir.mkdir(parents=True, exist_ok=True)
            final_path = output_dir / f"{title[:20]}_final.mp4"

            result_path = await compose_video_concat_simple(
                clip_urls=clip_urls,
                output_path=str(final_path),
            )
            return result_path.read_bytes(), degradation

        except Exception as e2:
            degradation.append(f"简单拼接也失败：{e2}")
            return None, degradation


@register
class MultiImageVideoSkill(Skill):
    """多图参考视频生成：多张参考图 + 描述 → 逐镜头编排 → 分镜关键帧 → image2video → 拼接成片。"""

    node_type = "produce"
    name = "multi_image_video"
    display_name = "多图参考视频生成"
    description = (
        "根据多张参考图片和文字描述，自动编排并生成一条完整短视频。"
        "流程：VL看图理解场景 → LLM编排分镜脚本 → AI生成分镜关键帧 → 逐镜图生视频 → 拼接成片。"
        "用户说'用这些图做视频''根据图片生成视频''多图生视频''做视频'时必须调用此工具。"
        "当用户上传了图片且意图是做视频时，优先调用此工具而非 generate_video 或 compose_card_deck。"
        "每个环节都有降级策略，不会因单个 API 不可用而中断。"
    )
    skill_category = "create"
    skill_priority = "hot"
    trigger_words = [
        "多图生视频", "用这些图做视频", "根据图片生成视频",
        "参考图做视频", "图片场景生成视频", "多图视频",
        "做视频", "生成视频", "视频", "图片做视频", "照片做视频",
    ]
    input_schema = MultiImageVideoInput

    async def execute(self, inputs: dict[str, Any]) -> dict[str, Any]:
        from app.config import get_settings

        context = inputs.get("_context")
        user_id = getattr(context, "user_id", None)
        if not user_id:
            return {"error": "未能确认用户身份"}

        params = MultiImageVideoInput.model_validate({
            key: value for key, value in inputs.items() if key in MultiImageVideoInput.model_fields
        })

        # asset_id 守卫（2026-10-14）：拦截 LLM 幻觉的假 ID（img_1 这类），
        # 失败时回带本会话 available_asset_ids 让它用真值自纠，
        # 替代原来"假 ID 硬查库 → 404 → Agent 谎报素材库失效"的链路。
        _session_id = (getattr(context, "extra", None) or {}).get("session_id")
        from app.services.asset_ref import guard_asset_ids

        _guard = await guard_asset_ids(params.image_asset_ids, str(user_id), _session_id)
        if not _guard["ok"]:
            return {
                "error": _guard["error"],
                "hint": _guard["hint"],
                "available_asset_ids": _guard["available_asset_ids"],
            }

        workflow_id = inputs.get("_workflow_id")
        degradation_notes: list[str] = []

        async def _emit_step(step: int, total: int, label: str, detail: str = "") -> None:
            if not workflow_id:
                return
            from app.services.sse_bus import sse_bus
            pct = int(step / total * 100)
            await sse_bus.publish(workflow_id, "multi_image_video_progress", {
                "skill": "multi_image_video",
                "step": step,
                "total": total,
                "label": label,
                "detail": detail,
                "percent": pct,
            })

        # ── 微调模式：跳过 VL+LLM，从 Step 3 开始 ──
        if params.refine_shots is not None:
            return await self._execute_refine(
                params, str(user_id), workflow_id, _emit_step, session_id=_session_id
            )

        # Step 1: VL 理解参考图
        logger.info(f"[1/6] VL 理解参考图（{len(params.image_asset_ids)} 张）")
        await _emit_step(1, 6, "VL理解参考图", f"分析{len(params.image_asset_ids)}张参考图...")

        try:
            image_urls = await _resolve_image_urls(params.image_asset_ids, str(user_id))
        except ValueError as e:
            return {"error": str(e)}

        scene_description = await _vl_understand_images(image_urls)
        if scene_description is None:
            degradation_notes.append("VL理解：不可用，跳过，直接用用户描述编排")

        # Step 2: LLM 编排分镜脚本
        logger.info("[2/6] 编排分镜脚本")
        await _emit_step(2, 6, "编排分镜脚本", "LLM 生成逐镜头脚本...")

        storyboard = await _generate_storyboard(
            scene_description=scene_description,
            user_prompt=params.prompt,
            target_duration=params.target_duration,
            shot_duration=params.shot_duration,
            style=params.style,
            num_reference_images=len(image_urls),
        )
        shots = storyboard.get("shots", [])
        title = storyboard.get("title", params.prompt[:30])

        if not shots:
            return {"error": "分镜脚本为空，无法生成视频"}

        # ── 仅预览模式：返回分镜草稿，不生成视频 ──
        if params.preview_only:
            logger.info("[preview_only] 分镜草稿已生成，返回给用户编辑")
            await _emit_step(2, 2, "分镜预览就绪", "请编辑分镜后确认生成")

            preview_result = {
                "mode": "preview",
                "title": title,
                "shots": shots,
                "scene_description": scene_description,
                "image_urls": image_urls,
                "total_shots": len(shots),
                "estimated_duration": len(shots) * params.shot_duration,
                "degradation": degradation_notes,
                "hint": "编辑 shots 中任意镜的 image_prompt/motion_prompt/duration/transition 后，"
                        "通过 refine_shots 参数传回即可生成视频。"
                        "也可增删镜头（shots 列表长度可变）。",
            }

            if workflow_id:
                from app.services.sse_bus import sse_bus
                await sse_bus.publish(workflow_id, "card_draft_ready", {
                    "card_draft": {
                        "title": f"分镜预览 - {title}",
                        "template": "storyboard_preview",
                        "pages": [{
                            "id": f"shot_{s.get('shot_index', i+1)}",
                            "type": "content",
                            "mediaType": "image",
                            "title": s.get("caption", f"第{i+1}镜"),
                            "imagePrompt": s.get("image_prompt", ""),
                            "motionPrompt": s.get("motion_prompt", ""),
                            "duration": s.get("duration", params.shot_duration),
                            "transition": s.get("transition", "cut"),
                            "referenceImages": s.get("reference_images", []),
                        } for i, s in enumerate(shots)],
                        "pngUrls": [],
                        "htmlUrls": [],
                    },
                    "png_urls": [],
                    "html_urls": [],
                })

            return preview_result

        # Step 3: text2image 生成分镜关键帧
        logger.info(f"[3/6] 生成分镜关键帧（{len(shots)} 镜）")
        await _emit_step(3, 6, "生成分镜关键帧", f"共{len(shots)}镜...")

        shots = await _generate_shot_frames(shots, params.ratio, str(user_id), image_urls)

        # Step 4: image2video 逐镜生视频
        logger.info(f"[4/6] 逐镜生成视频（{len(shots)} 镜）")
        await _emit_step(4, 6, "逐镜生成视频", f"第1/{len(shots)}镜...")

        clip_on_progress = None
        if workflow_id:
            from app.services.sse_bus import sse_bus

            async def _clip_progress(elapsed: float, max_wait: float, status: str) -> None:
                await sse_bus.publish(workflow_id, "multi_image_video_progress", {
                    "skill": "multi_image_video",
                    "step": 4,
                    "total": 6,
                    "label": "逐镜生成视频",
                    "detail": f"轮询中 {elapsed:.0f}s/{max_wait:.0f}s 状态={status}",
                    "percent": 50 + int(elapsed / max_wait * 15),
                })

            clip_on_progress = _clip_progress

        shots = await _generate_shot_clips(
            shots=shots,
            ratio=params.ratio,
            shot_duration=params.shot_duration,
            user_id=str(user_id),
            provider=params.provider,
            on_progress=clip_on_progress,
            total_timeout=get_settings().multi_image_video_total_timeout,
        )

        # Step 5: 拼接成片
        logger.info("[5/6] 拼接成片")
        await _emit_step(5, 6, "拼接成片", "ffmpeg 拼接视频片段...")

        final_bytes, compose_degradation = await _compose_final(
            shots=shots,
            ratio=params.ratio,
            user_id=str(user_id),
            title=title,
        )
        degradation_notes.extend(compose_degradation)

        if not final_bytes:
            clip_urls = [s["clip_url"] for s in shots if s.get("clip_url")]
            return {
                "success": False,
                "error": "成片拼接失败",
                "degradation": degradation_notes,
                "clip_urls": clip_urls,
                "shots_count": len(shots),
            }

        # Step 6: 存 asset_library + 发 SSE
        logger.info("[6/6] 保存交付")
        await _emit_step(6, 6, "保存交付", "存储视频素材...")

        from app.services.asset_library import save_video_asset

        asset = await save_video_asset(
            user_id=str(user_id),
            filename=f"{title[:20]}_multi_image.mp4",
            content_type="video/mp4",
            data=final_bytes,
            source="ai",
            metadata={
                "source": "multi_image_video",
                "prompt": params.prompt[:200],
                "ratio": params.ratio,
                "target_duration": params.target_duration,
                "style": params.style,
                "shots_count": len(shots),
                "reference_images": len(params.image_asset_ids),
                "degradation": degradation_notes,
            },
        )

        video_url = asset["original_url"]

        if workflow_id:
            from app.services.sse_bus import sse_bus

            card_draft = {
                "title": f"多图视频 - {title}",
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
            }
            await sse_bus.publish(workflow_id, "card_draft_ready", {
                "card_draft": card_draft,
                "png_urls": [],
                "html_urls": [],
            })

        return {
            "success": True,
            "asset_id": asset.get("asset_id") or asset.get("id"),
            "asset_url": video_url,
            "title": title,
            "shots_count": len(shots),
            "video_clips": sum(1 for s in shots if s.get("clip_mode") == "video"),
            "ken_burns_clips": sum(1 for s in shots if s.get("clip_mode") != "video"),
            "degradation": degradation_notes,
        }

    async def _execute_refine(
        self,
        params: MultiImageVideoInput,
        user_id: str,
        workflow_id: str | None,
        emit_step: Any,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        """微调模式：用户编辑了分镜后，跳过 VL+LLM，从 Step 3 开始生成。

        流程：
          1. 解析 refine_shots（用户编辑后的分镜列表）
          2. 解析参考图 URL（可用 refine_image_asset_ids 或原 image_asset_ids）
          3. Step 3→4→5→6 正常执行
        """
        shots = params.refine_shots
        if not shots:
            return {"error": "refine_shots 为空，无镜头可生成"}

        from app.config import get_settings

        asset_ids = params.refine_image_asset_ids or params.image_asset_ids
        degradation_notes: list[str] = ["微调模式：跳过 VL+LLM，使用用户编辑的分镜"]

        # asset_id 守卫（2026-10-14）：refine 可能换参考图，幻觉 ID 同样在此拦截
        from app.services.asset_ref import guard_asset_ids

        _guard = await guard_asset_ids(asset_ids, user_id, session_id)
        if not _guard["ok"]:
            return {
                "error": _guard["error"],
                "hint": _guard["hint"],
                "available_asset_ids": _guard["available_asset_ids"],
            }

        logger.info(f"[refine] 微调模式，{len(shots)} 镜，从 Step 3 开始")

        try:
            image_urls = await _resolve_image_urls(asset_ids, user_id)
        except ValueError as e:
            return {"error": str(e)}

        title = params.prompt[:30]

        # Step 3: text2image
        await emit_step(3, 6, "生成分镜关键帧", f"共{len(shots)}镜...")
        shots = await _generate_shot_frames(shots, params.ratio, user_id, image_urls)

        # Step 4: image2video
        await emit_step(4, 6, "逐镜生成视频", f"第1/{len(shots)}镜...")

        clip_on_progress = None
        if workflow_id:
            from app.services.sse_bus import sse_bus

            async def _clip_progress(elapsed: float, max_wait: float, status: str) -> None:
                await sse_bus.publish(workflow_id, "multi_image_video_progress", {
                    "skill": "multi_image_video",
                    "step": 4,
                    "total": 6,
                    "label": "逐镜生成视频",
                    "detail": f"轮询中 {elapsed:.0f}s/{max_wait:.0f}s 状态={status}",
                    "percent": 50 + int(elapsed / max_wait * 15),
                })

            clip_on_progress = _clip_progress

        shots = await _generate_shot_clips(
            shots=shots,
            ratio=params.ratio,
            shot_duration=params.shot_duration,
            user_id=user_id,
            provider=params.provider,
            on_progress=clip_on_progress,
            total_timeout=get_settings().multi_image_video_total_timeout,
        )

        # Step 5: 拼接
        await emit_step(5, 6, "拼接成片", "ffmpeg 拼接视频片段...")
        final_bytes, compose_degradation = await _compose_final(
            shots=shots, ratio=params.ratio, user_id=user_id, title=title,
        )
        degradation_notes.extend(compose_degradation)

        if not final_bytes:
            clip_urls = [s["clip_url"] for s in shots if s.get("clip_url")]
            return {
                "success": False,
                "error": "成片拼接失败",
                "degradation": degradation_notes,
                "clip_urls": clip_urls,
                "shots_count": len(shots),
            }

        # Step 6: 保存
        await emit_step(6, 6, "保存交付", "存储视频素材...")

        from app.services.asset_library import save_video_asset
        asset = await save_video_asset(
            user_id=user_id,
            filename=f"{title[:20]}_refine.mp4",
            content_type="video/mp4",
            data=final_bytes,
            source="ai",
            metadata={
                "source": "multi_image_video_refine",
                "prompt": params.prompt[:200],
                "ratio": params.ratio,
                "shots_count": len(shots),
                "degradation": degradation_notes,
            },
        )

        video_url = asset["original_url"]

        if workflow_id:
            from app.services.sse_bus import sse_bus
            card_draft = {
                "title": f"微调视频 - {title}",
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
            }
            await sse_bus.publish(workflow_id, "card_draft_ready", {
                "card_draft": card_draft,
                "png_urls": [],
                "html_urls": [],
            })

        return {
            "success": True,
            "mode": "refine",
            "asset_id": asset.get("asset_id") or asset.get("id"),
            "asset_url": video_url,
            "title": title,
            "shots_count": len(shots),
            "video_clips": sum(1 for s in shots if s.get("clip_mode") == "video"),
            "ken_burns_clips": sum(1 for s in shots if s.get("clip_mode") != "video"),
            "degradation": degradation_notes,
        }