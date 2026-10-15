# 方案B：多图参考视频生成流水线 — 策划书

> 版本：v1.0 | 日期：2026-10-12
> 状态：Phase 1 后端核心 ✅ 已完成 | Phase 2 前端 待实现

---

## 1. 目标

用户上传多张场景参考图 + 文字描述，系统自动编排为一条完整短视频：

```
3张场景图 + "从全景推到特写，再摇向窗外"
  → LLM看图理解场景语义
  → 输出逐镜头脚本（每镜含 text2image 提示词 + 运动指令）
  → text2image 生成分镜关键帧
  → image2video 每帧生成 5s 视频片段
  → ffmpeg 拼接成片
  → 侧边栏可播放
```

**核心差异（vs 现有 auto_short_video）**：

| | auto_short_video（现有） | 本方案（新增） |
|---|---|---|
| 输入 | 纯文字主题 | **多张参考图 + 文字描述** |
| 画面来源 | text2image 纯靠 prompt | **参考图语义 → VL理解 → 分镜图保持场景/角色一致** |
| 视频生成 | ken-burns 图片缓动（假视频） | **image2video 真视频（每帧 5s 片段）** |
| 拼接 | ffmpeg 图片序列 + ken-burns | **ffmpeg 视频片段 concat** |
| 角色/场景一致性 | 无保证 | **VL 理解参考图 → prompt 引用 → 分镜图保持一致** |

---

## 2. 架构总览

```
┌─────────────────────────────────────────────────────────────────┐
│  MultiImageVideoSkill (新 Skill)                                │
│                                                                 │
│  Step 1: VL 理解参考图                                          │
│    QwenVLAdapter.chat(images + "描述这些图片的场景/角色/道具")    │
│    → scene_description: {角色, 场景, 道具, 色彩, 构图}          │
│                                                                 │
│  Step 2: LLM 编排分镜脚本                                       │
│    LLM.chat(scene_description + user_prompt)                    │
│    → storyboard: {shots: [{caption, image_prompt, motion, dur}]}│
│                                                                 │
│  Step 3: text2image 生成分镜关键帧                               │
│    WanxAdapter.generate(shot.image_prompt) × N                  │
│    → shot_frames: [asset_id, ...]                               │
│                                                                 │
│  Step 4: image2video 逐帧生视频                                 │
│    DashScopeVideoAdapter.image2video(frame, motion_prompt) × N  │
│    → shot_clips: [video_bytes, ...]                             │
│                                                                 │
│  Step 5: ffmpeg 拼接成片                                        │
│    compose_video(storyboard) → final.mp4                        │
│                                                                 │
│  Step 6: 存 asset_library + 发 SSE 事件                         │
│    save_video_asset() + sse_bus.publish("card_draft_ready")     │
└─────────────────────────────────────────────────────────────────┘
```

---

## 3. 与现有模块的关系

### 3.1 复用（不改）

| 模块 | 路径 | 复用方式 |
|------|------|----------|
| QwenVLAdapter | `app/adapters/qwen_vl.py` | Step 1 直接调用，传多图 content |
| WanxAdapter | `app/adapters/image_gen.py` | Step 3 直接调用 text2img |
| DashScopeVideoAdapter | `app/adapters/video_gen.py` | Step 4 直接调用 image2video |
| compose_video | `app/adapters/video_compose.py` | Step 5 直接调用 |
| save_video_asset | `app/services/asset_library.py` | Step 6 存视频 |
| sse_bus | `app/services/sse_bus.py` | Step 6 发事件 |
| Skill 基类 | `app/core/skill_base.py` | 新 Skill 继承 |

### 3.2 新增

| 模块 | 路径 | 说明 |
|------|------|------|
| MultiImageVideoSkill | `app/skills/produce/multi_image_video.py` | 主编排 Skill |
| VL 场景理解 prompt | 同上，内置常量 | Step 1 的 VL 提示词 |
| 分镜编排 prompt | 同上，内置常量 | Step 2 的 LLM 提示词 |
| _resolve_image_urls | 同上，辅助函数 | asset_id[] → URL[] |
| _vl_understand_images | 同上，辅助函数 | 多图 → 场景描述 |
| _generate_storyboard | 同上，辅助函数 | 场景描述 + 用户描述 → 分镜脚本 |
| _generate_shot_frames | 同上，辅助函数 | 分镜脚本 → 关键帧图片 |
| _generate_shot_clips | 同上，辅助函数 | 关键帧 → 视频片段 |
| _compose_final | 同上，辅助函数 | 视频片段 → 成片 |

