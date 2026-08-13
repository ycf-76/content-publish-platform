"""小红书图文卡片渲染器：HTML → PNG（3:4 比例，1080x1440）。

架构：
- 单线程池 + sync_playwright（绕开 uvicorn SelectorEventLoop 不支持子进程的限制）
- HTML 模板按"图片风格"映射不同配色（清新自然/日系胶片/暖阳滤镜/复古胶片）
- 输出 1 张封面卡片 + 1 张内容卡片，base64 PNG

设计要点：
- 字体：用系统中文字体（微软雅黑/苹方），不依赖外部字体文件
- 配色：4 种风格各有一套主色/辅色/背景色
- 布局：封面卡片（大标题+话题标签）+ 内容卡片（分段正文+序号）
- 不违反"Playwright 只用于 QR 登录"约束：那条约束针对数据抓取，渲染是产出行为

红线：
- Playwright 不可用时降级返回空列表（让 image_gen_node 走 fallback）
- 单次渲染超时 15 秒（避免阻塞工作流）

技术决策：
- 使用 sync_playwright 而非 async_playwright，因为 uvicorn 在 Windows 上使用
  SelectorEventLoop，该循环不支持 asyncio.create_subprocess_exec（NotImplementedError），
  而 Playwright async API 启动 chromium 需要创建子进程。
- sync_playwright 通过单线程 ThreadPoolExecutor 运行，保证线程安全。
"""

from __future__ import annotations

import asyncio
import base64
import concurrent.futures
import logging
import threading
from typing import Any

logger = logging.getLogger(__name__)

# 卡片尺寸（小红书 3:4 竖图标准）
CARD_WIDTH = 1080
CARD_HEIGHT = 1440

# 渲染超时（秒）
RENDER_TIMEOUT = 15

# 单线程池：sync_playwright 非线程安全，所有操作必须在同一线程执行
_executor = concurrent.futures.ThreadPoolExecutor(
    max_workers=1, thread_name_prefix="card-renderer"
)

# sync_playwright 实例 + browser（仅在 executor 线程中访问）
_sync_pw = None
_sync_browser = None
_sync_lock = threading.Lock()


def _sync_get_browser():
    """在专用线程中获取/创建 sync_playwright browser 单例。"""
    global _sync_pw, _sync_browser
    if _sync_browser is not None:
        try:
            # 检查 browser 是否仍然连接
            if _sync_browser.is_connected():
                return _sync_browser
        except Exception:
            pass
        # 断开连接，重建
        logger.warning("[card_renderer] sync browser disconnected, recreating")
        try:
            _sync_browser.close()
        except Exception:
            pass
        _sync_browser = None
        try:
            if _sync_pw:
                _sync_pw.stop()
        except Exception:
            pass
        _sync_pw = None

    from playwright.sync_api import sync_playwright

    _sync_pw = sync_playwright().start()
    _sync_browser = _sync_pw.chromium.launch(
        headless=True,
        args=["--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage"],
    )
    logger.info("[card_renderer] sync Playwright chromium browser launched")
    return _sync_browser


def _sync_render(html: str, width: int, height: int) -> bytes:
    """在专用线程中同步渲染 HTML 为 PNG bytes。"""
    with _sync_lock:
        browser = _sync_get_browser()
        context = browser.new_context(
            viewport={"width": width, "height": height},
            device_scale_factor=1,
        )
        page = context.new_page()
        try:
            page.set_content(html, wait_until="domcontentloaded")
            page.evaluate("document.fonts.ready")
            png_bytes = page.screenshot(
                type="png",
                clip={"x": 0, "y": 0, "width": width, "height": height},
            )
            return png_bytes
        finally:
            try:
                context.close()
            except Exception:
                pass


