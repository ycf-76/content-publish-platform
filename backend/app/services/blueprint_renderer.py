"""动态布局蓝图渲染器：根据大模型输出的 blueprint 拼接 HTML 并截图。

架构：
- LLM 输出 blueprint JSON（intent/style/pages），结构见 BLUEPRINT_SCHEMA
- render_from_blueprint(blueprint) → list[html] 每个 page 一份完整 HTML
- 截图函数复用 card_renderer.render_html_to_base64，每页一张 PNG

支持的 page type：
- cover        封面（大标题 + 话题标签 + 意图色块）
- pain_quote   痛点金句（大字引言 + 副标题）
- steps        步骤教程（编号卡片 + 标题 + 描述）
- comparison   对比测评（左右两栏对比）
- single_quote 单图金句（居中大字 + 装饰线）
- list_tips    清单提示（要点列表 + 序号徽章）

设计原则：
- CSS 组件样式锁定（圆角大、留白足、字体层级清晰），只替换文字
- 颜色从 blueprint.style 动态注入（CSS 变量 --primary / --bg / --font）
- 字号自适应：长文字通过 clamp() 自动缩小，禁止溢出容器
- 卡片尺寸固定 1080x1440（3:4 小红书竖图标准）
"""
from __future__ import annotations

import asyncio
import base64
import logging
from typing import Any

from app.services.card_renderer import render_html_to_base64

logger = logging.getLogger(__name__)

CARD_WIDTH = 1080
CARD_HEIGHT = 1440

# 支持的 page type
SUPPORTED_PAGE_TYPES = {
    "cover", "pain_quote", "steps", "comparison", "single_quote", "list_tips"
}

# Blueprint JSON Schema（文档用，运行时不强制校验）
BLUEPRINT_SCHEMA = {
    "intent": "string  # 用户意图，如 教程/吐槽/对比/励志",
    "style": {
        "primary_color": "#RRGGBB  # 主色",
        "bg_color": "#RRGGBB  # 背景色",
        "font_style": "sans-serif|serif  # 字体风格",
    },
    "pages": [
        # 每个 page 的 type 不同，数据字段不同，详见 _render_page_* 函数
    ],
}


# ============================================================================
# 全局 CSS 基础样式（颜色变量注入）
# ============================================================================

def _build_base_css(style: dict[str, str]) -> str:
    """生成基础 CSS，包含颜色变量 + 字体 + 重置。"""
    primary = style.get("primary_color", "#FF5A5F") or "#FF5A5F"
    bg = style.get("bg_color", "#FDFBF7") or "#FDFBF7"
    font_style = style.get("font_style", "sans-serif") or "sans-serif"
    # font_style 映射：sans-serif 用系统中文字体，serif 用宋体
    if font_style == "serif":
        font_family = "'Noto Serif SC', 'Source Han Serif SC', '宋体', SimSun, serif"
    else:
        font_family = "'PingFang SC', 'Microsoft YaHei', '微软雅黑', sans-serif"

    return f"""
:root {{
    --primary: {primary};
    --primary-soft: {primary}22;
    --primary-deep: {primary}DD;
    --bg: {bg};
    --bg-card: #FFFFFF;
    --text-primary: #1A1A1A;
    --text-secondary: #555555;
    --text-tertiary: #999999;
    --font-family: {font_family};
}}

* {{
    margin: 0;
    padding: 0;
    box-sizing: border-box;
    -webkit-font-smoothing: antialiased;
}}

html, body {{
    width: {CARD_WIDTH}px;
    height: {CARD_HEIGHT}px;
    font-family: var(--font-family);
    background: var(--bg);
    color: var(--text-primary);
    overflow: hidden;
}}

.card {{
    width: {CARD_WIDTH}px;
    height: {CARD_HEIGHT}px;
    padding: 80px 72px;
    display: flex;
    flex-direction: column;
    position: relative;
    overflow: hidden;
}}
"""