### 3.3 需小改

| 模块 | 改动 | 原因 |
|------|------|------|
| `app/adapters/video_compose.py` | 支持 video 片段输入（现有只支持 image+ken-burns） | Step 5 需要拼接视频片段而非图片 |
| `app/config.py` | 新增 `dashscope_i2v_model` 配置项 | image2video 模型名与 text2video 不同 |

---

## 4. 详细设计

### 4.1 Input Schema

```python
class MultiImageVideoInput(BaseModel):
    image_asset_ids: list[str] = Field(
        min_length=1,
        max_length=9,
        description="参考图 asset_id 列表（1-9 张）",
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
        description="画幅比",
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
        description="视频生成 provider（None 用系统默认）",
    )
```

### 4.2 Step 1: VL 理解参考图

**输入**：N 张图片 URL + 固定 prompt
**输出**：结构化场景描述 JSON

```python
_VL_SCENE_PROMPT = """你是一个专业的视频策划师。请仔细观察以下参考图片，分析并输出 JSON：

{{
  "scenes": [
    {{
      "image_index": 1,
      "location": "场景地点",
      "subjects": ["主体1", "主体2"],
      "props": ["道具1", "道具2"],
      "lighting": "光线描述",
      "color_tone": "色调",
      "composition": "构图描述",
      "mood": "情绪氛围"
    }}
  ],
  "cross_scene": {{
    "shared_subjects": ["跨场景出现的主体"],
    "visual_style": "统一视觉风格",
    "color_system": "色彩体系"
  }}
}}

要求：
- 每张图单独分析，image_index 从 1 开始
- cross_scene 描述多图之间的关联（重复出现的角色/道具/场景）
- 描述要具体到可用于 AI 生图的提示词
"""
```

**实现**：调用 `QwenVLAdapter.chat()`，messages 中每张图作为 `{"image": url}` content 传入。

**降级**：VL 不可用时，跳过 Step 1，直接用用户 prompt 编排分镜（退化为 auto_short_video 模式）。

### 4.3 Step 2: LLM 编排分镜脚本

**输入**：VL 场景描述 + 用户 prompt + 目标时长 + 风格
**输出**：分镜脚本 JSON

```python
_STORYBOARD_PROMPT = """你是一个专业的短视频导演。根据以下参考图分析和用户描述，编排逐镜头脚本。

参考图分析：
{scene_description}

用户描述：{user_prompt}
目标时长：{duration}秒
风格：{style}
每镜头时长：{shot_duration}秒

请输出 JSON（不要 markdown 代码块）：
{{
  "title": "视频标题",
  "total_shots": N,
  "shots": [
    {{
      "shot_index": 1,
      "caption": "这镜头的口播/字幕文案",
      "image_prompt": "关键帧画面描述（英文，用于 AI 生图，要具体有画面感）",
      "motion_prompt": "镜头运动描述（如：缓慢推进、从左摇到右、俯拍拉远）",
      "reference_images": [1],
      "duration": 5.0,
      "transition": "cut"
    }}
  ]
}}

要求：
- reference_images 引用 Step 1 分析的图片编号，表示这镜参考哪张图
- image_prompt 要保持与参考图的角色/场景/道具一致
- motion_prompt 描述镜头运动，用于 image2video 的 prompt
- 分镜数 = 目标时长 / 每镜时长
- transition: cut / dissolve / wipe
- 第一个镜头要有 hook（3秒内抓住注意力）
"""
```

**实现**：调用项目 LLM（DeepSeek/Qwen），解析 JSON。

**降级**：JSON 解析失败时，生成默认分镜（每张参考图一镜 + 用户 prompt）。

### 4.4 Step 3: text2image 生成分镜关键帧

**输入**：分镜脚本的 `image_prompt` 列表
**输出**：每镜的关键帧图片 asset_id + URL

**实现**：
```python
for shot in storyboard["shots"]:
    img_bytes = await wanx_adapter.generate(
        prompt=shot["image_prompt"],
        size=size_for_ratio,
    )
    asset = await save_asset(user_id, filename, "image/png", img_bytes, source="ai")
    shot["frame_asset_id"] = asset["id"]
    shot["frame_url"] = asset["original_url"]
```

**并发**：最多 3 个并发（避免 API 限流）。

