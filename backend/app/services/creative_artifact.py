"""CreativeArtifact：统一的创作对象。

目标：让「对话式创作」和「工作流创作」共用同一份创作上下文，避免：

- 作品分析被压平成一段 prompt；
- 图文规划只有页面类型，没有页面角色；
- 前端只保存图片 URL，丢失组件级内容；
- 下一次创作无法继承上一次的视觉决策。

结构：

    CreativeArtifact
    ├── source        来源作品/会话/工作流
    ├── analysis      作品分析引用与结论
    ├── brief         创作简报：目标、受众、语气、方向、保留/避免模式
    ├── storyboard    分镜：每页的语义角色、组件、内容、图片角色、理由
    ├── assets        素材
    ├── quality       质量检查
    ├── review        人工审核
    └── history       变更历史

当前阶段以 JSON 文件持久化，后续可平滑迁移到数据库。
"""
from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

_STORE_DIR = Path(__file__).resolve().parents[2] / "data" / "creative_artifacts"

# 页面类型 → 默认语义角色
_PAGE_ROLE_MAP: dict[str, str] = {
    "cover": "hook",
    "image_page": "hook",
    "pain_quote": "pain",
    "quote": "summary",
    "big_quote": "summary",
    "content": "explanation",
    "list": "evidence",
    "dark_panel": "evidence",
    "numbered_cards": "evidence",
    "icon_text": "evidence",
    "newspaper": "evidence",
    "steps": "action",
    "timeline": "process",
    "compare": "contrast",
    "qa": "explanation",
    "stat_card": "evidence",
    "profile": "credibility",
    "code_panel": "explanation",
    "end_page": "action",
}

# 语义角色 → 中文说明，用于给用户展示「为什么这样设计」
_ROLE_LABELS: dict[str, str] = {
    "hook": "开场抓注意力",
    "pain": "引发共鸣/痛点",
    "explanation": "解释说明",
    "evidence": "给出证据/要点",
    "contrast": "形成对比",
    "process": "展示过程演变",
    "action": "给出行动步骤",
    "credibility": "建立信任",
    "summary": "总结/金句收尾",
}

# 语义角色 → 推荐图片角色
_ROLE_IMAGE_ROLE: dict[str, str] = {
    "hook": "hero",
    "pain": "supporting",
    "explanation": "none",
    "evidence": "none",
    "contrast": "supporting",
    "process": "supporting",
    "action": "none",
    "credibility": "portrait",
    "summary": "atmosphere",
}

# 语义角色 → 设计理由
_ROLE_RATIONALE: dict[str, str] = {
    "hook": "第一页需要在缩略图里快速说清主题和利益点",
    "pain": "先建立共鸣，让读者觉得内容与自己有关",
    "explanation": "把关键概念讲清楚，避免只有结论没有过程",
    "evidence": "用要点或数据增强可信度",
    "contrast": "用差异制造信息增量，避免平铺直叙",
    "process": "让读者看到变化过程，增强代入感",
    "action": "给出可执行步骤，提高收藏率",
    "credibility": "增强账号或人物可信度",
    "summary": "用一句话收束，便于记忆和转发",
}


def role_label(role: str) -> str:
    return _ROLE_LABELS.get(role, "内容表达")


def infer_role(page_type: str, index: int, total: int) -> str:
    """根据页面类型与位置推断语义角色。"""
    if index == 0:
        return "hook"
    if total > 1 and index == total - 1:
        if page_type in ("end_page", "quote", "big_quote"):
            return "summary"
        if page_type in ("steps", "list", "numbered_cards"):
            return "action"
    return _PAGE_ROLE_MAP.get(page_type, "explanation")


class SourceRef(BaseModel):
    """创作来源。"""
    work_id: str = ""
    session_id: str = ""
    workflow_id: str = ""
    platform: str = "xiaohongshu"


class AnalysisRef(BaseModel):
    """作品分析引用：只存结论与来源，不复制整篇报告。"""
    analysis_id: str = ""
    source_work_ids: list[str] = Field(default_factory=list)
    confidence: float = 0.0
    keep_patterns: list[str] = Field(default_factory=list)
    avoid_patterns: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)


class CreativeBrief(BaseModel):
    """创作简报：把分析结果翻译成可执行创作方向。"""
    goal: str = ""
    audience: str = ""
    tone: str = ""
    topic: str = ""
    title: str = ""
    visual_direction: str = "叙事型"
    template_id: str = ""
    keep_patterns: list[str] = Field(default_factory=list)
    avoid_patterns: list[str] = Field(default_factory=list)