# ============================================================================
# 6 个组件 CSS（样式锁定，只替换文字）
# ============================================================================

# 1. cover 封面 -------------------------------------------------------------
def _render_page_cover(page: dict[str, Any]) -> str:
    """封面：大标题 + 副标题 + 话题标签 + 意图色块装饰。"""
    title = (page.get("title") or "").strip() or "今日分享"
    subtitle = (page.get("subtitle") or "").strip()
    tags = page.get("tags") or []
    intent = (page.get("intent") or "").strip()
    tags_html = "".join(f'<span class="tag">#{t}</span>' for t in tags[:6] if t)

    return f"""
<section class="card cover">
    <div class="cover-deco-top"></div>
    <div class="cover-content">
        {f'<div class="cover-intent">{intent}</div>' if intent else ''}
        <h1 class="cover-title">{title}</h1>
        {f'<p class="cover-subtitle">{subtitle}</p>' if subtitle else ''}
        <div class="cover-tags">{tags_html}</div>
    </div>
    <div class="cover-deco-bottom"></div>
</section>

<style>
.cover {{
    justify-content: center;
    align-items: center;
    text-align: center;
    background:
        radial-gradient(circle at 20% 20%, var(--primary-soft) 0%, transparent 50%),
        radial-gradient(circle at 80% 80%, var(--primary-soft) 0%, transparent 50%),
        var(--bg);
}}
.cover-deco-top, .cover-deco-bottom {{
    position: absolute;
    left: 50%;
    transform: translateX(-50%);
    width: 120px;
    height: 8px;
    border-radius: 4px;
    background: var(--primary);
}}
.cover-deco-top {{ top: 100px; }}
.cover-deco-bottom {{ bottom: 100px; }}
.cover-content {{ width: 100%; }}
.cover-intent {{
    display: inline-block;
    padding: 8px 28px;
    border: 2px solid var(--primary);
    border-radius: 999px;
    color: var(--primary);
    font-size: 28px;
    font-weight: 600;
    margin-bottom: 56px;
    letter-spacing: 4px;
}}
.cover-title {{
    font-size: clamp(48px, 6vw, 86px);
    font-weight: 800;
    line-height: 1.2;
    color: var(--text-primary);
    margin-bottom: 32px;
    word-break: break-word;
}}
.cover-subtitle {{
    font-size: clamp(28px, 3vw, 38px);
    color: var(--text-secondary);
    line-height: 1.5;
    margin-bottom: 56px;
    font-weight: 400;
}}
.cover-tags {{
    display: flex;
    flex-wrap: wrap;
    justify-content: center;
    gap: 16px;
}}
.cover-tags .tag {{
    padding: 10px 24px;
    background: var(--primary-soft);
    color: var(--primary-deep);
    border-radius: 999px;
    font-size: 26px;
    font-weight: 500;
}}
</style>
"""


# 2. pain_quote 痛点金句 ----------------------------------------------------
def _render_page_pain_quote(page: dict[str, Any]) -> str:
    """痛点金句：大字引言 + 副标题，引发共鸣。"""
    quote = (page.get("quote") or "").strip() or "是不是也经常这样？"
    subtext = (page.get("subtext") or "").strip()
    author = (page.get("author") or "").strip()

    return f"""
<section class="card pain-quote">
    <div class="pq-mark">"</div>
    <div class="pq-content">
        <p class="pq-quote">{quote}</p>
        {f'<p class="pq-subtext">{subtext}</p>' if subtext else ''}
        {f'<p class="pq-author">— {author}</p>' if author else ''}
    </div>
</section>

<style>
.pain-quote {{
    justify-content: center;
    align-items: center;
    background: var(--bg);
    position: relative;
}}
.pain-quote::before {{
    content: "";
    position: absolute;
    top: 0; left: 0; right: 0;
    height: 200px;
    background: linear-gradient(180deg, var(--primary-soft) 0%, transparent 100%);
}}
.pq-mark {{
    font-size: 240px;
    line-height: 1;
    color: var(--primary);
    font-family: Georgia, serif;
    margin-bottom: 20px;
    opacity: 0.6;
    position: relative;
}}
.pq-content {{
    width: 100%;
    text-align: center;
    position: relative;
}}
.pq-quote {{
    font-size: clamp(42px, 5vw, 64px);
    font-weight: 700;
    line-height: 1.4;
    color: var(--text-primary);
    margin-bottom: 40px;
    word-break: break-word;
}}
.pq-subtext {{
    font-size: clamp(28px, 3vw, 36px);
    color: var(--text-secondary);
    line-height: 1.5;
    margin-bottom: 32px;
    font-weight: 400;
}}
.pq-author {{
    font-size: 26px;
    color: var(--text-tertiary);
    font-style: italic;
}}
</style>
"""