**降级**：某镜生图失败时，用对应参考图作为关键帧（fallback to reference image）。

### 4.5 Step 4: image2video 逐帧生视频

**输入**：每镜的关键帧图片 URL + motion_prompt
**输出**：每镜的视频片段 bytes

**实现**：
```python
for shot in storyboard["shots"]:
    video_bytes = await video_adapter.image2video(
        image=shot["frame_url"],
        prompt=shot["motion_prompt"],
        ratio=ratio,
        duration=shot_duration,
        on_progress=on_progress,
    )
    clip_asset = await save_video_asset(user_id, filename, "video/mp4", video_bytes, source="ai")
    shot["clip_url"] = clip_asset["original_url"]
```

**并发**：串行（视频生成耗时长，避免同时占多个 API 配额）。

**降级**：某镜 image2video 失败时，该镜退化为 ken-burns 图片缓动（复用现有 compose_video 的 image_motion 能力）。

### 4.6 Step 5: ffmpeg 拼接成片

**输入**：视频片段 URL 列表 + 分镜脚本（含 transition）
**输出**：final.mp4 bytes

**实现**：需要扩展 `video_compose.py` 支持视频片段拼接模式。

现有 `compose_video` 只支持 image+ken-burns 模式。新增 `video_concat` 模式：

```python
async def compose_video_concat(
    clips: list[str],       # 视频片段文件路径列表
    transitions: list[str], # 每个片段间的转场类型
    output_path: str,
) -> Path:
    """拼接视频片段。

    ffmpeg -i clip1.mp4 -i clip2.mp4 -i clip3.mp4
      -filter_complex "[0:v][1:v]xfade=transition=fade:duration=0.5[v01];
                       [v01][2:v]xfade=transition=fade:duration=0.5[vout]"
      -map "[vout]" output.mp4
    """
```

**转场支持**：
- `cut`：直接拼接（无转场）
- `dissolve`/`fade`：xfade filter，duration 0.5s
- `wipe`：xfade transition=wipeleft

### 4.7 Step 6: 存 asset + 发 SSE

与现有 `GenerateVideoSkill` 同模式：

```python
asset = await save_video_asset(user_id, filename, "video/mp4", final_bytes, source="ai", metadata={...})

await sse_bus.publish(workflow_id, "card_draft_ready", {
    "card_draft": {
        "title": title,
        "template": "video",
        "pages": [{"id": "page_video", "type": "content", "mediaType": "video",
                   "videoUrl": asset["original_url"], ...}],
    },
})
```

---

## 5. SSE 进度事件

全流程 6 步，每步发进度：

```python
await sse_bus.publish(workflow_id, "multi_image_video_progress", {
    "skill": "multi_image_video",
    "step": step,          # 1-6
    "total": 6,
    "label": "VL理解参考图",  # 每步的中文标签
    "detail": "分析第2张图...",
    "percent": pct,
    "shots_total": N,      # Step 3-4 时有
    "shots_done": i,       # 当前完成第几镜
})
```

| step | label | detail 示例 |
|------|-------|-------------|
| 1 | VL理解参考图 | "分析3张参考图..." |
| 2 | 编排分镜脚本 | "生成5镜分镜..." |
| 3 | 生成分镜关键帧 | "第2/5镜生图..." |
| 4 | 逐镜生成视频 | "第3/5镜生成视频（约15s）..." |
| 5 | 拼接成片 | "ffmpeg 拼接5个片段..." |
| 6 | 保存交付 | "存储视频素材..." |

---

## 6. 降级策略（零件可缺）

| 环节 | 降级条件 | 降级行为 | 用户体验 |
|------|----------|----------|----------|
| Step 1 VL | DASHSCOPE_API_KEY 未配置 / VL 调用失败 | 跳过 VL，直接用用户 prompt 编排 | 分镜图与参考图无关，但流程完整 |
| Step 2 LLM | LLM 不可用 / JSON 解析失败 | 用默认分镜（每图一镜 + 用户 prompt） | 分镜简单但可用 |
| Step 3 text2image | 万相 API 不可用 / 某镜失败 | 用参考图原片作为关键帧 | 画面即参考图，无 AI 增强 |
| Step 4 image2video | 视频 API 不可用 / 某镜失败 | 该镜退化为 ken-burns 图片缓动 | 部分镜头是静态缓动，部分是真视频 |
| Step 5 compose | ffmpeg 不可用 | 返回各片段 URL 列表，不拼接 | 用户看到多个片段而非成片 |