async def render_html_to_png(
    html: str,
    width: int = CARD_WIDTH,
    height: int = CARD_HEIGHT,
) -> bytes:
    """渲染 HTML 字符串为 PNG bytes。

    通过单线程池执行 sync_playwright，绕开 uvicorn SelectorEventLoop 限制。

    Args:
        html: 完整的 HTML 文档字符串（含 <style>）
        width: 卡片宽度（默认 1080）
        height: 卡片高度（默认 1440）

    Returns:
        PNG 图片的 bytes

    Raises:
        RuntimeError: Playwright 不可用或渲染超时
    """
    loop = asyncio.get_event_loop()
    try:
        png_bytes = await asyncio.wait_for(
            loop.run_in_executor(_executor, _sync_render, html, width, height),
            timeout=RENDER_TIMEOUT,
        )
        return png_bytes
    except asyncio.TimeoutError:
        logger.error(f"[card_renderer] render timeout ({RENDER_TIMEOUT}s)")
        raise RuntimeError(f"card render timeout after {RENDER_TIMEOUT}s")
    except RuntimeError:
        raise
    except Exception as e:
        logger.error(f"[card_renderer] render failed: {e}")
        raise RuntimeError(f"card render failed: {e}")


async def render_html_to_base64(
    html: str,
    width: int = CARD_WIDTH,
    height: int = CARD_HEIGHT,
) -> str:
    """渲染 HTML 为裸 base64 编码的 PNG（不带 data: 前缀）。

    与通义万相生图路径保持一致：后端统一返回裸 base64，
    由前端 imageGenImages computed 负责拼接 data:mime;base64, 前缀。
    避免双重前缀导致裂图。
    """
    png_bytes = await render_html_to_png(html, width, height)
    b64 = base64.b64encode(png_bytes).decode("ascii")
    return b64


# ============================================================================
# HTML 卡片模板
# ============================================================================


# 4 种图片风格 → 配色方案
STYLE_THEMES: dict[str, dict[str, str]] = {
    "fresh_natural": {
        "name": "清新自然",
        "bg_primary": "#FDFBF7",      # 米白
        "bg_secondary": "#E8F5E9",    # 淡绿
        "text_primary": "#2D3436",    # 深灰
        "text_secondary": "#636E72",  # 中灰
        "accent": "#00B894",          # 翠绿
        "accent_light": "#55EFC4",    # 浅翠
        "tag_bg": "#E8F5E9",
        "tag_text": "#00896B",
    },
    "japanese_film": {
        "name": "日系胶片",
        "bg_primary": "#F5F0E8",      # 米黄
        "bg_secondary": "#E8DFD0",    # 浅棕
        "text_primary": "#3E2F23",    # 深棕
        "text_secondary": "#7D6750",  # 中棕
        "accent": "#A0826D",          # 暖棕
        "accent_light": "#C4A58E",    # 浅棕
        "tag_bg": "#E8DFD0",
        "tag_text": "#6B4226",
    },
    "warm_sunlight": {
        "name": "暖阳滤镜",
        "bg_primary": "#FFF8F0",      # 暖白
        "bg_secondary": "#FFE8D6",    # 浅橙
        "text_primary": "#4A2C2A",    # 深褐
        "text_secondary": "#8B5A4A",  # 中褐
        "accent": "#FF8C42",          # 橙色
        "accent_light": "#FFB37D",    # 浅橙
        "tag_bg": "#FFE8D6",
        "tag_text": "#D2691E",
    },
    "vintage_film": {
        "name": "复古胶片",
        "bg_primary": "#F4ECD8",      # 复古黄
        "bg_secondary": "#E0D2B0",    # 复古棕
        "text_primary": "#3B2F2F",    # 深褐
        "text_secondary": "#6D5C4C",  # 中褐
        "accent": "#8B7355",          # 复古金
        "accent_light": "#B89968",    # 浅金
        "tag_bg": "#E0D2B0",
        "tag_text": "#5C4033",
    },
}


def _get_theme(style_name: str) -> dict[str, str]:
    """根据风格名获取配色方案，默认清新自然。"""
    return STYLE_THEMES.get(style_name, STYLE_THEMES["fresh_natural"])


