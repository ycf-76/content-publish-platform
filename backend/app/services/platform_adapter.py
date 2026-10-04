"""多平台内容适配器。

同一份文案，根据平台规格自动适配：
- 字数裁剪/扩写提示
- 标签格式转换
- CTA 风格适配
- 发布时间建议

借鉴 Easel post-formatter 的平台感知 + wordcount 校验，
但不做 LLM 重写（由 PromptDrivenSkill 负责）。
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PlatformSpec:
    name: str
    display_name: str
    title_max: int
    content_max: int
    content_soft_max: int
    tag_format: str
    tag_count_range: tuple[int, int]
    cta_style: str
    image_ratio: str
    image_max: int
    best_hours: list[int]


PLATFORMS: dict[str, PlatformSpec] = {
    "xiaohongshu": PlatformSpec(
        name="xiaohongshu",
        display_name="小红书",
        title_max=20,
        content_max=1000,
        content_soft_max=600,
        tag_format="#{}",
        tag_count_range=(5, 10),
        cta_style="收藏/评论引导",
        image_ratio="3:4",
        image_max=18,
        best_hours=[7, 8, 12, 13, 18, 19, 20, 21, 22],
    ),
    "douyin": PlatformSpec(
        name="douyin",
        display_name="抖音",
        title_max=15,
        content_max=300,
        content_soft_max=200,
        tag_format="#{}",
        tag_count_range=(3, 5),
        cta_style="关注/评论区引导",
        image_ratio="9:16",
        image_max=0,
        best_hours=[12, 13, 18, 19, 20, 21, 22],
    ),
    "bilibili": PlatformSpec(
        name="bilibili",
        display_name="B站",
        title_max=80,
        content_max=2000,
        content_soft_max=1500,
        tag_format="{}",
        tag_count_range=(4, 10),
        cta_style="一键三连",
        image_ratio="16:9",
        image_max=0,
        best_hours=[12, 18, 19, 20, 21, 22],
    ),
    "weibo": PlatformSpec(
        name="weibo",
        display_name="微博",
        title_max=0,
        content_max=140,
        content_soft_max=120,
        tag_format="#{}#",
        tag_count_range=(1, 3),
        cta_style="转发/评论引导",
        image_ratio="1:1",
        image_max=9,
        best_hours=[8, 9, 12, 20, 21, 22],
    ),
    "wechat": PlatformSpec(
        name="wechat",
        display_name="公众号",
        title_max=64,
        content_max=3000,
        content_soft_max=2000,
        tag_format="",
        tag_count_range=(0, 0),
        cta_style="在看/分享/关注",
        image_ratio="2.35:1",
        image_max=1,
        best_hours=[8, 12, 20, 21],
    ),
    "zhihu": PlatformSpec(
        name="zhihu",
        display_name="知乎",
        title_max=80,
        content_max=3000,
        content_soft_max=2000,
        tag_format="{}",
        tag_count_range=(3, 8),
        cta_style="赞同/收藏引导",
        image_ratio="16:9",
        image_max=0,
        best_hours=[9, 12, 20, 21],
    ),
    "kuaishou": PlatformSpec(
        name="kuaishou",
        display_name="快手",
        title_max=20,
        content_max=300,
        content_soft_max=200,
        tag_format="#{}",
        tag_count_range=(3, 5),
        cta_style="关注/评论区引导",
        image_ratio="9:16",
        image_max=0,
        best_hours=[12, 18, 19, 20, 21, 22],
    ),
    "wechat_video": PlatformSpec(
        name="wechat_video",
        display_name="视频号",
        title_max=30,
        content_max=1000,
        content_soft_max=600,
        tag_format="#{}",
        tag_count_range=(3, 5),
        cta_style="关注/评论区引导",
        image_ratio="9:16",
        image_max=9,
        best_hours=[12, 18, 19, 20, 21],
    ),
}


def get_platform_spec(platform: str) -> PlatformSpec:
    return PLATFORMS.get(platform, PLATFORMS["xiaohongshu"])


def adapt_tags(tags: list[str], platform: str) -> list[str]:
    """将标签列表适配到目标平台格式。"""
    spec = get_platform_spec(platform)
    if not spec.tag_format:
        return []
    lo, hi = spec.tag_count_range
    if lo == 0 and hi == 0:
        return []
    adapted = []
    for tag in tags[:hi]:
        if spec.tag_format == "#{}#":
            adapted.append(f"#{tag}#")
        elif spec.tag_format == "#{}":
            adapted.append(f"#{tag}")
        else:
            adapted.append(tag)
    return adapted


def check_platform_limits(
    title: str,
    content: str,
    platform: str,
) -> dict:
    """检查文案是否符合目标平台限制。"""
    spec = get_platform_spec(platform)
    from app.services.wordcount import count
    title_stats = count(title) if title else {"social_count": 0}
    content_stats = count(content) if content else {"social_count": 0}
    title_count = title_stats["social_count"]
    content_count = content_stats["social_count"]

    issues = []
    if spec.title_max > 0 and title_count > spec.title_max:
        issues.append(
            f"标题 {title_count} 字，超出 {spec.display_name} 上限 {spec.title_max} 字"
        )
    if content_count > spec.content_max:
        issues.append(
            f"正文 {content_count} 字，超出 {spec.display_name} 硬上限 {spec.content_max} 字"
        )
    elif content_count > spec.content_soft_max:
        issues.append(
            f"正文 {content_count} 字，超过 {spec.display_name} 软上限 {spec.content_soft_max} 字（建议精简）"
        )

    return {
        "platform": spec.display_name,
        "title_count": title_count,
        "title_max": spec.title_max,
        "content_count": content_count,
        "content_soft_max": spec.content_soft_max,
        "content_max": spec.content_max,
        "ok": len(issues) == 0,
        "issues": issues,
    }


def adapt_cta(platform: str) -> str:
    """返回平台适配的 CTA 模板。"""
    spec = get_platform_spec(platform)
    cta_map = {
        "收藏/评论引导": "记得收藏，需要的时候不迷路 ✨ 评论区告诉我你的想法",
        "关注/评论区引导": "关注不迷路，评论区告诉我你的答案",
        "一键三连": "一键三连，下期更精彩",
        "转发/评论引导": "转发让更多人看到，评论区聊聊你的看法",
        "在看/分享/关注": "觉得有用就点个在看，分享给需要的朋友",
        "赞同/收藏引导": "如果对你有帮助，点个赞同支持一下",
    }
    return cta_map.get(spec.cta_style, "记得收藏，需要的时候不迷路")