class PageComponent(BaseModel):
    """页面使用的组件。"""
    semantic_type: str = ""
    page_type: str = "content"
    template_id: str = ""
    decoration: str = ""


class StoryboardPage(BaseModel):
    """分镜页：比 card page 多一层「为什么这样设计」。"""
    page_id: str = ""
    index: int = 0
    role: str = "explanation"
    role_label: str = ""
    rationale: str = ""
    source_evidence: str = ""
    visual_goal: str = ""
    component: PageComponent = Field(default_factory=PageComponent)
    image_role: str = "none"
    content: dict[str, Any] = Field(default_factory=dict)
    image_url: str = ""
    html_url: str = ""


class QualityIssue(BaseModel):
    code: str = ""
    message: str = ""
    page_index: int = -1
    level: str = "warning"


class QualityReport(BaseModel):
    status: str = "pending"
    score: int = 0
    checks: list[str] = Field(default_factory=list)
    issues: list[QualityIssue] = Field(default_factory=list)


class ReviewState(BaseModel):
    status: str = "pending"
    feedback: str = ""
    approved_pages: list[int] = Field(default_factory=list)
    rejected_pages: list[int] = Field(default_factory=list)


class ArtifactHistoryEntry(BaseModel):
    at: float = 0.0
    action: str = ""
    detail: str = ""


class CreativeArtifact(BaseModel):
    """统一创作对象。"""
    artifact_id: str = ""
    version: int = 1
    created_at: float = 0.0
    updated_at: float = 0.0
    source: SourceRef = Field(default_factory=SourceRef)
    analysis: AnalysisRef = Field(default_factory=AnalysisRef)
    brief: CreativeBrief = Field(default_factory=CreativeBrief)
    storyboard: list[StoryboardPage] = Field(default_factory=list)
    assets: list[dict[str, Any]] = Field(default_factory=list)
    quality: QualityReport = Field(default_factory=QualityReport)
    review: ReviewState = Field(default_factory=ReviewState)
    history: list[ArtifactHistoryEntry] = Field(default_factory=list)

    def touch(self, action: str = "", detail: str = "") -> None:
        now = time.time()
        if not self.created_at:
            self.created_at = now
        self.updated_at = now
        if action:
            self.history.append(
                ArtifactHistoryEntry(at=now, action=action, detail=detail)
            )


def build_storyboard(
    pages: list[dict[str, Any]],
    *,
    template_id: str = "",
    analysis: AnalysisRef | None = None,
) -> list[StoryboardPage]:
    """把 card_draft.pages 提升为带语义角色的分镜。"""
    total = len(pages)
    storyboard: list[StoryboardPage] = []
    for index, raw in enumerate(pages):
        page = dict(raw or {})
        page_type = page.get("type") or "content"
        role = page.get("role") or infer_role(page_type, index, total)
        content = {k: v for k, v in page.items() if k not in ("type", "role", "id")}
        storyboard.append(
            StoryboardPage(
                page_id=page.get("id") or f"p{index + 1}",
                index=index,
                role=role,
                role_label=role_label(role),
                rationale=page.get("rationale") or _ROLE_RATIONALE.get(role, ""),
                source_evidence=page.get("source_evidence", ""),
                visual_goal=page.get("visual_goal") or role_label(role),
                component=PageComponent(
                    semantic_type=role,
                    page_type=page_type,
                    template_id=template_id,
                    decoration=page.get("decoration", "") or "",
                ),
                image_role=page.get("image_role") or _ROLE_IMAGE_ROLE.get(role, "none"),
                content=content,
                image_url=page.get("imageUrl") or page.get("image_url") or "",
                html_url=page.get("htmlUrl") or page.get("html_url") or "",
            )
        )
    if analysis and analysis.keep_patterns and storyboard:
        storyboard[0].source_evidence = (
            storyboard[0].source_evidence or analysis.keep_patterns[0]
        )
    return storyboard


def build_artifact(
    *,
    artifact_id: str = "",
    card_draft: dict[str, Any] | None = None,
    brief: dict[str, Any] | None = None,
    analysis: dict[str, Any] | None = None,
    source: dict[str, Any] | None = None,
) -> CreativeArtifact:
    """从现有产物构造 CreativeArtifact。"""
    draft = card_draft or {}
    pages = draft.get("pages") or []
    template_id = draft.get("suggested_template") or draft.get("template") or ""

    artifact = CreativeArtifact(
        artifact_id=artifact_id or f"ca_{uuid.uuid4().hex[:12]}",
        source=SourceRef(**(source or {})),
        analysis=AnalysisRef(**(analysis or {})),
        brief=CreativeBrief(**(brief or {})),
        storyboard=build_storyboard(
            pages, template_id=template_id, analysis=AnalysisRef(**(analysis or {}))
        ),
    )
    if template_id:
        artifact.brief.template_id = template_id
    artifact.touch(action="create", detail=f"pages={len(pages)}")
    return artifact


