"""One trusted HTML compiler for card preview and future Chromium export."""

from __future__ import annotations

from html import escape

from app.cards.audit import audit_page
from app.cards.schema import (
    THEMES, VARIANT_OPTIONS, BentoGrid, CardDeck, CardPage, Code, Compare, Cta, Footer, Heading,
    IconGrid, ImageBlock, Kicker, ListBlock, Qa, Quote, Stat, Steps, Text, Timeline,
    _accessible_accents, available_directions, compatible_layouts, theme_accent_class, theme_css,
)


# 布局基线（Easel layout-laws 的本地化）：
# footer 绝对定位钉在底部，内容区用 space-between 均匀铺开。
# 绝不用 margin-top:auto —— 它把所有空隙挤到中段，制造 50-75% 那一带的死空白。
CSS = """
*{box-sizing:border-box}html,body{margin:0;width:1080px;height:1440px;overflow:hidden}
body{font-family:var(--font,'Noto Sans SC','Microsoft YaHei',sans-serif)}
.card{position:relative;width:1080px;height:1440px;overflow:hidden;
padding:88px 82px 190px;display:flex;flex-direction:column}
.content{flex:1;display:flex;flex-direction:column;justify-content:flex-start;min-height:0}
""" + theme_css() + """
.kicker{font-family:var(--kicker-font,monospace);font-size:25px;letter-spacing:.2em;
text-transform:uppercase;color:var(--accent);margin-bottom:46px}
h1{font-size:91px;font-weight:var(--display-weight,400);line-height:1.17;letter-spacing:-.02em;margin:0;overflow-wrap:anywhere}
.body h1{font-size:66px;line-height:1.22;margin-bottom:48px}
.deck-title{position:absolute;left:82px;right:210px;bottom:76px;font-size:25px;letter-spacing:.08em;
color:var(--muted);padding-top:18px;border-top:2px solid var(--line)}
.page-no{position:absolute;right:82px;bottom:76px;font-size:24px;color:var(--muted)}
.text{white-space:pre-wrap;overflow-wrap:anywhere;line-height:1.7;font-size:34px;margin:10px 0;color:var(--muted)}
.cover_display h1{margin-top:110px;max-width:880px;font-size:116px}
.preview-label{font-family:var(--kicker-font,monospace);font-size:22px;letter-spacing:.18em;
color:var(--muted);margin-top:auto;padding-bottom:16px}
.preview{list-style:none;padding:0;margin:0;border-top:2px solid var(--line)}
/* 封面导读同样要吃掉剩余空间：flex:none 会让副标题与导读之间裂开一条死带。 */
.preview{flex:1;display:flex;flex-direction:column;justify-content:space-around;min-height:0}
.preview li{padding:18px 0;border-bottom:1px solid var(--line);font-size:30px;
line-height:1.4;color:var(--text);overflow-wrap:anywhere}
.cover_display .text{font-size:39px;margin-top:58px}
.cover_top_image{padding-top:54px}.cover_top_image img{width:100%;height:680px;object-fit:cover;margin-bottom:56px}
.cover_top_image h1{font-size:78px}.cover_top_image .text{font-size:32px}
.rows{list-style:none;padding:0;margin:20px 0 0;border-top:2px solid var(--text);
flex:1;display:flex;flex-direction:column;justify-content:space-around}
/* flex:1 1 auto —— 条目少时按剩余空间长高（这才是「填满」），
   条目多到撑满时退化为内容高度，与 flex:none 相比不会更差。 */
.rows li{display:flex;align-items:center;gap:16px;flex:1 1 auto;min-height:123px;padding:23px 10px;border-bottom:1px solid var(--line);overflow-wrap:anywhere}
.rows .number{color:var(--accent);font-size:25px;width:80px;flex:none}
.rows .line{flex:1;min-width:0}
.rows .main{font-size:36px;line-height:1.25}
/* 副行用 muted 小字：既不抢主行，又实打实多吃了一行高度。 */
.rows .note{font-size:24px;line-height:1.4;color:var(--muted);margin-top:10px}
/* 右侧标签走 kicker 那套等宽大写 + 字距，是清单里最出设计感的元素。 */
.rows .tag{flex:none;font-family:var(--kicker-font);font-size:22px;letter-spacing:.12em;
text-transform:uppercase;color:var(--accent);border:1px solid var(--line);
border-radius:var(--radius,0);padding:8px 14px}
.steps_flow .rows li{min-height:155px}.steps_flow .rows .number{font-size:48px}
/* grid-auto-rows:1fr 让每一行按剩余空间等分——对比表同样要填满，而不是缩在顶部。 */
.compare{display:grid;grid-template-columns:1fr 1fr;grid-auto-rows:1fr;gap:20px;margin-top:20px;flex:1;min-height:0}
.compare.labeled{grid-template-columns:auto 1fr 1fr}
.compare .head{background:var(--surface);padding:22px 28px;font-size:34px;font-weight:500;
color:var(--accent);border-radius:var(--radius,0);display:flex;align-items:center;min-width:0}
.compare .cell{background:var(--surface);padding:20px 28px;font-size:30px;line-height:1.35;
border-radius:var(--radius,0);display:flex;align-items:center;overflow-wrap:anywhere;min-width:0}
/* 行标签回答"这一行在比什么"：等宽小字 + 字距，是对比表最出设计感的地方。 */
.compare .rowlabel{font-family:var(--kicker-font);font-size:22px;letter-spacing:.12em;
text-transform:uppercase;color:var(--muted);display:flex;align-items:center;padding-right:18px}
.image_right_ledger .split{display:grid;grid-template-columns:53% 43%;gap:4%;min-height:750px}
.image_right_ledger .rows .main{font-size:30px}.image_right_ledger .rows li{min-height:136px}
.image_right_ledger .rows .number{width:55px}
.image_right_ledger img{width:100%;height:850px;object-fit:cover;border-radius:var(--radius,0)}
/* 图片蒙层：颜色全部来自主题的 --on-image-* 反色 token（见 schema.theme_css）。
   之前这里写死 #23323c + 白字，导致切任何主题蒙层页都是同一套青灰底白字。
   注意不能用 --bg / --text 推导：浅色主题的深字压在照片上会读不清。 */
.image_bg_overlay{padding:0;background:var(--on-image-bg,#23323c);color:var(--on-image-text,#fff)}
.image_bg_overlay img{position:absolute;inset:0;width:100%;height:100%;object-fit:cover}
.image_bg_overlay .shade{position:absolute;inset:0;background:var(--on-image-shade,linear-gradient(180deg,rgba(0,0,0,.08),rgba(0,0,0,.76)))}
.image_bg_overlay .overlay{position:relative;margin-top:auto;padding:100px 82px 125px}
.image_bg_overlay h1{font-size:102px}
.image_bg_overlay .text{color:var(--on-image-text,#fff);opacity:.92}
.image_bg_overlay .page-no{color:var(--on-image-text,#fff)}.image_bg_overlay .deck-title{display:none}
.end_cta .cta{background:var(--text);color:var(--bg);padding:62px;font-size:50px;line-height:1.35;border-radius:var(--radius,0)}
/* 矩阵 bento：3 列自适应网格，每格独立承载「kicker + big + unit + note + source」五层。
   grid-auto-rows:1fr 让格子按剩余空间均分——少格时填满、多格时不溢出。 */
/* 矩阵 bento：3 列自适应网格，每格独立承载「kicker + big + unit + note + source」五层。
   flex:1 + align-content:end 把 grid 撑到 content 底部，避免 grid 下方留死空；
   cell 内 ::before 发丝线在 big 与 note 之间作为视觉锚，避免被拉高后中段空洞。 */
.bento{display:grid;grid-template-columns:repeat(3,1fr);grid-auto-rows:1fr;
gap:18px;flex:1;min-height:0;margin-top:24px;align-content:end}
.bento .cell{background:var(--surface);padding:32px 28px;border-radius:var(--radius,0);
display:flex;flex-direction:column;justify-content:flex-start;min-width:0;
overflow-wrap:anywhere}
.bento .kicker{font-family:var(--kicker-font);font-size:20px;letter-spacing:.18em;
text-transform:uppercase;color:var(--accent);margin-bottom:18px}
.bento .big{font-size:96px;font-weight:var(--display-weight,500);line-height:1.05;
letter-spacing:-.03em;color:var(--text)}
.bento .unit{font-size:32px;color:var(--muted);margin-top:8px}
.bento .note{font-size:28px;line-height:1.5;color:var(--text);
margin-top:auto;padding-top:24px;position:relative}
.bento .note::before{content:"";position:absolute;left:0;top:0;width:36px;height:2px;
background:var(--line)}
.bento .source{font-family:var(--kicker-font);font-size:16px;letter-spacing:.14em;
text-transform:uppercase;color:var(--muted);margin-top:14px;opacity:.72}
/* 单数据卡 stat：呼吸型骨架（layout-laws 允许 ≤60% 覆盖）。
   flex:1 + justify-content:space-between 让 kicker 贴顶、巨数居中、note+source 贴底，
   内部空间被三组明确占据，下方空白变成"被刻意安排的留白"而非空洞。 */
.stat{display:flex;flex-direction:column;justify-content:space-between;
flex:1;min-height:0;margin-top:24px;padding:48px 0 24px;border-top:2px solid var(--line)}
.stat .kicker{font-family:var(--kicker-font);font-size:30px;letter-spacing:.2em;
text-transform:uppercase;color:var(--accent);margin:0}
/* 巨数 + 单位同行：让数据视觉重量集中在一行。 */
.stat .big-line{display:flex;align-items:flex-end;margin:36px 0 0}
.stat .big{font-size:340px;font-weight:var(--display-weight,500);line-height:.92;
letter-spacing:-.05em;color:var(--text)}
.stat .unit{font-size:84px;color:var(--muted);margin-left:28px;
line-height:1;padding-bottom:40px}
/* note 与 source 紧跟 big-line，space-between 把 3 段推到顶/中/底均匀铺开。 */
.stat .note{font-size:40px;line-height:1.55;color:var(--text);
max-width:88%;font-weight:400}
.stat .source{font-family:var(--kicker-font);font-size:22px;letter-spacing:.14em;
text-transform:uppercase;color:var(--muted);margin-top:36px;opacity:.8}
/* 时间线 timeline：左侧 mono 时间戳 + 右侧标题/说明，上下发丝线分隔。
   与 steps_flow 的差别是「按时间排序」而非「按流程顺序」——视觉上更强调
   日期/时间戳的纵向排列，而不是序号。 */
.timeline{list-style:none;padding:0;margin:20px 0 0;border-top:2px solid var(--text);
flex:1;display:flex;flex-direction:column;justify-content:space-around;min-height:0}
.timeline li{display:flex;align-items:flex-start;gap:28px;flex:1 1 auto;
min-height:120px;padding:28px 10px;border-bottom:1px solid var(--line);overflow-wrap:anywhere}
.timeline .date{font-family:var(--kicker-font);font-size:24px;letter-spacing:.08em;
color:var(--accent);width:140px;flex:none;padding-top:4px}
.timeline .line{flex:1;min-width:0}
.timeline .main{font-size:36px;line-height:1.25}
.timeline .note{font-size:24px;line-height:1.4;color:var(--muted);margin-top:10px}
/* 金句 quote：呼吸型骨架（允许 ≤60% 覆盖）。
   三锚点：顶 kicker + 底 author + 上下发丝线。
   正文 64px 斜体/大字撑出视觉重量；space-between 把三段推到顶/中/底。 */
.quote{display:flex;flex-direction:column;justify-content:space-between;
flex:1;min-height:0;margin-top:24px;padding:40px 0;border-top:2px solid var(--line);
border-bottom:2px solid var(--line)}
.quote .kicker{font-family:var(--kicker-font);font-size:24px;letter-spacing:.2em;
text-transform:uppercase;color:var(--accent);margin:0}
.quote .text{font-size:92px;font-style:italic;line-height:1.32;color:var(--text);
max-width:92%;margin:36px 0;overflow-wrap:anywhere}
.quote .author{font-family:var(--kicker-font);font-size:24px;letter-spacing:.14em;
text-transform:uppercase;color:var(--muted);margin:0;opacity:.8}
/* ---- 补齐的 5 个 Block（spec 规划 15 个，首批只落地 11 个）---- */
/* kicker 块：单页栏目名，区别于贴顶的 deck 级分类标签。 */
.blk-kicker{font-family:var(--kicker-font);font-size:26px;letter-spacing:.2em;
text-transform:uppercase;color:var(--accent);margin-bottom:30px}
/* qa：问答对，Q/A 用等宽字母做前缀锚，一问一答天然吃两行高度。 */
.qa{list-style:none;padding:0;margin:24px 0 0;border-top:2px solid var(--line);
flex:1;display:flex;flex-direction:column;justify-content:space-around;min-height:0}
.qa li{padding:24px 0;border-bottom:1px solid var(--line);overflow-wrap:anywhere}
.qa .q{display:flex;gap:16px;font-size:34px;line-height:1.3;color:var(--text)}
.qa .q::before{content:"Q";font-family:var(--kicker-font);font-size:24px;
color:var(--accent);flex:none;padding-top:6px}
.qa .a{display:flex;gap:16px;font-size:26px;line-height:1.55;color:var(--muted);margin-top:14px}
.qa .a::before{content:"A";font-family:var(--kicker-font);font-size:24px;
color:var(--muted);flex:none;padding-top:3px}
/* code：等宽面板，lang 只作右上角标注，不做语法高亮（避免引依赖）。 */
.code{position:relative;background:var(--surface);border-radius:var(--radius,0);
padding:30px 34px;margin-top:26px;border-left:4px solid var(--accent)}
.code .lang{position:absolute;right:26px;top:20px;font-family:var(--kicker-font);
font-size:18px;letter-spacing:.14em;text-transform:uppercase;color:var(--muted);opacity:.8}
.code pre{margin:0;font-family:'JetBrains Mono','Noto Sans Mono CJK SC',monospace;
font-size:25px;line-height:1.62;color:var(--text);white-space:pre-wrap;overflow-wrap:anywhere}
/* icon_grid：图标 + 短文本两列网格，比账本轻、比矩阵省字。 */
.icons{display:grid;grid-template-columns:repeat(2,1fr);gap:22px;margin-top:26px;
flex:1;align-content:start;min-height:0}
.icons .pair{display:flex;align-items:center;gap:20px;background:var(--surface);
padding:28px 30px;border-radius:var(--radius,0);min-width:0}
.icons .ico{flex:none;width:42px;height:42px;color:var(--accent);stroke:currentColor;
fill:none;stroke-width:1.5;stroke-linecap:round;stroke-linejoin:round}
.icons .txt{font-size:31px;line-height:1.3;color:var(--text);overflow-wrap:anywhere}
/* footer 块：该页专属来源/注释，钉在内容区底部（区别于绝对定位的 deck 页脚）。 */
.blk-footer{font-size:24px;line-height:1.5;color:var(--muted);margin-top:auto;
padding-top:22px;border-top:1px solid var(--line)}
/* ===== 组件视觉变体（schema.VARIANT_OPTIONS）=====
   只改变同一骨架下的视觉语气，不碰几何版式。class 仅在该组件 variant 非空时追加，
   所以经典渲染（variant=""）完全不受影响。 */
/* list: cards —— 每条要点做成卡片 */
.rows.variant-cards{border-top:none}
.rows.variant-cards li{background:var(--surface);border:1px solid var(--line);
border-radius:var(--radius,0);border-bottom:none;margin-bottom:16px;flex:none;padding:24px 28px}
.rows.variant-cards .tag{margin-left:auto}
/* list: tags —— 紧凑药丸（特性/标签速览） */
.rows.variant-tags{display:flex;flex-wrap:wrap;gap:16px;border-top:none}
.rows.variant-tags li{background:var(--surface);border:1px solid var(--line);
border-radius:999px;padding:14px 26px;flex:none;min-height:auto;
display:inline-flex;align-items:center;gap:14px}
.rows.variant-tags .number{display:none}
.rows.variant-tags .note{margin-top:0}
/* steps: chips —— 编号做成圆形徽标，步骤卡片化 */
.rows.variant-chips{display:flex;flex-wrap:wrap;align-items:stretch;gap:16px;border-top:none}
.rows.variant-chips li{flex:1 1 240px;min-height:auto;flex-direction:column;align-items:flex-start;
background:var(--surface);border:1px solid var(--line);border-radius:var(--radius,0);
padding:26px;flex:none}
.rows.variant-chips .number{border-radius:50%;background:var(--accent);color:var(--bg);
width:56px;height:56px;display:flex;align-items:center;justify-content:center}
/* steps: minimal —— 去掉分隔线，编号弱化 */
.rows.variant-minimal li{border-bottom:none;padding:14px 6px;min-height:auto}
.rows.variant-minimal .number{color:var(--muted)}
/* compare: table —— 连成整表，去掉间隙 */
.compare.variant-table{gap:0}
.compare.variant-table .cell,.compare.variant-table .head,.compare.variant-table .rowlabel{
border:1px solid var(--line);border-radius:0}
.compare.variant-table .cell{border-left:none}
.compare.variant-table .rowlabel{border-right:none}
/* bento: masonry —— 首格放大占两行两列 */
.bento.variant-masonry .cell:first-child{grid-column:span 2;grid-row:span 2}
/* bento: row —— 单行自适应排布 */
.bento.variant-row{grid-template-columns:repeat(auto-fit,minmax(0,1fr));
grid-auto-rows:minmax(170px,auto);align-content:stretch}
/* stat: ring —— 巨数套圆环 */
.stat.variant-ring .big-line{justify-content:center}
.stat.variant-ring .big{border:6px solid var(--accent);border-radius:50%;display:inline-flex;
align-items:center;justify-content:center;padding:36px 56px;margin:0 auto}
.stat.variant-ring .unit{padding-bottom:0;margin-left:0;margin-top:18px}
/* stat: underline —— 巨数下划强调线 */
.stat.variant-underline .big-line{justify-content:flex-start}
.stat.variant-underline .big{display:inline-block;border-bottom:6px solid var(--accent);padding-bottom:18px}
/* timeline: dots —— 圆点锚 + 左侧竖轨 */
.timeline.variant-dots li{position:relative;border-bottom:none;padding:22px 0 22px 44px}
.timeline.variant-dots li::before{content:"";position:absolute;left:12px;top:30px;width:16px;height:16px;
border-radius:50%;background:var(--accent);border:3px solid var(--bg);z-index:1}
.timeline.variant-dots li::after{content:"";position:absolute;left:19px;top:46px;bottom:-4px;width:2px;background:var(--line)}
/* timeline: slim —— 更轻的间距 */
.timeline.variant-slim li{border-bottom:none;min-height:auto;padding:16px 8px}
.timeline.variant-slim .date{color:var(--muted)}
"""