# 3. steps 步骤教程 ---------------------------------------------------------
def _render_page_steps(page: dict[str, Any]) -> str:
    """步骤教程：编号卡片 + 标题 + 描述。"""
    title = (page.get("title") or "").strip() or "操作步骤"
    steps = page.get("steps") or []
    # 兜底：至少 3 个占位
    if not steps:
        steps = [{"title": "步骤一", "desc": "做好第一步"}, {"title": "步骤二", "desc": "继续推进"}, {"title": "步骤三", "desc": "完成收尾"}]

    steps_html = ""
    for i, s in enumerate(steps[:5]):
        s_title = (s.get("title") or "").strip() or f"步骤 {i+1}"
        s_desc = (s.get("desc") or "").strip()
        steps_html += f"""
        <div class="step-item">
            <div class="step-num">{i+1:02d}</div>
            <div class="step-body">
                <h3 class="step-title">{s_title}</h3>
                {f'<p class="step-desc">{s_desc}</p>' if s_desc else ''}
            </div>
        </div>
        """

    return f"""
<section class="card steps-card">
    <h2 class="card-title">{title}</h2>
    <div class="steps-list">
        {steps_html}
    </div>
</section>

<style>
.steps-card {{
    background: var(--bg);
}}
.card-title {{
    font-size: 48px;
    font-weight: 700;
    color: var(--text-primary);
    margin-bottom: 56px;
    padding-left: 24px;
    border-left: 8px solid var(--primary);
    line-height: 1.3;
}}
.steps-list {{
    display: flex;
    flex-direction: column;
    gap: 28px;
    flex: 1;
}}
.step-item {{
    display: flex;
    gap: 28px;
    padding: 24px 28px;
    background: var(--bg-card);
    border-radius: 24px;
    box-shadow: 0 4px 16px rgba(0,0,0,0.04);
    align-items: flex-start;
}}
.step-num {{
    flex-shrink: 0;
    width: 72px;
    height: 72px;
    border-radius: 20px;
    background: var(--primary);
    color: #FFFFFF;
    font-size: 32px;
    font-weight: 800;
    display: flex;
    align-items: center;
    justify-content: center;
}}
.step-body {{ flex: 1; min-width: 0; }}
.step-title {{
    font-size: clamp(28px, 3vw, 36px);
    font-weight: 600;
    color: var(--text-primary);
    line-height: 1.3;
    margin-bottom: 8px;
    word-break: break-word;
}}
.step-desc {{
    font-size: clamp(24px, 2.5vw, 28px);
    color: var(--text-secondary);
    line-height: 1.5;
    word-break: break-word;
}}
</style>
"""


