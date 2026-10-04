# 素材处理流程

用户提供的素材（图片 / 视频 / 文字 / 数据）需要经过标准化清点、AI 补量和渲染路径分配，才能进入卡片/分镜生产。

## 一、素材清点与 AI 衡量

### 1. 脚本做确定性分析

```bash
python3 skills/openclaw/xhs-note-creator/scripts/analyze_material.py input.jpg \
  --out <work-dir>/reference/materials.json \
  --frames-dir <work-dir>/reference/frames \
  --frames-per-video 6
```

脚本做确定性的事：

- 按扩展名分类 `text / image / video / audio / unknown`
- 图片：读 `width / height / aspect`
- 视频：读 `duration_sec`、抽 N 帧存到 `frames-dir/`
- 文本：截取前 400 字预览
- 输出 `{ "materials": [...] }`，每条含空字段 `caption`、`usage`、`strategy`

### 2. AI 用多模态能力补全

打开 `materials.json`，对每条 image 和每个 video 的抽帧：

- 用 Read 工具**目视**查看
- 填 `caption`：10-40 字客观描述画面，不加情绪词
- 填 `usage`：这张图打算用在哪(`cover` / `content-3` / `ending` / `reference-only` / `discard`)
- 填 `strategy`：见本文第二节

### 3. 从素材反推观点

素材清点完后，再写长文原稿。**不要先写原稿再硬塞素材**——那会退化成纯文字帖 + 配图。正确顺序：

1. 素材里最强的 1-2 张/段 → 决定 `cover` 钩子
2. 其余素材按 `usage` 串成叙事线 → 决定 content 卡顺序
3. 缺口(没有素材支撑的论点) → 由 `html_card`(card-design 渲染)卡补

## 二、卡片渲染路径(3 条)

每张卡片在 `meta.json.cards[i].synthesis_strategy` 里必须标明走哪条路径。

### 策略 A：`html_card` — card-design HTML 卡（默认、最常用）

**适用**：纯文字卡 / 金句 / 数据卡 / 概念图 / 流程示意——凡是没有真实照片、要靠排版承载的卡，都走这条。

**做法**：交给 card-xiaohongshu——读 card-design 选风格锁 spec → 写 HTML → `render_card.py` 渲染 → `card_audit.py` 硬门禁。

### 策略 B：`text_on_photo` — 照片 + 文字叠加

**适用**：有一张构图干净的真实照片 + 一句强钩子(cover / ending 常用)。

```bash
python3 skills/openclaw/xhs-note-creator/scripts/text_on_image.py input.jpg output.jpg \
  --text "一句钩子" \
  --position top \
  --fit 3x4 \
  --size 72 \
  --color "#FFFFFF" \
  --bg "#000000AA"
```

- 文字长度 ≤18 字，更长先拆成两行
- 照片有水印先走 `crop_watermark.py`

### 策略 C：`collage` — 多图拼贴

**适用**：2-4 张素材互为补充(前后对比 / 多角度 / 步骤图)。

```bash
python3 skills/openclaw/xhs-note-creator/scripts/collage_3x4.py output.jpg \
  --layout 2v --inputs a.jpg b.jpg \
  --gap 12 --bg "#FFFFFF" --size 900x1200
```

| layout | 素材数 | 排列 | 常用场景 |
|---|---|---|---|
| `2v` | 2 | 上下 | 对比 before/after |
| `2h` | 2 | 左右 | 窄图配对(慎用) |
| `3` | 3 | 大图在上 + 两小图 | 主图 + 细节 |
| `4` | 4 | 2×2 | 步骤 / 多角度 |

## 三、图文 vs 视频的分流判断

- 用户明确说"视频" / "短视频" / "reels" → 走视频帖
- 用户素材里 ≥1 段可用视频(> 5 秒) → 默认建议视频帖，但由用户拍板
- 其余情况 → 走图文帖

视频帖仍然需要一张 `cover` 卡(3:4)作封面，合成策略同上。