---

## 7. 配置项

```python
# app/config.py 新增

dashscope_i2v_model: str = Field(
    default="wan2.1-i2v-turbo",
    description="通义万相图生视频模型（wan2.1-i2v-turbo / wan2.1-i2v-plus）",
)
multi_image_video_max_concurrent_frames: int = Field(
    default=3,
    description="分镜关键帧生图最大并发数",
)
multi_image_video_vl_model: str = Field(
    default="qwen-vl-max",
    description="VL 理解参考图用的模型",
)
```

---

## 8. 前端改动

### 8.1 新增：参考图上传 UI

在聊天输入框旁新增"上传参考图"按钮，支持多选（最多 9 张）。

上传后图片存入 asset_library，前端记住 `asset_id` 列表，在调用 Skill 时传入 `image_asset_ids`。

### 8.2 进度展示

监听 `multi_image_video_progress` SSE 事件，展示 6 步进度条 + 当前步骤描述。

### 8.3 侧边栏预览

复用已修复的 VideoPreview 组件，无需额外改动。

---

## 9. 实现计划

### Phase 1：后端核心（2 天）

| 序号 | 任务 | 产出 | 预估 |
|------|------|------|------|
| 1.1 | 创建 `multi_image_video.py` Skill 骨架 | Skill 注册 + Input Schema | 0.5h |
| 1.2 | 实现 `_resolve_image_urls` | asset_id[] → URL[] | 0.5h |
| 1.3 | 实现 Step 1 `_vl_understand_images` | QwenVL 多图调用 + JSON 解析 | 1h |
| 1.4 | 实现 Step 2 `_generate_storyboard` | LLM 编排 + JSON 解析 + 降级 | 1h |
| 1.5 | 实现 Step 3 `_generate_shot_frames` | WanxAdapter 并发生图 | 1h |
| 1.6 | 实现 Step 4 `_generate_shot_clips` | image2video 串行 + 降级 | 1h |
| 1.7 | 扩展 `video_compose.py` 支持 video_concat | ffmpeg xfade 拼接 | 2h |
| 1.8 | 实现 Step 5-6 拼接 + 存储 + SSE | 完整链路 | 1h |
| 1.9 | 配置项 + .env.example 更新 | 新增 3 个配置 | 0.5h |
| 1.10 | 单元测试 | mock 全链路测试 | 2h |

### Phase 2：前端（1 天）

| 序号 | 任务 | 产出 | 预估 |
|------|------|------|------|
| 2.1 | 参考图上传 UI | 多图选择 + asset 上传 | 2h |
| 2.2 | Skill 调用集成 | image_asset_ids 传入 | 1h |
| 2.3 | 进度展示 | 6 步进度条 | 1h |

### Phase 3：联调 + 优化（0.5 天）

| 序号 | 任务 | 产出 | 预估 |
|------|------|------|------|
| 3.1 | 端到端联调 | 完整流程跑通 | 2h |
| 3.2 | 降级场景测试 | 各环节降级验证 | 1h |
| 3.3 | 性能优化 | 并发控制 + 超时调优 | 1h |

**总预估：3.5 天**

---

## 10. 风险与应对

| 风险 | 概率 | 影响 | 应对 |
|------|------|------|------|
| Qwen-VL 多图调用不稳定 | 中 | Step 1 失败 | 降级到纯 prompt 编排 |
| image2video 单次耗时 30-60s，9 镜需 5-9 分钟 | 高 | 用户等待久 | SSE 实时进度 + 预估剩余时间 |
| image2video 角色一致性不足 | 中 | 相邻镜头角色不连贯 | LLM prompt 强化角色描述 + 参考图引用 |
| ffmpeg xfade 转场兼容性 | 低 | 拼接失败 | fallback 到 concat demuxer（无转场直接拼） |
| 万相/可灵 API 限流 | 中 | Step 3/4 部分失败 | 降级到 ken-burns + 重试 |

---

## 11. 成功标准

1. 用户上传 3 张场景图 + 描述 → 30s 内出分镜脚本 → 5-9 分钟出成片
2. 成片在侧边栏可播放，视频流畅无卡顿
3. VL 不可用时自动降级，流程不中断
4. 视频 API 不可用时部分镜头退化为 ken-burns，成片仍可播放
5. 全程 SSE 进度可见，用户知道当前在做什么