# 4. comparison 对比测评 ----------------------------------------------------
def _render_page_comparison(page: dict[str, Any]) -> str:
    """对比测评：左右两栏对比，中间分隔线。"""
    title = (page.get("title") or "").strip() or "对比测评"
    left = page.get("left") or {}
    right = page.get("right") or {}
    left_title = (left.get("title") or "").strip() or "方案 A"
    right_title = (right.get("title") or "").strip() or "方案 B"
    left_points = left.get("points") or []
    right_points = right.get("points") or []
    if not left_points:
        left_points = ["优点一", "优点二", "缺点一"]
    if not right_points:
        right_points = ["优点一", "优点二", "缺点一"]

    def _points_html(points: list, is_left: bool) -> str:
        html = ""
        for p in points[:4]:
            p_text = (p if isinstance(p, str) else str(p.get("text", ""))).strip()
            if not p_text:
                continue
            icon = "✓" if is_left else "✗"
            cls = "pros" if is_left else "cons"
            html += f'<li class="cmp-{cls}"><span class="cmp-icon">{icon}</span><span>{p_text}</span></li>'
        return html

    return f"""
<section class="card comparison-card">
    <h2 class="card-title">{title}</h2>
    <div class="cmp-grid">
        <div class="cmp-col cmp-left">
            <div class="cmp-header">{left_title}</div>
            <ul class="cmp-list">{_points_html(left_points, True)}</ul>
        </div>
        <div class="cmp-divider"></div>
        <div class="cmp-col cmp-right">
            <div class="cmp-header">{right_title}</div>
            <ul class="cmp-list">{_points_html(right_points, False)}</ul>
        </div>
    </div>
</section>

<style>
.comparison-card {{
    background: var(--bg);
}}
.card-title {{
    font-size: 48px;
    font-weight: 700;
    color: var(--text-primary);
    margin-bottom: 56px;
    padding-left: 24px;
    border-left: 8px solid var(--primary);
    line-height: 1.3;
}}
.cmp-grid {{
    display: grid;
    grid-template-columns: 1fr 4px 1fr;
    gap: 32px;
    flex: 1;
}}
.cmp-col {{
    background: var(--bg-card);
    border-radius: 24px;
    padding: 36px 28px;
    display: flex;
    flex-direction: column;
}}
.cmp-divider {{
    background: linear-gradient(180deg, transparent, var(--primary), transparent);
    border-radius: 2px;
}}
.cmp-header {{
    font-size: 36px;
    font-weight: 700;
    color: var(--primary);
    margin-bottom: 32px;
    text-align: center;
    padding-bottom: 20px;
    border-bottom: 2px dashed var(--primary-soft);
}}
.cmp-list {{
    list-style: none;
    display: flex;
    flex-direction: column;
    gap: 20px;
    flex: 1;
}}
.cmp-list li {{
    display: flex;
    gap: 14px;
    align-items: flex-start;
    font-size: clamp(24px, 2.5vw, 28px);
    line-height: 1.4;
    color: var(--text-primary);
    word-break: break-word;
}}
.cmp-icon {{
    flex-shrink: 0;
    width: 36px;
    height: 36px;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 22px;
    font-weight: 700;
}}
.cmp-pros .cmp-icon {{ background: var(--primary-soft); color: var(--primary); }}
.cmp-cons .cmp-icon {{ background: #F5F5F5; color: var(--text-tertiary); }}
</style>
"""


# 5. single_quote 单图金句 --------------------------------------------------
def _render_page_single_quote(page: dict[str, Any]) -> str:
    """单图金句：居中大字 + 装饰线，适合励志/总结。"""
    quote = (page.get("quote") or "").strip() or "坚持就是胜利"
    subtext = (page.get("subtext") or "").strip()
    author = (page.get("author") or "").strip()

    return f"""
<section class="card single-quote">
    <div class="sq-line sq-line-top"></div>
    <div class="sq-content">
        <p class="sq-quote">{quote}</p>
        {f'<p class="sq-subtext">{subtext}</p>' if subtext else ''}
        {f'<p class="sq-author">— {author}</p>' if author else ''}
    </div>
    <div class="sq-line sq-line-bottom"></div>
</section>

<style>
.single-quote {{
    justify-content: center;
    align-items: center;
    background: var(--bg);
    text-align: center;
}}
.sq-line {{
    width: 80px;
    height: 4px;
    background: var(--primary);
    border-radius: 2px;
    margin: 0 auto;
}}
.sq-line-top {{ margin-bottom: 80px; }}
.sq-line-bottom {{ margin-top: 80px; }}
.sq-content {{ max-width: 900px; }}
.sq-quote {{
    font-size: clamp(48px, 5.5vw, 72px);
    font-weight: 800;
    line-height: 1.4;
    color: var(--text-primary);
    margin-bottom: 32px;
    word-break: break-word;
}}
.sq-subtext {{
    font-size: clamp(28px, 3vw, 36px);
    color: var(--text-secondary);
    line-height: 1.5;
    margin-bottom: 24px;
    font-weight: 400;
}}
.sq-author {{
    font-size: 26px;
    color: var(--text-tertiary);
    font-style: italic;
}}
</style>
"""