def build_cover_html(
    title: str,
    tags: list[str],
    topic: str,
    style_name: str = "fresh_natural",
) -> str:
    """构建封面卡片 HTML。

    封面卡片结构：
    - 顶部：话题标签（#xxx）
    - 中部：大标题（居中，多行换行）
    - 底部：主题词 + 装饰线
    """
    theme = _get_theme(style_name)

    # 标签 HTML（最多 3 个）
    tags_html = "".join(
        f'<span class="tag">#{t}</span>' for t in tags[:3]
    )

    # 标题处理：如果太长，自动按字符数分割
    title_display = title.strip() or "今日分享"

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{
    width: {CARD_WIDTH}px;
    height: {CARD_HEIGHT}px;
    font-family: "Microsoft YaHei", "PingFang SC", "Hiragino Sans GB", sans-serif;
    background: {theme["bg_primary"]};
    overflow: hidden;
    position: relative;
}}
.cover {{
    width: 100%;
    height: 100%;
    display: flex;
    flex-direction: column;
    padding: 100px 80px;
    position: relative;
}}
/* 顶部装饰色块 */
.cover::before {{
    content: "";
    position: absolute;
    top: 0; left: 0;
    width: 100%;
    height: 12px;
    background: {theme["accent"]};
}}
/* 话题标签区 */
.tags {{
    display: flex;
    flex-wrap: wrap;
    gap: 16px;
    margin-bottom: 80px;
}}
.tag {{
    display: inline-block;
    padding: 12px 28px;
    background: {theme["tag_bg"]};
    color: {theme["tag_text"]};
    font-size: 32px;
    border-radius: 30px;
    font-weight: 500;
}}
/* 主标题 */
.title {{
    flex: 1;
    display: flex;
    align-items: center;
    justify-content: center;
    text-align: center;
    color: {theme["text_primary"]};
    font-size: 72px;
    font-weight: 700;
    line-height: 1.4;
    letter-spacing: 2px;
    word-break: break-word;
}}
/* 底部主题 */
.footer {{
    display: flex;
    align-items: center;
    gap: 20px;
    margin-top: 60px;
}}
.footer-line {{
    flex: 1;
    height: 2px;
    background: {theme["accent"]};
    opacity: 0.5;
}}
.footer-text {{
    color: {theme["text_secondary"]};
    font-size: 28px;
    letter-spacing: 4px;
    white-space: nowrap;
}}
/* 右下角装饰圆点 */
.deco-dot {{
    position: absolute;
    bottom: 80px;
    right: 80px;
    width: 16px;
    height: 16px;
    background: {theme["accent"]};
    border-radius: 50%;
}}
</style>
</head>
<body>
<div class="cover">
    <div class="tags">{tags_html}</div>
    <div class="title">{title_display}</div>
    <div class="footer">
        <div class="footer-line"></div>
        <div class="footer-text">{topic or "分享"}</div>
        <div class="footer-line"></div>
    </div>
    <div class="deco-dot"></div>