def _text(text: str) -> str:
    return escape(text, quote=True)


def _list(items, numbered: bool = True, variant: str = "") -> str:
    """账本行：主行 + 副行 + 右侧标签。

    副行不是装饰——它让一条要点能装下"是什么 + 为什么"，
    同样填满画幅所需的主行数从 6 条降到 4 条。
    `variant` 非空时给 <ol> 追加 `variant-<v>` class，由 CSS 切换视觉语气。
    """
    cells = []
    for position, item in enumerate(items, 1):
        note = f'<div class="note">{_text(item.note)}</div>' if item.note else ""
        tag = f'<div class="tag">{_text(item.tag)}</div>' if item.tag else ""
        cells.append(
            '<li><span class="number">' + (f"{position:02}" if numbered else "—") + '</span>'
            '<div class="line"><div class="main">' + _text(item.text) + "</div>" + note + "</div>"
            + tag + "</li>"
        )
    cls = "rows" + (f" variant-{variant}" if variant else "")
    return f'<ol class="{cls}">' + "".join(cells) + "</ol>"


def _img(block: ImageBlock) -> str:
    # resolved_url is restricted by ImageBlock's schema to our upload namespace.
    return f'<img src="{_text(block.resolved_url)}" alt="{_text(block.alt)}">'


def _cell(cell, kind: str) -> str:
    """bento 与 stat 共享的渲染：kicker / big / unit / note / source 五层。

    `kind == "bento"` 时把 note 用 margin-top:auto 顶到格子底部，让格子在不同
    行高下都视觉对齐；`kind == "stat"` 时用 space-between 把整组内容顶到底部，
    大字与脚注之间留出 3 倍字距的呼吸位。
    """
    layers = []
    if cell.kicker:
        layers.append(f'<div class="kicker">{_text(cell.kicker)}</div>')
    big_html = f'<div class="big">{_text(cell.big)}</div>' if cell.big else ""
    unit_html = f'<span class="unit">{_text(cell.unit)}</span>' if cell.unit else ""
    if big_html and unit_html:
        # big + unit 同行：让 stat 单卡的数据视觉重量集中在一行。
        layers.append(f'<div class="big-line">{big_html}{unit_html}</div>')
    elif big_html:
        layers.append(big_html)
    elif unit_html:
        layers.append(f'<div class="big-line">{unit_html}</div>')
    if cell.note:
        layers.append(f'<div class="note">{_text(cell.note)}</div>')
    if cell.source:
        layers.append(f'<div class="source">{_text(cell.source)}</div>')
    if kind == "bento":
        return f'<div class="cell">' + "".join(layers) + "</div>"
    return "".join(layers)