# 6. list_tips 清单提示 -----------------------------------------------------
def _render_page_list_tips(page: dict[str, Any]) -> str:
    """清单提示：要点列表 + 序号徽章，适合干货总结。"""
    title = (page.get("title") or "").strip() or "避坑清单"
    tips = page.get("tips") or page.get("items") or []
    if not tips:
        tips = ["要点一", "要点二", "要点三", "要点四"]

    tips_html = ""
    for i, t in enumerate(tips[:5]):
        t_text = (t if isinstance(t, str) else str(t.get("text") or t.get("title") or "")).strip()
        if not t_text:
            continue
        tips_html += f"""
        <div class="tip-item">
            <div class="tip-badge">{i+1}</div>
            <p class="tip-text">{t_text}</p>
        </div>
        """

    return f"""
<section class="card list-tips-card">
    <h2 class="card-title">{title}</h2>
    <div class="tips-list">
        {tips_html}
    </div>
</section>

<style>
.list-tips-card {{
    background: var(--bg);
}}
.card-title {{
    font-size: 48px;
    font-weight: 700;
    color: var(--text-primary);
    margin-bottom: 56px;
    padding-left: 24px;
    border-left: 8px solid var(--primary);
    line-height: 1.3;
}}
.tips-list {{
    display: flex;
    flex-direction: column;
    gap: 24px;
    flex: 1;
}}
.tip-item {{
    display: flex;
    gap: 24px;
    align-items: center;
    padding: 24px 32px;
    background: var(--bg-card);
    border-radius: 20px;
    border-left: 6px solid var(--primary);
    box-shadow: 0 4px 12px rgba(0,0,0,0.03);
}}
.tip-badge {{
    flex-shrink: 0;
    width: 56px;
    height: 56px;
    border-radius: 50%;
    background: var(--primary-soft);
    color: var(--primary);
    font-size: 30px;
    font-weight: 800;
    display: flex;
    align-items: center;
    justify-content: center;
}}
.tip-text {{
    font-size: clamp(26px, 2.8vw, 32px);
    font-weight: 500;
    color: var(--text-primary);
    line-height: 1.4;
    word-break: break-word;
}}
</style>
"""


# ============================================================================
# page type → 渲染函数映射
# ============================================================================

_PAGE_RENDERERS = {
    "cover": _render_page_cover,
    "pain_quote": _render_page_pain_quote,
    "steps": _render_page_steps,
    "comparison": _render_page_comparison,
    "single_quote": _render_page_single_quote,
    "list_tips": _render_page_list_tips,
}