def _path_for(artifact_id: str) -> Path:
    safe = "".join(c for c in artifact_id if c.isalnum() or c in "-_")[:64]
    return _STORE_DIR / f"{safe}.json"


def save_artifact(artifact: CreativeArtifact) -> CreativeArtifact:
    _STORE_DIR.mkdir(parents=True, exist_ok=True)
    artifact.touch(action="save")
    _path_for(artifact.artifact_id).write_text(
        artifact.model_dump_json(indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return artifact


def load_artifact(artifact_id: str) -> CreativeArtifact | None:
    path = _path_for(artifact_id)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return CreativeArtifact(**data)
    except Exception:
        return None


def delete_artifact(artifact_id: str) -> bool:
    path = _STORE_DIR / f"{artifact_id}.json"
    if not path.exists():
        return False
    path.unlink(missing_ok=True)
    return True


def list_artifacts(limit: int = 50) -> list[dict[str, Any]]:
    if not _STORE_DIR.exists():
        return []
    items: list[dict[str, Any]] = []
    for path in sorted(_STORE_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        storyboard = data.get("storyboard") or []
        page_images = [
            p.get("image_url", "")
            for p in storyboard
            if p.get("image_url")
        ]
        cover_url = page_images[0] if page_images else ""
        first_page_html = ""
        if storyboard:
            first_content = (storyboard[0].get("content") or {})
            first_page_html = first_content.get("htmlContent", "")
        if not cover_url:
            card_draft = data.get("card_draft") or {}
            cd_pages = card_draft.get("pages") or []
            for p in cd_pages:
                img = p.get("imageUrl") or ""
                if img:
                    cover_url = img
                    page_images = [img] + [
                        pp.get("imageUrl", "")
                        for pp in cd_pages
                        if pp.get("imageUrl") and pp is not p
                    ]
                    break
            if not cover_url:
                for p in cd_pages:
                    pngs = p.get("pngUrls") or []
                    if pngs:
                        cover_url = pngs[0]
                        break
        card_draft_pages = []
        for sb in storyboard:
            page_item = {
                "id": sb.get("page_id", ""),
                "type": (sb.get("component") or {}).get("page_type", "content"),
                "role": sb.get("role", ""),
                "content": sb.get("content") or {},
            }
            if sb.get("image_url"):
                page_item["imageUrl"] = sb["image_url"]
            if sb.get("html_url"):
                page_item["htmlUrl"] = sb["html_url"]
            card_draft_pages.append(page_item)
        card_draft = {
            "title": (data.get("brief") or {}).get("title", ""),
            "suggested_template": (data.get("brief") or {}).get("template_id", ""),
            "pages": card_draft_pages,
        }
        all_page_htmls = []
        for sb in storyboard:
            content = sb.get("content") or {}
            html = content.get("htmlContent", "")
            if html:
                all_page_htmls.append(html)
        items.append(
            {
                "artifact_id": data.get("artifact_id", path.stem),
                "title": (data.get("brief") or {}).get("title", ""),
                "topic": (data.get("brief") or {}).get("topic", ""),
                "page_count": len(storyboard),
                "updated_at": data.get("updated_at", 0),
                "cover_url": cover_url,
                "page_images": page_images,
                "first_page_html": first_page_html,
                "card_draft": card_draft,
                "all_page_htmls": all_page_htmls,
            }
        )
        if len(items) >= limit:
            break
    return items


def to_card_draft(artifact: CreativeArtifact) -> dict[str, Any]:
    """反向输出给卡片编辑器使用，保证不破坏现有渲染链路。"""
    pages: list[dict[str, Any]] = []
    for page in artifact.storyboard:
        item: dict[str, Any] = {
            "id": page.page_id,
            "type": page.component.page_type,
            "role": page.role,
            "rationale": page.rationale,
            "source_evidence": page.source_evidence,
            "image_role": page.image_role,
        }
        item.update(page.content)
        if page.image_url:
            item["imageUrl"] = page.image_url
        if page.html_url:
            item["htmlUrl"] = page.html_url
        pages.append(item)
    return {
        "title": artifact.brief.title,
        "suggested_template": artifact.brief.template_id,
        "pages": pages,
    }