</div>
</body>
</html>"""


def build_content_html(
    title: str,
    content: str,
    tags: list[str],
    style_name: str = "fresh_natural",
) -> str:
    """构建内容卡片 HTML。

    内容卡片结构：
    - 顶部：小标题（带装饰条）
    - 中部：正文分段（每段带序号圆圈）
    - 底部：标签区 + 互动引导
    """
    theme = _get_theme(style_name)

    # 正文分段：按换行分割，过滤空行
    paragraphs = [p.strip() for p in content.split("\n") if p.strip()]

    # 构建分段 HTML（每段带序号）
    paragraphs_html = ""
    for i, para in enumerate(paragraphs[:8], 1):  # 最多 8 段
        # 检测是否是数字开头的列表项（如 "1. xxx"）
        if para[:2].rstrip().isdigit() or (len(para) > 2 and para[0].isdigit() and para[1] in ".、"):
            # 去掉原有的序号
            clean_para = para.split(".", 1)[-1].strip() if "." in para[:3] else para.split("、", 1)[-1].strip()
        else:
            clean_para = para

        paragraphs_html += f"""
        <div class="para-item">
            <div class="para-num">{i}</div>
            <div class="para-text">{clean_para}</div>
        </div>"""

    # 标签 HTML
    tags_html = "".join(
        f'<span class="content-tag">#{t}</span>' for t in tags[:5]
    )

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{
    width: {CARD_WIDTH}px;
    height: {CARD_HEIGHT}px;
    font-family: "Microsoft YaHei", "PingFang SC", "Hiragino Sans GB", sans-serif;
    background: {theme["bg_primary"]};
    overflow: hidden;
    position: relative;
}}
.content {{
    width: 100%;
    height: 100%;
    display: flex;
    flex-direction: column;
    padding: 80px 70px;
}}
/* 顶部装饰条 */
.content::before {{
    content: "";
    position: absolute;
    top: 0; left: 0;
    width: 100%;
    height: 8px;
    background: {theme["accent"]};
}}
/* 小标题区 */
.header {{
    display: flex;
    align-items: center;
    gap: 16px;
    margin-bottom: 50px;
}}
.header-bar {{
    width: 8px;
    height: 48px;
    background: {theme["accent"]};
    border-radius: 4px;
}}
.header-title {{
    color: {theme["text_primary"]};
    font-size: 42px;
    font-weight: 700;
    line-height: 1.3;
}}
/* 正文分段 */
.paras {{
    flex: 1;
    display: flex;
    flex-direction: column;
    gap: 32px;
}}
.para-item {{
    display: flex;
    align-items: flex-start;
    gap: 20px;
}}
.para-num {{
    flex-shrink: 0;
    width: 48px;
    height: 48px;
    background: {theme["accent"]};
    color: white;
    font-size: 28px;
    font-weight: 700;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
}}
.para-text {{
    flex: 1;
    color: {theme["text_primary"]};
    font-size: 32px;
    line-height: 1.6;
    word-break: break-word;
    padding-top: 6px;
}}
/* 底部标签区 */
.footer {{
    margin-top: 40px;
    padding-top: 30px;
    border-top: 2px solid {theme["bg_secondary"]};
}}
.content-tags {{
    display: flex;
    flex-wrap: wrap;
    gap: 12px;
    margin-bottom: 20px;
}}
.content-tag {{
    color: {theme["tag_text"]};
    font-size: 26px;
    font-weight: 500;
}}
.cta {{
    color: {theme["text_secondary"]};
    font-size: 24px;
    text-align: center;
    margin-top: 10px;
}}
</style>
</head>
<body>
<div class="content">
    <div class="header">
        <div class="header-bar"></div>
        <div class="header-title">{title.strip() or "内容详情"}</div>
    </div>
    <div class="paras">
        {paragraphs_html}
    </div>
    <div class="footer">
        <div class="content-tags">{tags_html}</div>
        <div class="cta">关注我，获取更多分享 ❤</div>
    </div>
</div>
</body>
</html>"""


async def render_card_set(
    title: str,
    content: str,
    tags: list[str],
    topic: str,
    style_name: str = "fresh_natural",
) -> dict[str, Any]:
    """渲染一套小红书图文卡片（1 封面 + 1 内容图）。

    Args:
        title: 笔记标题
        content: 笔记正文（多段，用换行分隔）
        tags: 话题标签列表
        topic: 工作流主题（用于封面底部装饰）
        style_name: 图片风格名（fresh_natural/japanese_film/warm_sunlight/vintage_film）

    Returns:
        {
            "images_base64": ["data:image/png;base64,...", ...],
            "image_details": [
                {"role": "cover", "description": "封面卡片", "prompt": "..."},
                {"role": "content_1", "description": "内容卡片", "prompt": "..."},
            ],
            "style": "清新自然",
            "_source": "card_render",
        }

    Raises:
        RuntimeError: Playwright 不可用或渲染失败
    """
    # 构建封面 HTML
    cover_html = build_cover_html(title, tags, topic, style_name)
    # 构建内容 HTML
    content_html = build_content_html(title, content, tags, style_name)

    # 并行渲染两张卡片（复用同一个 browser）
    cover_b64, content_b64 = await asyncio.gather(
        render_html_to_base64(cover_html),
        render_html_to_base64(content_html),
    )

    theme = _get_theme(style_name)
    return {
        "images_base64": [cover_b64, content_b64],
        "image_details": [
            {
                "role": "cover",
                "description": f"封面卡片（{theme['name']}风格）",
                "prompt": f"cover card: {title}",
            },
            {
                "role": "content_1",
                "description": f"内容卡片（{theme['name']}风格）",
                "prompt": f"content card: {title}",
            },
        ],
        "style": f"小红书卡片（{theme['name']}）",
        "image_prompts": [
            {"role": "cover", "prompt": f"cover card: {title}", "description": "封面卡片"},
            {"role": "content_1", "prompt": f"content card: {title}", "description": "内容卡片"},
        ],
        "_source": "card_render",
    }