# lucide 线性图标的一小撮内置路径（24×24 viewBox，stroke 1.5）。
# 出图跑在服务端的 Playwright 里，不引前端图标库——依赖越少越稳。
# 未收录的名字退回中性圆环标记，**不用 emoji**（Easel anti-ai-slop 铁律）。
_ICON_PATHS = {
    "check": '<polyline points="20 6 9 17 4 12"/>',
    "zap": '<polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/>',
    "target": '<circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r="6"/>'
              '<circle cx="12" cy="12" r="2"/>',
    "star": '<polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 '
            '5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/>',
    "clock": '<circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>',
    "shield": '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>',
    "trending-up": '<polyline points="23 6 13.5 15.5 8.5 10.5 1 18"/>'
                   '<polyline points="17 6 23 6 23 12"/>',
    "users": '<path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/>'
             '<circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/>',
    "lightbulb": '<path d="M9 18h6"/><path d="M10 22h4"/>'
                 '<path d="M15.09 14c.18-.98.65-1.74 1.41-2.5A4.65 4.65 0 0 0 18 8 '
                 '6 6 0 0 0 6 8c0 1 .23 2.23 1.5 3.5A4.61 4.61 0 0 1 8.91 14"/>',
    "heart": '<path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78'
             'l7.78 7.78 7.78-7.78a5.5 5.5 0 0 0 0-7.78z"/>',
}
_ICON_FALLBACK = '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="3.5"/>'