def _wrap_full_html(body: str, base_css: str) -> str:
    """拼接完整 HTML 文档。"""
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=1080">
{base_css}
</head>
<body>
{body}
</body>
</html>"""


def render_from_blueprint(blueprint: dict[str, Any]) -> list[str]:
    """根据 blueprint 中的 pages 动态拼接 HTML，返回每个 page 一份完整 HTML 字符串。

    Args:
        blueprint: {
            "intent": str,
            "style": {primary_color, bg_color, font_style},
            "pages": [{type, ...}, ...]
        }

    Returns:
        list[str]: 每个 page 一份完整 HTML（含 <style>），可直接用于截图

    Raises:
        ValueError: blueprint 结构无效或 page type 不支持
    """
    if not isinstance(blueprint, dict):
        raise ValueError("blueprint 必须是 dict")

    pages = blueprint.get("pages")
    if not isinstance(pages, list) or not pages:
        raise ValueError("blueprint.pages 必须是非空 list")

    style = blueprint.get("style") or {}
    if not isinstance(style, dict):
        style = {}

    base_css = _build_base_css(style)
    html_list: list[str] = []

    for i, page in enumerate(pages):
        if not isinstance(page, dict):
            logger.warning(f"[blueprint] page[{i}] 非 dict，跳过: {type(page)}")
            continue
        page_type = page.get("type", "")
        if page_type not in _PAGE_RENDERERS:
            logger.warning(f"[blueprint] page[{i}] 未知 type {page_type!r}，跳过")
            continue
        renderer = _PAGE_RENDERERS[page_type]
        body = renderer(page)
        full_html = _wrap_full_html(body, base_css)
        html_list.append(full_html)

    if not html_list:
        raise ValueError(
            f"blueprint 没有可渲染的 page，支持的 type: {sorted(SUPPORTED_PAGE_TYPES)}"
        )

    logger.info(
        f"[blueprint] rendered {len(html_list)} pages, "
        f"intent={blueprint.get('intent', '')!r}"
    )
    return html_list


# ============================================================================
# 截图函数：对 blueprint 生成的 HTML 批量截图
# ============================================================================

async def render_blueprint_to_images(
    blueprint: dict[str, Any],
    max_pages: int = 4,
) -> list[dict[str, Any]]:
    """根据 blueprint 渲染多张卡片 PNG。

    Args:
        blueprint: 蓝图 dict（含 intent/style/pages）
        max_pages: 最多渲染几张（小红书笔记通常 4 张），超出截断

    Returns:
        [
            {
                "index": 0,
                "type": "cover",
                "image_base64": "iVBOR...",  # 裸 base64
                "description": "封面",
            },
            ...
        ]

    Raises:
        ValueError: blueprint 无效
        RuntimeError: 渲染失败
    """
    pages = blueprint.get("pages") or []
    if len(pages) > max_pages:
        logger.info(
            f"[blueprint] pages={len(pages)} 超过 max_pages={max_pages}，截断"
        )
        pages = pages[:max_pages]
        blueprint = {**blueprint, "pages": pages}

    html_list = render_from_blueprint(blueprint)

    async def _render_one(idx: int, page: dict[str, Any], html: str) -> dict[str, Any]:
        page_type = page.get("type", "unknown")
        try:
            b64 = await render_html_to_base64(html, CARD_WIDTH, CARD_HEIGHT)
            return {
                "index": idx,
                "type": page_type,
                "image_base64": b64,
                "description": _PAGE_DESCRIPTIONS.get(page_type, page_type),
            }
        except Exception as e:
            logger.error(f"[blueprint] page[{idx}] ({page_type}) 渲染失败: {e}")
            raise

    # 并行渲染（card_renderer 内部用单线程池串行，这里并行提交任务）
    tasks = [
        _render_one(i, page, html)
        for i, (page, html) in enumerate(zip(pages, html_list))
    ]
    results = await asyncio.gather(*tasks)

    logger.info(
        f"[blueprint] render_blueprint_to_images OK: "
        f"{len(results)} pages, intent={blueprint.get('intent', '')!r}"
    )
    return list(results)


# page type → 中文描述
_PAGE_DESCRIPTIONS = {
    "cover": "封面",
    "pain_quote": "痛点金句",
    "steps": "步骤教程",
    "comparison": "对比测评",
    "single_quote": "金句总结",
    "list_tips": "清单提示",
}