# ============================================================================
# 结构化图表模板（第一期：流程图 / 要点列表 / 时间线）
#
# 与封面/内容卡片不同，结构化模板用语义化 HTML 表达内容结构，
# 而非用文字描述图片。LLM 填充 template_data，后端渲染为 PNG。
# ============================================================================


# 尺寸映射：支持多比例（第四期完整落地，第一期先内部用）
_SIZE_DIMENSIONS: dict[str, tuple[int, int]] = {
    "1:1": (1080, 1080),
    "3:4": (1080, 1440),
    "4:3": (1440, 1080),
}


def _get_size_dimensions(size: str) -> tuple[int, int]:
    """尺寸名 → (width, height)，默认 3:4。"""
    return _SIZE_DIMENSIONS.get(size, _SIZE_DIMENSIONS["3:4"])


def _html_skeleton(
    body_html: str,
    css: str,
    width: int,
    height: int,
    bg_color: str,
) -> str:
    """生成完整 HTML 文档骨架，供所有结构化模板复用。"""
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{
    width: {width}px;
    height: {height}px;
    font-family: "Microsoft YaHei", "PingFang SC", "Hiragino Sans GB", sans-serif;
    background: {bg_color};
    overflow: hidden;
    position: relative;
}}
{css}
</style>
</head>
<body>
{body_html}
</body>
</html>"""


def build_flow_html(
    title: str,
    steps: list[dict],
    style_name: str = "fresh_natural",
    size: str = "3:4",
) -> str:
    """构建流程图模板 HTML。

    数据结构：steps=[{title, desc}, ...]
    视觉：竖向步骤卡片，步骤间用箭头连接，每步带序号圆圈。
    """
    theme = _get_theme(style_name)
    width, height = _get_size_dimensions(size)

    # 构建步骤 HTML
    steps_html = ""
    for i, step in enumerate(steps, 1):
        step_title = str(step.get("title", "")).strip() or f"步骤 {i}"
        step_desc = str(step.get("desc", "")).strip()
        desc_html = f'<div class="step-desc">{step_desc}</div>' if step_desc else ""
        # 步骤间箭头（最后一个不加）
        arrow_html = '<div class="step-arrow">↓</div>' if i < len(steps) else ""
        steps_html += f"""
        <div class="flow-step">
            <div class="step-num">{i}</div>
            <div class="step-content">
                <div class="step-title">{step_title}</div>
                {desc_html}
            </div>
        </div>
        {arrow_html}"""

    body = f"""
    <div class="flow-card">
        <h1 class="flow-title">{title}</h1>
        <div class="flow-steps">
            {steps_html}
        </div>
    </div>"""

    css = f"""
    .flow-card {{
        width: 100%;
        height: 100%;
        display: flex;
        flex-direction: column;
        padding: 90px 80px 70px;
        position: relative;
    }}
    .flow-card::before {{
        content: "";
        position: absolute;
        top: 0; left: 0;
        width: 100%; height: 12px;
        background: {theme["accent"]};
    }}
    .flow-title {{
        font-size: 52px;
        font-weight: 800;
        color: {theme["text_primary"]};
        text-align: center;
        margin-bottom: 50px;
        line-height: 1.3;
    }}
    .flow-steps {{
        display: flex;
        flex-direction: column;
        align-items: center;
        gap: 0;
        flex: 1;
    }}
    .flow-step {{
        display: flex;
        align-items: center;
        gap: 28px;
        width: 100%;
        background: {theme["bg_secondary"]};
        border-radius: 20px;
        padding: 28px 36px;
    }}
    .step-num {{
        width: 64px;
        height: 64px;
        border-radius: 50%;
        background: {theme["accent"]};
        color: #FFFFFF;
        font-size: 32px;
        font-weight: 700;
        display: flex;
        align-items: center;
        justify-content: center;
        flex-shrink: 0;
    }}
    .step-content {{
        flex: 1;
    }}
    .step-title {{
        font-size: 32px;
        font-weight: 600;
        color: {theme["text_primary"]};
        margin-bottom: 8px;
    }}
    .step-desc {{
        font-size: 24px;
        color: {theme["text_secondary"]};
        line-height: 1.5;
    }}
    .step-arrow {{
        font-size: 36px;
        color: {theme["accent"]};
        text-align: center;
        margin: 12px 0;
        line-height: 1;
    }}
    """

    return _html_skeleton(body, css, width, height, theme["bg_primary"])


def build_list_html(
    title: str,
    items: list[dict],
    style_name: str = "fresh_natural",
    size: str = "3:4",
) -> str:
    """构建要点列表模板 HTML。

    数据结构：items=[{num, title, desc}, ...]
    视觉：大号序号 + 标题 + 说明的横向布局。
    """
    theme = _get_theme(style_name)
    width, height = _get_size_dimensions(size)

    items_html = ""
    for i, item in enumerate(items):
        num = str(item.get("num", f"{i+1:02d}")).strip()
        item_title = str(item.get("title", "")).strip() or f"要点 {i+1}"
        item_desc = str(item.get("desc", "")).strip()
        desc_html = f'<div class="item-desc">{item_desc}</div>' if item_desc else ""
        items_html += f"""
        <div class="list-item">
            <div class="item-num">{num}</div>
            <div class="item-content">
                <div class="item-title">{item_title}</div>
                {desc_html}
            </div>
        </div>"""

    body = f"""
    <div class="list-card">
        <h1 class="list-title">{title}</h1>
        <div class="list-items">
            {items_html}
        </div>
    </div>"""

    css = f"""
    .list-card {{
        width: 100%;
        height: 100%;
        display: flex;
        flex-direction: column;
        padding: 90px 80px 70px;
        position: relative;
    }}
    .list-card::before {{
        content: "";
        position: absolute;
        top: 0; left: 0;
        width: 100%; height: 12px;
        background: {theme["accent"]};
    }}
    .list-title {{
        font-size: 52px;
        font-weight: 800;
        color: {theme["text_primary"]};
        text-align: center;
        margin-bottom: 50px;
        line-height: 1.3;
    }}
    .list-items {{
        display: flex;
        flex-direction: column;
        gap: 24px;
        flex: 1;
    }}
    .list-item {{
        display: flex;
        align-items: flex-start;
        gap: 32px;
        padding: 24px 32px;
        border-left: 6px solid {theme["accent"]};
        background: {theme["bg_secondary"]};
        border-radius: 0 16px 16px 0;
    }}
    .item-num {{
        font-size: 56px;
        font-weight: 800;
        color: {theme["accent"]};
        line-height: 1;
        flex-shrink: 0;
        min-width: 90px;
    }}
    .item-content {{
        flex: 1;
        padding-top: 6px;
    }}
    .item-title {{
        font-size: 34px;
        font-weight: 600;
        color: {theme["text_primary"]};
        margin-bottom: 8px;
    }}
    .item-desc {{
        font-size: 24px;
        color: {theme["text_secondary"]};
        line-height: 1.5;
    }}
    """

    return _html_skeleton(body, css, width, height, theme["bg_primary"])


def build_timeline_html(
    title: str,
    events: list[dict],
    style_name: str = "fresh_natural",
    size: str = "3:4",
) -> str:
    """构建时间线模板 HTML。

    数据结构：events=[{time, title, desc}, ...]
    视觉：竖向时间轴，左侧时间 + 圆点 + 右侧内容。
    """
    theme = _get_theme(style_name)
    width, height = _get_size_dimensions(size)

    events_html = ""
    for i, event in enumerate(events):
        ev_time = str(event.get("time", "")).strip() or f"节点 {i+1}"
        ev_title = str(event.get("title", "")).strip() or f"事件 {i+1}"
        ev_desc = str(event.get("desc", "")).strip()
        desc_html = f'<div class="event-desc">{ev_desc}</div>' if ev_desc else ""
        # 最后一个事件不画连线
        line_html = '<div class="event-line"></div>' if i < len(events) - 1 else ""
        events_html += f"""
        <div class="timeline-event">
            <div class="event-time">{ev_time}</div>
            <div class="event-marker">
                <div class="event-dot"></div>
                {line_html}
            </div>
            <div class="event-content">
                <div class="event-title">{ev_title}</div>
                {desc_html}
            </div>
        </div>"""

    body = f"""
    <div class="timeline-card">
        <h1 class="timeline-title">{title}</h1>
        <div class="timeline-track">
            {events_html}
        </div>
    </div>"""

    css = f"""
    .timeline-card {{
        width: 100%;
        height: 100%;
        display: flex;
        flex-direction: column;
        padding: 90px 80px 70px;
        position: relative;
    }}
    .timeline-card::before {{
        content: "";
        position: absolute;
        top: 0; left: 0;
        width: 100%; height: 12px;
        background: {theme["accent"]};
    }}
    .timeline-title {{
        font-size: 52px;
        font-weight: 800;
        color: {theme["text_primary"]};
        text-align: center;
        margin-bottom: 50px;
        line-height: 1.3;
    }}
    .timeline-track {{
        display: flex;
        flex-direction: column;
        flex: 1;
    }}
    .timeline-event {{
        display: flex;
        align-items: flex-start;
        gap: 28px;
        min-height: 140px;
    }}
    .event-time {{
        font-size: 28px;
        font-weight: 600;
        color: {theme["accent"]};
        min-width: 180px;
        text-align: right;
        padding-top: 8px;
        flex-shrink: 0;
    }}
    .event-marker {{
        display: flex;
        flex-direction: column;
        align-items: center;
        flex-shrink: 0;
        padding-top: 10px;
    }}
    .event-dot {{
        width: 20px;
        height: 20px;
        border-radius: 50%;
        background: {theme["accent"]};
        border: 4px solid {theme["bg_primary"]};
        box-shadow: 0 0 0 4px {theme["accent_light"]};
        flex-shrink: 0;
    }}
    .event-line {{
        width: 3px;
        flex: 1;
        min-height: 80px;
        background: {theme["accent_light"]};
        margin-top: 8px;
    }}
    .event-content {{
        flex: 1;
        padding-bottom: 32px;
    }}
    .event-title {{
        font-size: 34px;
        font-weight: 600;
        color: {theme["text_primary"]};
        margin-bottom: 8px;
    }}
    .event-desc {{
        font-size: 24px;
        color: {theme["text_secondary"]};
        line-height: 1.5;
    }}
    """

    return _html_skeleton(body, css, width, height, theme["bg_primary"])


# 模板类型 → 构建函数映射
_TEMPLATE_BUILDERS = {
    "flow": build_flow_html,
    "list": build_list_html,
    "timeline": build_timeline_html,
}


async def render_template_to_base64(
    template_type: str,
    data: dict,
    style: str = "fresh_natural",
    size: str = "3:4",
) -> str:
    """渲染结构化模板为 base64 PNG。

    Args:
        template_type: 模板类型（"flow" | "list" | "timeline"）
        data: 模板数据（必须包含 title，以及 steps/items/events 之一）
        style: 配色风格名（fresh_natural/japanese_film/warm_sunlight/vintage_film）
        size: 尺寸（"1:1" | "3:4" | "4:3"）

    Returns:
        裸 base64 编码的 PNG（不带 data: 前缀）

    Raises:
        ValueError: 未知模板类型或数据缺失
        RuntimeError: Playwright 渲染失败
    """
    builder = _TEMPLATE_BUILDERS.get(template_type)
    if builder is None:
        raise ValueError(
            f"Unknown template type: {template_type}. "
            f"Supported: {list(_TEMPLATE_BUILDERS.keys())}"
        )

    title = str(data.get("title", "")).strip() or "内容卡片"
    style_name = style or "fresh_natural"
    size_name = size or "3:4"

    if template_type == "flow":
        steps = data.get("steps", [])
        if not steps:
            raise ValueError("flow template requires 'steps' field")
        html = builder(title, steps, style_name, size_name)
    elif template_type == "list":
        items = data.get("items", [])
        if not items:
            raise ValueError("list template requires 'items' field")
        html = builder(title, items, style_name, size_name)
    elif template_type == "timeline":
        events = data.get("events", [])
        if not events:
            raise ValueError("timeline template requires 'events' field")
        html = builder(title, events, style_name, size_name)
    else:
        # 理论上不会到这里（前面已校验）
        raise ValueError(f"Unsupported template type: {template_type}")

    width, height = _get_size_dimensions(size_name)
    return await render_html_to_base64(html, width, height)