def _icon_svg(name: str) -> str:
    body = _ICON_PATHS.get(name.strip().lower(), _ICON_FALLBACK)
    return f'<svg class="ico" viewBox="0 0 24 24" aria-hidden="true">{body}</svg>'


def _kicker(block: Kicker) -> str:
    return f'<div class="blk-kicker">{_text(block.text)}</div>'


def _footer(block: Footer) -> str:
    return f'<div class="blk-footer">{_text(block.text)}</div>'


def _qa(block: Qa) -> str:
    rows = "".join(
        f'<li><div class="q">{_text(pair.q)}</div><div class="a">{_text(pair.a)}</div></li>'
        for pair in block.pairs
    )
    return f'<ul class="qa">{rows}</ul>'


def _code(block: Code) -> str:
    lang = ""
    if block.lang and block.lang != "text":
        lang = f'<div class="lang">{_text(block.lang)}</div>'
    return f'<div class="code">{lang}<pre>{_text(block.content)}</pre></div>'


def _icon_grid(block: IconGrid) -> str:
    pairs = "".join(
        f'<div class="pair">{_icon_svg(pair.icon)}<div class="txt">{_text(pair.text)}</div></div>'
        for pair in block.pairs
    )
    return f'<div class="icons">{pairs}</div>'


def render_page(deck: CardDeck, page: CardPage, index: int) -> str:
    by_type = {block.type: block for block in page.blocks}
    # 金句页 quote_callout 的 LAYOUTS 只含 quote、不含 heading（kicker 由块内承载），
    # 其余版式都含 heading，所以取不到时降级为空标题。
    heading = by_type.get("heading")
    title = f"<h1>{_text(heading.text)}</h1>" if isinstance(heading, Heading) else ""
    description = by_type.get("text")
    desc_html = f'<p class="text">{_text(description.text)}</p>' if isinstance(description, Text) else ""
    image = by_type.get("image")
    content = ""
    if page.layout_id == "cover_display":
        preview = by_type.get("list")
        preview_html = ""
        if isinstance(preview, ListBlock):
            preview_html = (
                '<div class="preview-label">本期导读</div>'
                + '<ul class="preview">' + "".join(
                    f"<li>{_text(item.text)}</li>" for item in preview.items
                ) + "</ul>"
            )
        content = title + desc_html + preview_html
    elif page.layout_id == "cover_top_image" and isinstance(image, ImageBlock):
        content = _img(image) + title + desc_html
    elif page.layout_id == "content_text":
        content = title + desc_html
    elif page.layout_id in ("list_ledger", "steps_flow", "image_right_ledger"):
        items_block = by_type.get("list") or by_type.get("steps")
        assert isinstance(items_block, (ListBlock, Steps))
        rows = _list(items_block.items, variant=getattr(items_block, "variant", ""))
        if page.layout_id == "image_right_ledger" and isinstance(image, ImageBlock):
            content = title + '<div class="split">' + rows + _img(image) + "</div>"
        else:
            content = title + rows
    elif page.layout_id == "compare_split":
        compare = by_type["compare"]
        assert isinstance(compare, Compare)
        # 有行标签时多出第一列：标签回答"这一行在比什么"，否则两栏就是两串孤立的值。
        labeled = any(row.label for row in compare.rows)
        heads = "".join(
            f'<div class="head">{_text(name)}</div>'
            for name in (("", compare.left_title, compare.right_title) if labeled
                         else (compare.left_title, compare.right_title)))
        body = "".join(
            (f'<div class="rowlabel">{_text(row.label)}</div>' if labeled else "")
            + f'<div class="cell">{_text(row.left)}</div><div class="cell">{_text(row.right)}</div>'
            for row in compare.rows)
        variant_cls = f" variant-{compare.variant}" if compare.variant else ""
        content = title + f'<div class="compare{" labeled" if labeled else ""}{variant_cls}">' + heads + body + '</div>'
    elif page.layout_id == "image_bg_overlay" and isinstance(image, ImageBlock):
        # 蒙层的 kicker 用 deck 自己的分类/来源，之前写死 "VISUAL STORY" 是硬编码文案。
        overlay_kicker = f'<div class="kicker">{_text(deck.kicker)}</div>' if deck.kicker else ""
        content = _img(image) + '<div class="shade"></div><div class="overlay">' + overlay_kicker + title + desc_html + '</div>'
    elif page.layout_id == "bento_grid":
        bento = by_type["bento_grid"]
        assert isinstance(bento, BentoGrid)
        # 2-6 格自适应网格；grid-auto-rows:1fr 由 CSS 保证格子铺满剩余高度。
        variant_cls = f" variant-{bento.variant}" if bento.variant else ""
        content = title + f'<div class="bento{variant_cls}">' + "".join(_cell(c, "bento") for c in bento.cells) + '</div>'
    elif page.layout_id == "stat_card":
        stat = by_type["stat"]
        assert isinstance(stat, Stat)
        variant_cls = f" variant-{stat.variant}" if stat.variant else ""
        content = title + f'<div class="stat{variant_cls}">' + _cell(stat.cell, "stat") + '</div>'
    elif page.layout_id == "timeline_flow":
        timeline = by_type["timeline"]
        assert isinstance(timeline, Timeline)
        rows = ""
        for item in timeline.items:
            note = f'<div class="note">{_text(item.note)}</div>' if item.note else ""
            rows += (
                '<li><div class="date">' + _text(item.date) + '</div>'
                + '<div class="line"><div class="main">' + _text(item.text) + "</div>" + note + "</div></li>"
            )
        variant_cls = f" variant-{timeline.variant}" if timeline.variant else ""
        content = title + f'<ul class="timeline{variant_cls}">' + rows + "</ul>"
    elif page.layout_id == "quote_callout":
        quote = by_type["quote"]
        assert isinstance(quote, Quote)
        kicker_html = f'<div class="kicker">{_text(quote.kicker)}</div>' if quote.kicker else ""
        author_html = f'<div class="author">{_text(quote.author)}</div>' if quote.author else ""
        content = (
            '<div class="quote">' + kicker_html
            + f'<div class="text">{_text(quote.text)}</div>' + author_html + "</div>"
        )
    elif page.layout_id == "end_cta":
        cta = by_type["cta"]
        assert isinstance(cta, Cta)
        # 只放一句行动号召必然撑不满画幅，所以收尾页挂一组要点回顾。
        review = by_type.get("list")
        review_html = _list(review.items, variant=getattr(review, "variant", "")) if isinstance(review, ListBlock) else ""
        content = title + desc_html + review_html + f'<div class="cta">{_text(cta.text)}</div>'
    else:
        raise ValueError(f"未实现的版式: {page.layout_id}")

    # 补齐的 5 个 Block 作为「可选挂载」统一参与排版：kicker 置顶、footer 贴底、
    # qa/code/icon_grid 接在版式主体之后。刻意不塞进上面 13 个 layout 分支里——
    # 否则每新增一个组件就要改 13 个分支，那正是旧前端 18 个 PageType 的老路。
    head_extra = _kicker(by_type["kicker"]) if isinstance(by_type.get("kicker"), Kicker) else ""
    tail_extra = _footer(by_type["footer"]) if isinstance(by_type.get("footer"), Footer) else ""
    body_extra = ""
    if isinstance(by_type.get("qa"), Qa):
        body_extra += _qa(by_type["qa"])
    if isinstance(by_type.get("code"), Code):
        body_extra += _code(by_type["code"])
    if isinstance(by_type.get("icon_grid"), IconGrid):
        body_extra += _icon_grid(by_type["icon_grid"])
    if page.layout_id in ("cover_top_image", "image_bg_overlay"):
        # 图片版式：文字不能盖到图上，可选块一律挂在图后文字区的尾部。
        content = content + head_extra + tail_extra
    else:
        content = head_extra + content + body_extra + tail_extra

    kicker = ""
    if page.layout_id not in ("cover_top_image", "image_bg_overlay"):
        # kicker 是内容语义（分类/来源），不是装饰文字；没有就只留页码。
        label = _text(deck.kicker) if deck.kicker else ""
        suffix = f" / {index + 1:02}" if label else f"{index + 1:02}"
        kicker = f'<div class="kicker">{label}{suffix}</div>'
    footer = f'<div class="deck-title">{_text(deck.title)}</div>'
    # 满版蒙层用自己的定位体系；其余版式把内容装进 .content，
    # 让剩余空间在各块之间均匀摊开，而不是全堆到顶部、中段留一片空。
    if page.layout_id == "image_bg_overlay":
        inner = kicker + content
    else:
        # kicker 固定贴顶，只让内容块在剩余空间里均匀摊开。
        inner = f'{kicker}<div class="content">{content}</div>'
    return (
        '<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=1080,initial-scale=1">'
        '<style>' + CSS + '</style></head><body>'
        f'<article class="card {deck.theme_id} {theme_accent_class(deck.theme_id, deck.accent_index)} {page.layout_id} {page.role}">'
        + inner + footer + f'<span class="page-no">{index + 1:02} / {len(deck.pages):02}</span>'
        '</article></body></html>'
    )


def to_card_draft(deck: CardDeck) -> dict:
    pages = [{
        "id": page.id,
        "type": page.role,
        "layoutId": page.layout_id,
        "availableLayouts": compatible_layouts(page),
        "title": next((block.text for block in page.blocks if isinstance(block, Heading)), ""),
        "htmlContent": render_page(deck, page, i),
    } for i, page in enumerate(deck.pages)]
    # 渲染前的密度诊断随卡片一起下发，前端可以直接提示「这一页太空」。
    for page, report in zip(pages, deck.pages):
        page["density"] = audit_page(deck, report)
    return {
        "schema_version": 1,
        "title": deck.title,
        "template": "structured_cards",
        "deck": deck.model_dump(mode="json"),
        "themeId": deck.theme_id,
        "themeOptions": [
            {
                "id": name,
                "label": spec["label"],
                "hint": spec["hint"],
                # 强调色轴：可切换的强调色板（已通过对比度校准，所见即所得）
                "accents": _accessible_accents(spec),
            }
            for name, spec in THEMES.items()
        ],
        # 当前 deck 选中的强调色索引与色板，前端据此渲染色板选择器
        "accentIndex": deck.accent_index,
        "accentOptions": _accessible_accents(THEMES[deck.theme_id]),
        "variantOptions": VARIANT_OPTIONS,
        "availableDirections": available_directions(deck),
        "pages": pages,
        "htmlUrls": [],
    }
