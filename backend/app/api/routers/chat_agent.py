"""Agent Chat 适配层端点（ReAct 模式）。

流程：获取/创建 Session → 写用户消息 → 守卫 → 直接走 ReAct Loop →
LLM 自己选工具、自己执行、自己观察、自己决定下一步。
不再有 TopPlanner 预先决定工具链。
"""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.chat_agent import ChatAgent
from app.engine.schemas import WorkflowContext
from app.agents.input_rules import ChatInputRule
from app.api.deps import get_current_user
from app.db.session import get_db
from app.services import chat_session
from app.services.sse_bus import EVENT_INTENT_PARSED, sse_bus

router = APIRouter(prefix="/api/v1/chat", tags=["chat_agent"])

logger = logging.getLogger(__name__)

_input_rule = ChatInputRule()


def _humanize_output(raw_message: str, output_data: dict | None) -> str:
    """Convert raw AgentOutput into natural language for chat display.

    Rules:
    - If output has summary, use it as the base
    - Strip internal keys (_model_used, _duration_ms, etc.)
    - Convert structured data into readable paragraphs
    - Truncate overly long content (skill_chain summaries exempt — they are pre-formatted)
    - Never expose error messages or $ symbols
    """
    if not output_data:
        return raw_message

    summary = output_data.get("summary", "")
    if summary and len(summary) > 10:
        message = summary
    else:
        message = raw_message

    key_findings = output_data.get("key_findings")
    recommendations = output_data.get("recommendations")

    parts: list[str] = []

    if message:
        cleaned = _strip_internal_markers(message)
        parts.append(cleaned)

    if key_findings and isinstance(key_findings, list) and "**关键发现：**" not in message:
        findings_text = [f"• {f}" for f in key_findings[:5] if f]
        if findings_text:
            parts.append("\n**关键发现：**\n" + "\n".join(findings_text))

    if (
        recommendations
        and isinstance(recommendations, list)
        and "**建议方向：**" not in message
        and "**选题建议：**" not in message
    ):
        recs_text = []
        for r in recommendations[:3]:
            if isinstance(r, dict):
                topic_dir = r.get("topic_direction", r.get("title", ""))
                if topic_dir:
                    recs_text.append(f"• {topic_dir}")
            elif isinstance(r, str):
                recs_text.append(f"• {r}")
        if recs_text:
            parts.append("\n**建议方向：**\n" + "\n".join(recs_text))

    result = "\n".join(parts).strip()

    result = _clean_error_leakage(result)
    return result


def _append_search_summary(summary_parts: list[str], search_data: dict) -> None:
    """把搜索结果摘要追加到 summary_parts（SEARCH_ONLY 或降级分析时调用）。"""
    results = search_data.get("results", [])
    if not results:
        return
    summary_parts.append("**搜索结果：**")
    for r in results[:5]:
        if not isinstance(r, dict):
            continue
        title = r.get("title", "")
        platform = r.get("platform", "")
        summary = r.get("summary", "")
        interactions = r.get("interactions", 0)
        prefix = f"[{platform}]" if platform else ""
        line = f"  - {prefix} {title}" if prefix else f"  - {title}"
        if interactions:
            line += f"（互动 {interactions}）"
        if summary:
            line += f"\n    {summary[:80]}"
        summary_parts.append(line)


def _sanitize_sse_payload(event_type: str, payload: dict) -> dict:
    """Presentation Layer boundary — sanitize SSE payloads before they reach the UI.

    Following Codex's Event Channel principle: internal events must NOT leak to UI.
    Following Claude Code's render-logic separation: UI only sees DisplayItem-compatible data.

    Rules:
    - Remove all keys starting with _ (internal markers)
    - Remove SQL, traceback, pymysql errors
    - Convert raw error messages to user-friendly text
    - Keep only UI-relevant fields per event type
    """
    INTERNAL_KEY_PREFIXES = ('_', 'sql', 'traceback', 'pymysql', 'internal')
    cleaned = {}
    for k, v in payload.items():
        if any(k.lower().startswith(p) for p in INTERNAL_KEY_PREFIXES):
            continue
        if isinstance(v, str):
            v = _strip_internal_markers(v)
            v = _clean_error_leakage(v)
        cleaned[k] = v

    if event_type in ('workflow_error', 'workflow_failed'):
        error_msg = cleaned.get('error', '') or cleaned.get('message', '')
        if error_msg:
            cleaned['error'] = '处理过程中遇到问题，请稍后重试'
        cleaned.pop('traceback', None)
        cleaned.pop('exception', None)

    return cleaned


def _strip_internal_markers(text: str) -> str:
    """Remove internal markers like _model_used, _duration_ms, <thinking>, <needs_clarification> tags, etc."""
    import re
    patterns = [
        r'_model_used["\s:]+["\']?\w[\w-]*["\']?',
        r'_duration_ms["\s:]+\d+',
        r'_message["\s:]+["\'][^"\']*["\']',
        r'\$+\s*$',
        r'\w+_gen\s*未收到[^，。]*',
        r'未收到前端注入[^，。]*',
        r'，?请确认[^，。\n]*生成[^，。\n]*',
        r'Data truncated for column[^，。\n]*',
        r'SQL:\s*[^。\n]*',
        r'\(pymysql\.err\.[A-Za-z]+\)[^。\n]*',
        r'工作流启动失败[^，。\n]*',
        r'workflow\s+start\s+failed[^，.\n]*',
    ]
    for p in patterns:
        text = re.sub(p, '', text)
    # 保护代码块中的内容不被误删
    code_blocks: list[str] = []
    text = re.sub(r'```[\s\S]*?```', lambda m: (
        code_blocks.append(m.group()) or f'\x00CB{len(code_blocks) - 1}\x00'
    ), text)
    # 清理 <thinking>...</thinking> 标签及其内容（思考过程通过 reasoning 字段单独展示）
    text = re.sub(r'<thinking>[\s\S]*?</thinking>', '', text, flags=re.IGNORECASE)
    text = re.sub(r'<thinking>[\s\S]*$', '', text, flags=re.IGNORECASE)
    # 清理 <needs_clarification>...</needs_clarification> 标签及其内容（澄清通过独立卡片展示）
    text = re.sub(r'<needs_clarification>[\s\S]*?</needs_clarification>', '', text, flags=re.IGNORECASE)
    text = re.sub(r'<needs_clarification>[\s\S]*$', '', text, flags=re.IGNORECASE)
    # 恢复代码块
    text = re.sub(r'\x00CB(\d+)\x00', lambda m: code_blocks[int(m.group(1))], text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def _clean_error_leakage(text: str) -> str:
    """Remove leaked internal error messages."""
    import re
    error_patterns = [
        # 含 "error" 键的结构化 JSON（loop 工具失败 observation 被 LLM 复述进最终回复时）
        # 必须放在行级模式之前：否则 Error 行级匹配会先破坏 JSON 结构留下残缺片段
        r'\{[^{}]*"error"\s*:[^{}]*\}',
        r'(?:Traceback|Error|Exception)[^\n]*(?:\n[^\n]*){0,3}',
        r'File\s+"[^"]+",\s*line\s+\d+',
        r'pymysql\.err\.\w+',
        r'DataError.*?row \d+',
    ]
    for p in error_patterns:
        text = re.sub(p, '[内部错误已隐藏]', text)
    # loop 工具失败/熔断标记词：直接剔除（整段替换会产生"引擎 [内部错误已隐藏] 已拦截"这类破碎句）
    text = re.sub(r'\btool_(?:failed|blocked)\b[\s:：,，]*', '', text)
    text = re.sub(r'\$\s*\n?', '', text)
    text = re.sub(r'\n+', '\n', text)
    return text.strip()


class AgentChatRequest(BaseModel):
    message: str = Field(..., max_length=10000)
    mode: str = Field(default="auto", pattern="^(auto|full_pipeline|chat)$")
    account_id: str | None = None
    session_id: str | None = None
    agent_id: str | None = Field(default=None, description="指定使用的智能体 ID，不传则默认 chat_agent")
    creation_type: str | None = Field(default=None, description="当前创作类型(image_text/voiceover/short_video/ai_edit/long_article/live_clip)，用于按需加载Skill")
    analysis_context: str | None = Field(default=None, description="AI数据分析报告上下文，注入到 prompt 中让 AI 基于真实数据给建议")
    work_context: dict | None = Field(default=None, description="当前作品上下文，包含标题/平台/正文/指标等")
    workspace_id: str | None = Field(default=None, description="当前绑定的本地工作区 ID")
    file_context: dict | None = Field(default=None, description="当前选中的对话/本地文件元数据")
    folder_context: dict | None = Field(default=None, description="当前文件夹的对话文件/工作区文件列表")
    model_settings: dict | None = Field(default=None, description="模型和推送设置，包含 enable_wechat_push, wechat_target_user_id, enable_feishu_push, feishu_chat_id 等")
    auto_approve: bool = Field(default=True, description="工具调用是否自动放行（True=自动放行，False=需要用户确认）")


_LOCAL_FILE_HINTS = ("本地文件", "本地文件夹", "本地文档", "本地目录", "文件夹", "工作区文件", "工作区里", "文件中的", "文件里", "找文件", "查文件")
_LOCAL_FILE_NOISE = (
    "帮我", "请", "查找", "搜索", "搜一下", "找一下", "寻找", "看看", "找", "查",
    "本地文件", "本地文件夹", "本地文档", "本地目录", "文件夹", "工作区", "文件", "文档",
    "目录", "中的", "里面", "里", "一个", "那份", "那篇", "这个", "有没有",
)


_trigger_words_cache: dict[str, str] | None = None


def _get_third_party_trigger_words() -> dict[str, str]:
    """从 Skill Registry 获取所有非本地平台的触发词（元数据驱动，无需硬编码）。

    结果在首次调用后缓存，避免每次请求都重新扫描注册表。
    """
    global _trigger_words_cache
    if _trigger_words_cache is not None:
        return _trigger_words_cache
    try:
        from app.tools.registry import SkillRegistry, ensure_builtin_skills_registered
        ensure_builtin_skills_registered()
        registry = SkillRegistry.instance()
        registry.scan_third_party()
        _trigger_words_cache = registry.all_trigger_words_for_non_local_platforms()
        return _trigger_words_cache
    except Exception:
        return {}


def _looks_like_local_file_request(message: str) -> bool:
    if not message:
        return False
    _trigger_words = _get_third_party_trigger_words()
    if _trigger_words and any(kw in message.lower() for kw in _trigger_words):
        return False
    has_file_word = any(h in message for h in ("文件", "文档", "目录"))
    has_local_word = any(h in message for h in ("本地", "文件夹", "工作区", "对话文件"))
    has_action = any(h in message for h in ("找", "查", "搜", "读", "打开", "看看", "列一下"))
    return (has_file_word and has_local_word and has_action) or any(h in message for h in ("找文件", "查文件", "本地文件"))


def _extract_local_file_terms(message: str) -> list[str]:
    import re as _re
    msg = message
    for noise in _LOCAL_FILE_NOISE:
        msg = msg.replace(noise, " ")
    parts = [
        p.strip()
        for p in _re.split(r"[\s,，。;；、:：]+", msg)
        if p.strip() and len(p.strip()) >= 2
    ]
    return parts[:5] or [message.strip()[:40]]


def _is_bare_analysis_request(message: str) -> bool:
    """Return True when the message asks to analyze a piece of content without supplying it."""
    if not message or len(message.strip()) > 24:
        return False

    compact = message.strip()
    analysis_phrases = (
        "分析一下",
        "分析这篇",
        "分析这个",
        "拆解一下",
        "拆解这篇",
        "点评一下",
        "帮我看下",
        "帮我看一下",
        "看下这篇",
        "看看这篇",
    )
    if not any(phrase in compact for phrase in analysis_phrases):
        return False

    # 用户已经带上了正文、链接或明确的粘贴分隔符时，进入正常分析流程。
    if any(marker in compact for marker in ("：", ":", "\n", "http://", "https://")):
        return False

    return True


async def _try_local_file_search(
    message: str,
    session_id: str,
    user_id: str,
    request: "AgentChatRequest",
) -> dict | None:
    if not _looks_like_local_file_request(message) or request.agent_id:
        return None
    _trigger_words = _get_third_party_trigger_words()
    if _trigger_words and any(kw in message.lower() for kw in _trigger_words):
        logger.info(f"[chat_agent] skip local_file_search: third-party platform keyword detected in '{message[:60]}'")
        return None

    terms = _extract_local_file_terms(message)
    matches: list[dict] = []
    all_files: list[dict] = []
    all_file_count = 0

    try:
        from app.services import chat_file as chat_file_svc
        records = await chat_file_svc.list_files_for_session(session_id)
        for f in records:
            name = str(f.get("name") or "")
            content = str(f.get("content_text") or "")[:20000]
            meta = f.get("meta") or {}
            meta_text = str(meta.get("topic") or meta.get("source") or "")
            all_file_count += 1
            if len(all_files) < 40:
                all_files.append({
                    "name": name,
                    "path": name,
                    "size": f.get("size") or 0,
                    "source": "对话文件",
                    "meta": meta,
                })
            haystack = (name + "\n" + content + "\n" + meta_text).lower()
            if any(term.lower() in haystack for term in terms):
                matches.append({
                    "name": name,
                    "path": name,
                    "size": f.get("size") or 0,
                    "source": "对话文件",
                    "meta": meta,
                })
    except Exception as exc:
        logger.warning(f"[chat_agent] local chat-file scan failed: {exc}")

    if request.workspace_id:
        try:
            from pathlib import Path as _Path
            from app.api.routers import workspace as workspace_api
            root = workspace_api._resolve_root(request.workspace_id, user_id)
            skip_dirs = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build", ".next"}
            text_exts = {".md", ".txt", ".json", ".csv", ".py", ".ts", ".vue", ".js", ".html", ".yaml", ".yml", ".org"}
            for p in root.rglob("*"):
                try:
                    rel = str(p.relative_to(root))
                    if any(part in skip_dirs for part in p.parts):
                        continue
                    if not p.is_file():
                        continue
                    all_file_count += 1
                    if len(all_files) < 40:
                        all_files.append({
                            "name": p.name,
                            "path": rel,
                            "size": p.stat().st_size if p.stat().st_size is not None else 0,
                            "source": "本地工作区",
                        })
                    haystack = rel.lower()
                    if p.suffix.lower() in text_exts and p.stat().st_size <= 200_000:
                        try:
                            haystack += "\n" + p.read_text(encoding="utf-8", errors="ignore")[:20000].lower()
                        except Exception:
                            pass
                    if any(term.lower() in haystack for term in terms):
                        matches.append({
                            "name": p.name,
                            "path": rel,
                            "size": p.stat().st_size,
                            "source": "本地工作区",
                        })
                except Exception:
                    continue
        except Exception as exc:
            logger.warning(f"[chat_agent] local workspace scan failed: {exc}")

    seen = {(m.get("path"), m.get("name")) for m in matches}
    deduped = []
    for m in matches:
        key = (m.get("path"), m.get("name"))
        if key not in seen:
            continue
        seen.discard(key)
        deduped.append(m)
    matches = deduped[:20]

    if matches:
        lines = [f"📁 找到 {len(matches)} 个匹配文件（关键词：{' / '.join(terms)}）："]
        for m in matches:
            tag = m.get("source") or ""
            size = m.get("size") or 0
            size_text = f"{size / 1024:.1f} KB" if size >= 1024 else f"{size} B"
            topic = (m.get("meta") or {}).get("topic") if isinstance(m.get("meta"), dict) else ""
            topic_text = f" · {topic}" if topic else ""
            lines.append(f"- **{m.get('name')}** [{tag} · {size_text}]\n  `{m.get('path')}`{topic_text}")
    else:
        lines = [f"未找到含「{' / '.join(terms)}」的文件。"]
        if all_files:
            lines.append(f"当前可访问的本地/对话文件共 {all_file_count} 个，以下是部分文件：")
            for f in all_files[-8:]:
                lines.append(f"- {f.get('name')} `{f.get('path')}`")
        else:
            lines.append("当前会话没有对话文件，也没有绑定本地工作区，所以不会去搜索互联网热点。")
    summary = "\n".join(lines)

    intent = {
        "action": "local_file_search",
        "tools": ["local_file_search"],
        "topic": message[:100],
        "params": None,
        "confidence": 1.0,
        "is_chat": False,
    }
    await chat_session.add_message(
        session_id, "assistant", summary,
        {"intent": intent, "workflow_status": "completed", "source": "local_file_search"},
    )
    _cs = await chat_session.get_creative_state(session_id)
    return {
        "session_id": session_id,
        "status": "shortcut_completed",
        "intent": intent,
        "message": summary,
        "plan_steps": ["local_file_search"],
        "creative_state": _cs,
    }


async def _generate_session_summary(
    session_id: str,
    recent_limit: int = 2,
) -> str | None:
    """用 LLM 将旧消息压缩为摘要，保留最近 recent_limit 条不参与摘要。"""
    from app.services import chat_session as _cs
    from app.engine.governance.llm_circuit import get_llm_circuit
    _circuit = get_llm_circuit()
    if not _circuit.allow_request():
        return None

    try:
        all_messages = await _cs.list_messages(session_id, limit=200)
        user_assistant_msgs = [
            m for m in all_messages
            if m["role"] in ("user", "assistant")
        ]

        if len(user_assistant_msgs) <= recent_limit:
            return None

        old_msgs = user_assistant_msgs[:-recent_limit]

        history_lines = []
        for m in old_msgs:
            role = "用户" if m["role"] == "user" else "助手"
            content = m["content"][:500]
            history_lines.append(f"{role}：{content}")

        history_text = "\n".join(history_lines)

        if not history_text.strip():
            return None

        summary_prompt = (
            "请将以下对话历史压缩为简洁但完整的摘要。必须保留：\n"
            "1. 用户的核心需求（要写什么主题、什么风格、什么平台）\n"
            "2. 关键决策和修改指令（用户要求改了什么、调整了什么）\n"
            "3. 已产出的文案标题和关键内容\n"
            "4. 用户的偏好和反馈（喜欢什么、不喜欢什么）\n"
            "不要丢失任何重要信息，但可以省略过程细节。\n"
            "摘要长度控制在 300-500 字。"
        )

        from app.agents.registry import AgentRegistry
        _registry = AgentRegistry()
        try:
            _harness = _registry.build_harness("chat_agent")
            _llm = _harness.llm
        except Exception:
            _llm = None

        if _llm is None:
            logger.warning("[chat_agent] no LLM available for summary generation")
            return None

        result = await _llm.chat(
            [
                {"role": "system", "content": summary_prompt},
                {"role": "user", "content": f"对话历史：\n{history_text}"},
            ],
            response_format=None,
        )

        summary = result.get("content", "").strip()
        if summary and len(summary) >= 20:
            return summary

    except Exception as e:
        logger.warning(f"[chat_agent] session summary generation failed: {e}")

    return None


@router.post("/agent")
async def agent_chat(
    request: AgentChatRequest,
    user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    # 1. 获取或创建 Session
    if request.session_id:
        existing = await chat_session.get_session(request.session_id)
        if existing is None:
            logger.warning(f"[chat_agent] session_id={request.session_id} not found in DB, ensuring session")
            await chat_session.ensure_session(request.session_id, user_id)
            session_id = request.session_id
        elif existing["user_id"] != user_id:
            raise HTTPException(status_code=404, detail="会话不存在")
        else:
            session_id = request.session_id
    else:
        session = await chat_session.create_session(user_id)
        session_id = session["id"]

    # 1.5 注入作品上下文（强化版：强制AI必须使用）
    logger.info(f"[chat_agent] DEBUG: work_context={request.work_context is not None}, message={str(request.message)[:60]}")
    if request.work_context:
        wc = request.work_context
        logger.info(f"[chat_agent] work_context received: keys={list(wc.keys())}, title={wc.get('title')}, contentText_len={len(wc.get('contentText') or '')}")
        work_prompt_parts = [
            "【重要】当前用户正在查看以下作品，你必须基于此作品的实际内容来回答问题：",
            "",
            "=== 作品信息 ===",
        ]
        if wc.get("title"):
            work_prompt_parts.append(f"📝 标题: {wc['title']}")
        if wc.get("platform"):
            work_prompt_parts.append(f"📱 平台: {wc['platform']}")
        if wc.get("contentType"):
            work_prompt_parts.append(f"📄 类型: {wc['contentType']}")
        if wc.get("performanceTier"):
            work_prompt_parts.append(f"⭐ 等级: {wc['performanceTier']}")
        if wc.get("contentText"):
            work_prompt_parts.append(f"\n📖 正文内容（必须以此为准）:\n{wc['contentText'][:800]}")
        if wc.get("cardDraft"):
            import json as _json
            pages = wc["cardDraft"].get("pages", []) if isinstance(wc["cardDraft"], dict) else []
            if pages:
                work_prompt_parts.append(f"\n🖼️ 当前视觉组图卡片（重新编排时必须基于这些内容，不得凭空编造）:\n{_json.dumps(pages, ensure_ascii=False)[:6000]}")
        if wc.get("scriptText"):
            work_prompt_parts.append(f"\n🎬 脚本内容:\n{wc['scriptText'][:800]}")
        if wc.get("tags"):
            work_prompt_parts.append(f"🏷️ 标签: {', '.join(wc['tags'][:10])}")
        metrics = wc.get("metrics")
        if metrics:
            ir = metrics.get("interactionRate", 0) or 0
            work_prompt_parts.append(f"📊 数据: 浏览{metrics.get('views', 0)} | 点赞{metrics.get('likes', 0)} | 互动率{ir:.1%}")
        work_prompt_parts.extend([
            "",
            "=== 强制要求 ===",
            "1. 回答时必须引用上述作品的实际内容，不要说'没有内容'或'未保存'",
            "2. 如果用户要求分析/优化/改写，直接针对上述正文内容进行操作",
            "3. 绝对禁止回复'草稿文件还没有保存'或类似的内容缺失提示",
            "4. 作品内容已经完整提供给你，立即开始工作！",
            "",
        ])
        await chat_session.add_message(session_id, "system", "\n".join(work_prompt_parts))

    # 1.6 注入分析上下文
    if request.analysis_context:
        await chat_session.add_message(
            session_id, "system",
            request.analysis_context + "\n\n请基于以上数据分析上下文来回答用户问题，给出具体、可操作的建议。",
        )

    # 1.7 注入草稿结构说明书
    if request.work_context:
        try:
            from app.agents.draft_schema import build_draft_schema_prompt
            schema_prompt = build_draft_schema_prompt(request.work_context)
            await chat_session.add_message(session_id, "system", schema_prompt)
        except Exception:
            pass

    # 2. 写用户消息
    await chat_session.add_message(session_id, "user", request.message)

    # 3. 输入守卫
    context = WorkflowContext(
        workflow_id="",
        node_id="chat",
        user_id=user_id,
        account_id=request.account_id or "",
    )
    if request.work_context:
        context.extra["work_context"] = request.work_context
    if request.model_settings:
        context.extra["model_settings"] = request.model_settings
        logger.info(f"[chat_agent] model_settings received: {list(request.model_settings.keys())}")
    if not await _input_rule.check_pre({"message": request.message}, context):
        await chat_session.add_message(
            session_id, "assistant", "输入未通过安全校验", {"workflow_status": "error"}
        )
        return {"session_id": session_id, "status": "blocked", "message": "输入未通过安全校验"}

    # 3.5 输入清洗
    sanitized_message = _input_rule.sanitize(request.message)

    # 3.6 本地文件请求直接走文件检索
    _local_file_result = await _try_local_file_search(
        sanitized_message, session_id, user_id, request,
    )
    if _local_file_result is not None:
        return _local_file_result

    # 3.7 纯分析请求但没有提供正文/上下文时，直接说明需要内容，避免空转结束。
    if (
        _is_bare_analysis_request(sanitized_message)
        and not request.work_context
        and not request.analysis_context
        and not request.file_context
        and not request.folder_context
    ):
        _direct_message = (
            "我还没有看到要分析的具体文案内容。"
            "你可以直接把文案正文粘贴在问题里，例如：\n"
            "帮我分析一下这篇文案：<粘贴正文>\n"
            "或者先在作品区选中/打开对应作品后再发送，我就能基于实际内容继续分析。"
        )
        await chat_session.add_message(
            session_id,
            "assistant",
            _direct_message,
            {
                "workflow_status": "completed",
                "source": "analysis_content_guard",
                "intent": {
                    "action": "ANALYZE_ONLY",
                    "tools": [],
                    "topic": sanitized_message[:100],
                    "confidence": 1.0,
                    "is_chat": True,
                },
            },
        )
        return {
            "session_id": session_id,
            "status": "chat",
            "intent": {
                "action": "ANALYZE_ONLY",
                "tools": [],
                "topic": sanitized_message[:100],
                "confidence": 1.0,
                "is_chat": True,
            },
            "message": _direct_message,
        }

    # 4. LLM 熔断检查
    from app.engine.governance.llm_circuit import get_llm_circuit
    _circuit = get_llm_circuit()
    if not _circuit.allow_request():
        _abort_reason = _circuit.open_reason or "LLM 连续失败"
        logger.error(f"[chat_agent] LLM circuit OPEN at entry, refusing: {_abort_reason}")
        await chat_session.add_message(
            session_id, "assistant",
            f"LLM 服务不可用（{_abort_reason}），请检查 API 余额和配置后重试。",
            {"workflow_status": "error", "source": "llm_circuit"},
        )
        return {
            "session_id": session_id,
            "status": "error",
            "message": f"LLM 服务不可用（{_abort_reason}），请检查 API 余额和配置",
        }

    # 5. 会话摘要（长对话压缩）
    # 逻辑：达到阈值 → 生成摘要 → 记录已摘要数 → 等新增消息再次达到阈值才重新生成
    _session_summary_text: str | None = None
    try:
        _SUMMARY_THRESHOLD = 8
        _RECENT_LIMIT = 4
        _total_msg_count = await chat_session.count_messages(session_id)
        _summary_meta = await chat_session.get_session_summary_meta(session_id)
        _last_summarized_count = (_summary_meta or {}).get("summarized_count", 0) or 0
        _new_msgs_since_summary = _total_msg_count - _last_summarized_count

        logger.info(f"[chat_agent] summary check: total={_total_msg_count}, last_summarized={_last_summarized_count}, new_since={_new_msgs_since_summary}, threshold={_SUMMARY_THRESHOLD}")

        if _new_msgs_since_summary > _SUMMARY_THRESHOLD:
            try:
                await sse_bus.publish(session_id, "decision_made", {
                    "decision": f"正在更新对话摘要…",
                    "iteration": 0,
                })
            except Exception as _sse_err:
                logger.warning(f"[chat_agent] SSE publish failed: {_sse_err}")
            _new_summary = await _generate_session_summary(
                session_id, recent_limit=_RECENT_LIMIT
            )
            if _new_summary:
                await chat_session.save_session_summary(
                    session_id, _new_summary,
                    summarized_count=_total_msg_count - _RECENT_LIMIT,
                )
                _session_summary_text = _new_summary
                logger.info(f"[chat_agent] summary updated, {len(_new_summary)} chars, summarized_count={_total_msg_count - _RECENT_LIMIT}")
            else:
                logger.warning("[chat_agent] _generate_session_summary returned None, fallback to cached")
                _cached_summary = await chat_session.get_session_summary(session_id)
                if _cached_summary:
                    _session_summary_text = _cached_summary
        else:
            _session_summary_text = await chat_session.get_session_summary(session_id)
            logger.info(f"[chat_agent] new msgs ({_new_msgs_since_summary}) <= threshold ({_SUMMARY_THRESHOLD}), use cached summary")
    except Exception as _summary_err:
        logger.warning(f"[chat_agent] summary block error: {_summary_err}")

    # 6. 直接走 ReAct Loop — LLM 自己选工具、自己执行、自己观察
    _extra_prompt: str | None = None
    if _session_summary_text:
        _extra_prompt = f"[早期对话摘要]\n{_session_summary_text}\n[摘要结束]"

    if request.model_settings:
        _wx_target = (request.model_settings or {}).get("wechat_target_user_id", "")
        if _wx_target:
            _wx_prompt = f"[微信推送配置] wechat_target_user_id={_wx_target} — 当用户要求发到微信时，使用此 wxid 作为 to_user_id 参数调用 wechat_send_text 或 wechat_send_file。"
            if _extra_prompt:
                _extra_prompt = _extra_prompt + "\n" + _wx_prompt
            else:
                _extra_prompt = _wx_prompt

    if request.work_context:
        wc = request.work_context
        _work_prompt_parts = [
            "",
            "【重要】当前用户正在查看以下作品，你必须基于此作品的实际内容来回答问题：",
            "",
            "=== 作品信息 ===",
        ]
        if wc.get("title"):
            _work_prompt_parts.append(f"标题: {wc['title']}")
        if wc.get("platform"):
            _work_prompt_parts.append(f"平台: {wc['platform']}")
        if wc.get("contentType"):
            _work_prompt_parts.append(f"类型: {wc['contentType']}")
        if wc.get("performanceTier"):
            _work_prompt_parts.append(f"等级: {wc['performanceTier']}")
        if wc.get("contentText"):
            _work_prompt_parts.append(f"\n正文内容（必须以此为准）:\n{wc['contentText'][:800]}")
        if wc.get("cardDraft"):
            import json as _json
            pages = wc["cardDraft"].get("pages", []) if isinstance(wc["cardDraft"], dict) else []
            if pages:
                _work_prompt_parts.append(f"\n当前视觉组图卡片（重新编排时必须基于这些内容，不得凭空编造）:\n{_json.dumps(pages, ensure_ascii=False)[:6000]}")
        if wc.get("scriptText"):
            _work_prompt_parts.append(f"\n脚本内容:\n{wc['scriptText'][:800]}")
        if wc.get("tags"):
            _work_prompt_parts.append(f"标签: {', '.join(wc['tags'][:10])}")
        _wc_metrics = wc.get("metrics")
        if _wc_metrics:
            _ir = _wc_metrics.get("interactionRate", 0) or 0
            _work_prompt_parts.append(f"数据: 浏览{_wc_metrics.get('views', 0)} | 点赞{_wc_metrics.get('likes', 0)} | 互动率{_ir:.1%}")
        _work_prompt_parts.extend([
            "",
            "=== 强制要求 ===",
            "1. 回答时必须引用上述作品的实际内容，不要说'没有内容'或'未保存'",
            "2. 如果用户要求分析/优化/改写，直接针对上述正文内容进行操作",
            "3. 绝对禁止回复'草稿文件还没有保存'或类似的内容缺失提示",
            "4. 作品内容已经完整提供给你，立即开始工作！",
        ])
        _work_prompt_str = "\n".join(_work_prompt_parts)
        if _extra_prompt:
            _extra_prompt = _extra_prompt + "\n" + _work_prompt_str
        else:
            _extra_prompt = _work_prompt_str
        logger.info(f"[chat_agent] work_context injected into extra_system_prompt, len={len(_work_prompt_str)}")

    async def _sse_emit_callback(node_id: str, event_type: str, payload: dict) -> None:
        try:
            if event_type == "agent_message_delta":
                delta_preview = (payload.get("delta") or "")[:60]
                logger.info(f"[chat_agent] SSE emit: {event_type}, node={node_id}, delta_len={len(payload.get('delta', ''))}, preview={delta_preview!r}")
            elif event_type == "reasoning_summary_text_delta":
                delta_preview = (payload.get("delta") or "")[:60]
                logger.info(f"[chat_agent] SSE emit: {event_type}, node={node_id}, delta_len={len(payload.get('delta', ''))}, preview={delta_preview!r}")
            else:
                logger.info(f"[chat_agent] SSE emit: {event_type}, node={node_id}, keys={list(payload.keys())}")
            await sse_bus.publish(session_id, event_type, payload)
        except Exception as _cb_err:
            logger.warning(f"[chat_agent] SSE emit callback error: {_cb_err}")

    agent = ChatAgent(emit_callback=_sse_emit_callback)

    # 发送 chat_turn_started 事件，标记新一轮对话开始
    # 前端用此事件作为"开始接收事件"的标志，忽略之前的 replay 事件
    await sse_bus.publish(session_id, "chat_turn_started", {
        "session_id": session_id,
        "message_preview": sanitized_message[:60],
    })
    result = await agent.process(
        sanitized_message,
        session_id,
        user_id,
        account_id=request.account_id or "",
        db=db,
        workflow_id=session_id,
        agent_id=request.agent_id,
        creation_type=request.creation_type,
        extra_system_prompt=_extra_prompt,
        work_context=request.work_context,
        auto_approve=request.auto_approve,
    )

    # 7. 结果处理
    if result.status == "workflow_started":
        output_data = result.output.output if result.output else {}
        workflow_id = output_data.get("workflow_id", "")
        await chat_session.add_message(
            session_id, "assistant",
            "已启动处理，正在为您准备内容…",
            {"workflow_id": workflow_id, "workflow_status": "running", "source": "react_loop"},
        )
        if workflow_id:
            await sse_bus.publish(workflow_id, EVENT_INTENT_PARSED, {
                "workflow_id": workflow_id,
                "topic": sanitized_message[:100],
            })
        return {
            "session_id": session_id,
            "workflow_id": workflow_id,
            "status": "workflow_started",
        }

    if result.status == "awaiting_clarification":
        output_data = result.output.output if result.output else {}
        await chat_session.add_message(
            session_id, "assistant", result.message,
            {
                "workflow_status": "awaiting_clarification",
                "source": "react_loop",
                "loop_state_path": output_data.get("_loop_state_path", ""),
                "clarification_prompt": output_data.get("_clarification_prompt", ""),
                "clarification_skill": output_data.get("_clarification_skill", ""),
                "clarification_batches": output_data.get("_clarification_batches", []),
            },
        )
        return {
            "session_id": session_id,
            "status": "awaiting_clarification",
            "clarification_prompt": output_data.get("_clarification_prompt", ""),
            "clarification_skill": output_data.get("_clarification_skill", ""),
            "clarification_batches": output_data.get("_clarification_batches", []),
            "loop_state_path": output_data.get("_loop_state_path", ""),
        }

    if result.status == "awaiting_confirmation":
        output_data = result.output.output if result.output else {}
        await chat_session.add_message(
            session_id, "assistant", result.message,
            {
                "workflow_status": "awaiting_confirmation",
                "source": "react_loop",
                "loop_state_path": output_data.get("_loop_state_path", ""),
                "confirmation_prompt": output_data.get("_confirmation_prompt", ""),
                "confirmation_skill": output_data.get("_confirmation_skill", ""),
            },
        )
        return {
            "session_id": session_id,
            "status": "awaiting_confirmation",
            "confirmation_prompt": output_data.get("_confirmation_prompt", ""),
            "confirmation_skill": output_data.get("_confirmation_skill", ""),
            "loop_state_path": output_data.get("_loop_state_path", ""),
        }

    output_data = result.output.output if result.output else None
    humanized_message = _humanize_output(result.message, output_data)

    agent_meta = {
        "workflow_status": "completed" if result.output else "error",
        "source": "react_loop",
    }
    await chat_session.add_message(session_id, "assistant", humanized_message, agent_meta)

    try:
        await sse_bus.publish(session_id, "workflow_completed", {
            "workflow_id": session_id,
        })
        logger.info(f"[chat_agent] workflow_completed published to SSE bus for session={session_id}")
    except Exception as _sse_finish_err:
        logger.warning(f"[chat_agent] failed to publish workflow_completed: {_sse_finish_err}")

    thinking = output_data.get("_last_thought", "") if output_data else ""

    creative_state_data = await chat_session.get_creative_state(session_id)

    return {
        "session_id": session_id,
        "status": result.status,
        "output": output_data,
        "message": humanized_message,
        "thinking": thinking or None,
        "creative_state": creative_state_data,
    }

# Confirm API
class ConfirmRequest(BaseModel):
    session_id: str = Field(..., description="会话 ID")
    loop_state_path: str = Field(..., description="循环状态文件路径")
    action: str = Field(..., pattern="^(approve|reject)$")
    feedback: str = Field(default="", description="用户反馈（可选）")

@router.post("/confirm")
async def confirm_action(
    request: ConfirmRequest,
    user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """确认或拒绝等待中的高危操作，恢复 Agentic Loop。"""
    import logging as _logging
    import asyncio
    _logger = _logging.getLogger("chat_agent.confirm")
    _logger.info(f"[confirm] session={request.session_id} action={request.action} path={request.loop_state_path}")

    from app.engine.harness.executor.loop_state import load_loop_state, cleanup_loop_state
    from app.agents.registry import AgentRegistry
    from app.tools.context_vars import current_db_session

    try:
        state = load_loop_state(request.loop_state_path)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="循环状态不存在或已过期")

    # Build user decision observation
    decision = "approved" if request.action == "approve" else "rejected"
    obs = f"[observation] 用户{decision}了操作" + (f": {request.feedback}" if request.feedback else "")
    state["messages"].append({"role": "user", "content": obs})

    if request.action == "reject":
        await chat_session.add_message(
            request.session_id, "assistant", "操作已取消。",
            {"workflow_status": "completed", "source": "react_loop"},
        )
        cleanup_loop_state(request.loop_state_path)
        return {
            "session_id": request.session_id,
            "status": "rejected",
            "message": "操作已取消。",
            "action": request.action,
        }

    # ── approve: 立即返回，续跑在后台异步执行，结果通过 SSE 推送 ──
    _confirm_session_id = state["context_snapshot"].get("workflow_id", "") or request.session_id

    async def _run_resume_background():
        """后台续跑 ReAct 循环，结果通过 SSE 实时推送。"""
        from app.engine.harness.observer.observer import Observer

        registry = AgentRegistry()
        harness = registry.build_harness("chat_agent")
        executor = harness.executor
        if hasattr(executor, "max_iterations") and state.get("max_iterations"):
            executor.max_iterations = int(state["max_iterations"])

        async def _bg_sse_emit(node_id: str, event_type: str, payload: dict) -> None:
            try:
                await sse_bus.publish(_confirm_session_id, event_type, payload)
            except Exception:
                pass

        harness.observer = Observer(emit_callback=_bg_sse_emit)

        _saved_auto_approve = state.get("context_snapshot", {}).get("extra", {}).get("auto_approve", True)
        if not _saved_auto_approve:
            for _tn, _pol in harness.guardian._policies.items():
                if _pol.needs_confirmation:
                    continue
                _pol.auto_allow = False
                _pol.needs_confirmation = True
            _logger.info(f"[confirm-bg] auto_approve=False restored from loop_state")

        from app.tools.context_vars import current_db_session as _cdbs
        from app.engine.schemas import WorkflowContext
        from app.db.session import AsyncSessionLocal

        async with AsyncSessionLocal() as _bg_db:
            _token = _cdbs.set(_bg_db)
            try:
                ctx = WorkflowContext(
                    workflow_id=state["context_snapshot"].get("workflow_id", ""),
                    node_id="chat",
                    user_id=user_id,
                    account_id=state["context_snapshot"].get("account_id", ""),
                )
                saved_extra = state.get("context_snapshot", {}).get("extra")
                if isinstance(saved_extra, dict):
                    ctx.extra.update(saved_extra)

                # 执行被批准的工具
                if state.get("pending_skill_call"):
                    pending = state["pending_skill_call"]
                    call = {
                        "name": pending.get("name", ""),
                        "arguments": pending.get("arguments", {}) or {},
                    }
                    if call["name"]:
                        skill_map = {s.name: s for s in harness.skills}
                        try:
                            result_obs, _new_conf = await executor._execute_tool_call(  # noqa: SLF001
                                harness, ctx, skill_map, call, _approved=True
                            )
                        except Exception as e:
                            result_obs = f'[observation] {{"error": "tool execution failed: {e}"}}'
                        state["messages"].append({"role": "user", "content": f"[observation] {result_obs}"})

                output = await executor.execute(
                    harness,
                    {"topic": ""},
                    ctx,
                    resume_messages=state["messages"],
                )
            finally:
                _cdbs.reset(_token)

        cleanup_loop_state(request.loop_state_path)

        # 续跑再次触发确认门
        if isinstance(output, dict) and output.get("_awaiting_confirmation"):
            new_prompt = output.get("_confirmation_prompt", "")
            new_skill = output.get("_confirmation_skill", "")
            new_state_path = output.get("_loop_state_path", "")
            await chat_session.add_message(
                request.session_id, "assistant",
                new_prompt or "需要进一步确认操作",
                {
                    "workflow_status": "awaiting_confirmation",
                    "source": "react_loop",
                    "loop_state_path": new_state_path,
                    "confirmation_prompt": new_prompt,
                    "confirmation_skill": new_skill,
                },
            )
            try:
                await sse_bus.publish(_confirm_session_id, "agent_confirm_required", {
                    "confirmation_prompt": new_prompt,
                    "confirmation_skill": new_skill,
                    "loop_state_path": new_state_path,
                })
            except Exception:
                pass
            return

        # 正常完成
        output_data = output if isinstance(output, dict) else {}
        final_message = _humanize_output(output_data.get("summary", ""), output_data)
        if not final_message:
            final_message = "操作已完成。"
        await chat_session.add_message(
            request.session_id, "assistant", final_message,
            {"workflow_status": "completed", "source": "react_loop"},
        )
        try:
            await sse_bus.publish(_confirm_session_id, "agent_loop_done", {
                "status": "completed",
                "message": final_message,
            })
        except Exception:
            pass

    # 启动后台任务
    asyncio.create_task(_run_resume_background())
    _logger.info(f"[confirm] approve → background resume started for session={request.session_id}")

    # 立即返回
    return {
        "session_id": request.session_id,
        "status": "resumed",
        "message": "操作已确认，正在继续执行…",
        "action": request.action,
    }


# Clarify API
class ClarifyRequest(BaseModel):
    model_config = {"arbitrary_types_allowed": True}
    session_id: str = Field(..., description="会话 ID")
    loop_state_path: str = Field(..., description="循环状态文件路径")
    answers: dict = Field(default_factory=dict, description="用户回答 {field_name: value}")
    batch_id: str = Field(default="", description="当前批次 ID")
    action: str = Field(default="answer", pattern="^(answer|skip|cancel)$")
    user_comment: str = Field(default="", description="用户补充说明")


@router.post("/clarify")
async def clarify_action(
    request: ClarifyRequest,
    user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """回答澄清问题，恢复 Agentic Loop。"""
    from app.engine.harness.executor.loop_state import load_loop_state, cleanup_loop_state
    from app.agents.registry import AgentRegistry
    from app.tools.context_vars import current_db_session
    from app.agents.clarification_graph import compile_clarification_result, collect_clarify_fields
    from app.engine.harness.executor.loop_state import check_clarification_timeout, mark_loop_state_expired, _get_lock

    # §5.2 v2.2 并发文件锁：防止并发 /clarify 请求导致 lost update
    _file_lock = _get_lock(request.loop_state_path)
    _file_lock.acquire()

    try:
        state = load_loop_state(request.loop_state_path)
    except FileNotFoundError:
        _file_lock.release()
        raise HTTPException(status_code=404, detail="循环状态不存在或已过期")

    # §5.3 v2.2 超时检查：expired 后拒绝提交
    if state.get("_clarification_expired"):
        _file_lock.release()
        raise HTTPException(status_code=410, detail="澄清已超时，按默认设置继续")

    # §5.3 超时自动 skip
    _timeout_status = check_clarification_timeout(state)
    if _timeout_status == "expired":
        mark_loop_state_expired(request.loop_state_path)
        _file_lock.release()
        raise HTTPException(status_code=410, detail="澄清已超时，按默认设置继续")

    if request.action == "cancel":
        # §6.1 跳过全部：对每个未回答字段走降级链，编译 clarification_result 后 resume
        _pending = state.get("pending_clarification") or state.get("pending_skill_call", {})
        _skill_name = _pending.get("name", "")
        registry = AgentRegistry()
        harness = registry.build_harness("chat_agent")
        skill_map = {s.name: s for s in harness.skills}
        _skill = skill_map.get(_skill_name)
        # §2.5.2 ReAct 模式：收集所有创作类 Skill 的 clarify_meta（与 Step 0 一致）
        _CLARIFY_TRIGGER_NODE_TYPES_CANCEL = {"produce", "create", "design", "generate", "copywrite", "card_design"}
        _clarify_skills_cancel = [
            s for s in harness.skills
            if getattr(s, "node_type", "") in _CLARIFY_TRIGGER_NODE_TYPES_CANCEL
            and getattr(s, "clarify_meta", None)
        ]
        if not _clarify_skills_cancel and _skill:
            _clarify_skills_cancel = [_skill]
        _fields = collect_clarify_fields(_clarify_skills_cancel, clarified_answers={}) if _clarify_skills_cancel else {}
        _model_settings = state.get("context_snapshot", {}).get("extra", {}).get("model_settings", {})
        _clarification_result = compile_clarification_result(
            all_answers={},
            fields=_fields,
            model_settings=_model_settings,
        )
        # 注入 clarification_result 到 context.extra 并 resume
        from app.engine.schemas import WorkflowContext
        ctx = WorkflowContext(
            workflow_id=state["context_snapshot"].get("workflow_id", ""),
            node_id="chat",
            user_id=user_id,
            account_id=state["context_snapshot"].get("account_id", ""),
        )
        saved_extra = state.get("context_snapshot", {}).get("extra", {})
        if isinstance(saved_extra, dict):
            ctx.extra.update(saved_extra)
        ctx.extra["clarification_result"] = _clarification_result

        executor = harness.executor
        if hasattr(executor, "max_iterations") and state.get("max_iterations"):
            executor.max_iterations = int(state["max_iterations"])
        if hasattr(executor, "max_iterations") and state.get("_awaiting_clarification"):
            executor.max_iterations = max(
                executor.max_iterations,
                int(state.get("max_iterations", executor.max_iterations)) + 1,
            )

        _cancel_session_id = state["context_snapshot"].get("workflow_id", "") or request.session_id
        async def _cancel_sse_emit(node_id: str, event_type: str, payload: dict) -> None:
            try:
                await sse_bus.publish(_cancel_session_id, event_type, payload)
            except Exception:
                pass
        from app.engine.harness.observer.observer import Observer
        harness.observer = Observer(emit_callback=_cancel_sse_emit)

        try:
            await chat_session.mark_clarification_resolved(request.session_id)
        except Exception:
            pass

        token = current_db_session.set(db)
        try:
            if state.get("pending_skill_call"):
                pending = state["pending_skill_call"]
                call = {
                    "name": pending.get("name", ""),
                    "arguments": pending.get("arguments", {}) or {},
                }
                if _clarification_result:
                    call["arguments"].update(_clarification_result)
                if call["name"]:
                    try:
                        result_obs, _ = await executor._execute_tool_call(  # noqa: SLF001
                            harness, ctx, skill_map, call, _approved=True
                        )
                    except Exception as e:
                        result_obs = f'[observation] {{"error": "tool execution failed: {e}"}}'
                    state["messages"].append({"role": "user", "content": f"[observation] {result_obs}"})

            output = await executor.execute(
                harness,
                {"topic": ""},
                ctx,
                resume_messages=state["messages"],
            )
        finally:
            current_db_session.reset(token)

        cleanup_loop_state(request.loop_state_path)
        _file_lock.release()

        if isinstance(output, dict) and output.get("_awaiting_clarification"):
            new_prompt = output.get("_clarification_prompt", "")
            new_skill = output.get("_clarification_skill", "")
            new_batches = output.get("_clarification_batches", [])
            new_state_path = output.get("_loop_state_path", "")
            return {
                "session_id": request.session_id,
                "status": "awaiting_clarification",
                "message": new_prompt or "需要进一步确认创作偏好",
                "clarification_prompt": new_prompt,
                "clarification_skill": new_skill,
                "clarification_batches": new_batches,
                "loop_state_path": new_state_path,
                "clarification_result": _clarification_result,
            }

        output_data = output if isinstance(output, dict) else {}
        final_message = _humanize_output(output_data.get("summary", ""), output_data)
        if not final_message:
            final_message = "操作已完成。"
        return {
            "session_id": request.session_id,
            "status": "completed",
            "message": final_message,
            "output": output,
            "clarification_result": _clarification_result,
        }

    # §5.1 步骤 5: action=skip → 本批所有未回答字段走降级链，继续步骤 3
    if request.action == "skip":
        # 不合并本批回答（用户跳过了），但保留之前批次的回答
        pass

    # 合并已有澄清结果
    _existing = state.get("clarified_answers", {})
    if request.action == "answer":
        _existing.update(request.answers)
    state["clarified_answers"] = _existing

    # 编译 clarification_result
    _pending = state.get("pending_clarification") or state.get("pending_skill_call", {})
    _skill_name = _pending.get("name", "")

    registry = AgentRegistry()
    harness = registry.build_harness("chat_agent")
    skill_map = {s.name: s for s in harness.skills}
    _skill = skill_map.get(_skill_name)
    # §2.5.2 ReAct 模式：收集所有创作类 Skill 的 clarify_meta（与 Step 0 一致）
    _CLARIFY_TRIGGER_NODE_TYPES = {"produce", "create", "design", "generate", "copywrite", "card_design"}
    _clarify_skills = [
        s for s in harness.skills
        if getattr(s, "node_type", "") in _CLARIFY_TRIGGER_NODE_TYPES
        and getattr(s, "clarify_meta", None)
    ]
    if not _clarify_skills and _skill:
        _clarify_skills = [_skill]
    _fields = collect_clarify_fields(_clarify_skills, clarified_answers=_existing) if _clarify_skills else {}
    _model_settings = state.get("context_snapshot", {}).get("extra", {}).get("model_settings", {})
    _clarification_result = compile_clarification_result(
        all_answers=_existing,
        fields=_fields,
        model_settings=_model_settings,
    )

    # Build user decision observation
    _answer_summary = ", ".join(f"{k}={v}" for k, v in request.answers.items()) if request.answers else "skipped"
    obs = f"[observation] 用户确认了创作偏好: {_answer_summary}"
    state["messages"].append({"role": "user", "content": obs})

    # Build new harness with resume_messages
    executor = harness.executor
    if hasattr(executor, "max_iterations") and state.get("max_iterations"):
        executor.max_iterations = int(state["max_iterations"])

    # Iteration 补偿（§2.8）：澄清恢复时补偿 1 次迭代，给创作留余量
    if hasattr(executor, "max_iterations") and state.get("_awaiting_clarification"):
        executor.max_iterations = max(
            executor.max_iterations,
            int(state.get("max_iterations", executor.max_iterations)) + 1,
        )

    _clarify_session_id = state["context_snapshot"].get("workflow_id", "") or request.session_id
    async def _clarify_sse_emit(node_id: str, event_type: str, payload: dict) -> None:
        try:
            await sse_bus.publish(_clarify_session_id, event_type, payload)
        except Exception:
            pass

    from app.engine.harness.observer.observer import Observer
    harness.observer = Observer(emit_callback=_clarify_sse_emit)

    # §3.2 推送 agent_clarification_ack 事件
    try:
        await sse_bus.publish(
            _clarify_session_id,
            "agent_clarification_ack",
            {"batch_id": request.batch_id, "action": request.action},
        )
    except Exception:
        pass

    # 把该会话中所有旧的 awaiting_clarification 消息标记为 completed，
    # 防止刷新页面时旧澄清卡片重新出现
    try:
        await chat_session.mark_clarification_resolved(request.session_id)
    except Exception:
        pass

    # Set db session context
    token = current_db_session.set(db)
    try:
        from app.engine.schemas import WorkflowContext
        ctx = WorkflowContext(
            workflow_id=state["context_snapshot"].get("workflow_id", ""),
            node_id="chat",
            user_id=user_id,
            account_id=state["context_snapshot"].get("account_id", ""),
        )
        # 恢复原循环快照里的 extra
        saved_extra = state.get("context_snapshot", {}).get("extra", {})
        if isinstance(saved_extra, dict):
            ctx.extra.update(saved_extra)
        # 注入 clarification_result 到 context.extra
        ctx.extra["clarification_result"] = _clarification_result

        # 批准 → 立即执行被澄清的工具并把结果注入对话
        if state.get("pending_skill_call"):
            pending = state["pending_skill_call"]
            call = {
                "name": pending.get("name", ""),
                "arguments": pending.get("arguments", {}) or {},
            }
            # 把 clarification_result 合并进 arguments
            if _clarification_result:
                call["arguments"].update(_clarification_result)
            if call["name"]:
                try:
                    result_obs, _new_conf = await executor._execute_tool_call(  # noqa: SLF001
                        harness, ctx, skill_map, call, _approved=True
                    )
                except Exception as e:
                    result_obs = f'[observation] {{"error": "tool execution failed: {e}"}}'
                state["messages"].append({"role": "user", "content": f"[observation] {result_obs}"})

        output = await executor.execute(
            harness,
            {"topic": ""},
            ctx,
            resume_messages=state["messages"],
        )
    finally:
        current_db_session.reset(token)

    cleanup_loop_state(request.loop_state_path)
    _file_lock.release()

    # 续跑再次触发澄清/确认
    if isinstance(output, dict) and output.get("_awaiting_clarification"):
        new_prompt = output.get("_clarification_prompt", "")
        new_skill = output.get("_clarification_skill", "")
        new_batches = output.get("_clarification_batches", [])
        new_state_path = output.get("_loop_state_path", "")
        await chat_session.add_message(
            request.session_id, "assistant",
            new_prompt or "需要进一步确认创作偏好",
            {
                "workflow_status": "awaiting_clarification",
                "source": "react_loop",
                "loop_state_path": new_state_path,
                "clarification_prompt": new_prompt,
                "clarification_skill": new_skill,
                "clarification_batches": new_batches,
            },
        )
        return {
            "session_id": request.session_id,
            "status": "awaiting_clarification",
            "message": new_prompt or "需要进一步确认创作偏好",
            "clarification_prompt": new_prompt,
            "clarification_skill": new_skill,
            "clarification_batches": new_batches,
            "loop_state_path": new_state_path,
            "clarification_result": _clarification_result,
        }

    if isinstance(output, dict) and output.get("_awaiting_confirmation"):
        new_prompt = output.get("_confirmation_prompt", "")
        new_skill = output.get("_confirmation_skill", "")
        new_state_path = output.get("_loop_state_path", "")
        await chat_session.add_message(
            request.session_id, "assistant",
            new_prompt or "需要进一步确认操作",
            {
                "workflow_status": "awaiting_confirmation",
                "source": "react_loop",
                "loop_state_path": new_state_path,
                "confirmation_prompt": new_prompt,
                "confirmation_skill": new_skill,
            },
        )
        return {
            "session_id": request.session_id,
            "status": "awaiting_confirmation",
            "message": new_prompt or "需要进一步确认操作",
            "confirmation_prompt": new_prompt,
            "confirmation_skill": new_skill,
            "loop_state_path": new_state_path,
            "clarification_result": _clarification_result,
        }

    # 正常完成
    output_data = output if isinstance(output, dict) else {}
    final_message = _humanize_output(output_data.get("summary", ""), output_data)
    if not final_message:
        final_message = "操作已完成。"
    await chat_session.add_message(
        request.session_id, "assistant", final_message,
        {"workflow_status": "completed", "source": "react_loop"},
    )

    return {
        "session_id": request.session_id,
        "status": "completed",
        "message": final_message,
        "output": output,
        "clarification_result": _clarification_result,
    }


@router.post("/llm-circuit/reset")
async def reset_llm_circuit(
    user_id: str = Depends(get_current_user),
) -> dict:
    """重置 LLM 熔断器（用户充值/更换 API Key 后调用）。"""
    from app.engine.governance.llm_circuit import get_llm_circuit
    circuit = get_llm_circuit()
    old_state = circuit.to_dict()
    circuit.reset()
    logger.info(f"[chat_agent] LLM circuit manually reset by user={user_id}, old_state={old_state}")
    return {"success": True, "message": "LLM 熔断器已重置", "previous_state": old_state}


@router.get("/llm-circuit/status")
async def get_llm_circuit_status(
    user_id: str = Depends(get_current_user),
) -> dict:
    """查询 LLM 熔断器状态。"""
    from app.engine.governance.llm_circuit import get_llm_circuit
    return get_llm_circuit().to_dict()


@router.post("/llm-circuit/_internal-reset")
async def internal_reset_llm_circuit(request: Request) -> dict:
    """内部重置端点（免鉴权，仅限 localhost 调用）。用于脚本/运维重置熔断器。"""
    client_host = request.client.host if request.client else ""
    if client_host not in ("127.0.0.1", "::1", "localhost"):
        raise HTTPException(status_code=403, detail="仅限本地调用")
    from app.engine.governance.llm_circuit import get_llm_circuit
    circuit = get_llm_circuit()
    old_state = circuit.to_dict()
    circuit.reset()
    logger.info(f"[chat_agent] LLM circuit internal reset, old_state={old_state}")
    return {"success": True, "message": "LLM 熔断器已重置", "previous_state": old_state}


@router.post("/llm-circuit/probe")
async def probe_llm_circuit(
    user_id: str = Depends(get_current_user),
) -> dict:
    """探测 LLM API 可用性。如果 API 恢复（如充值后），自动重置熔断器。

    前端在发送消息前调用此端点：
    - 熔断器 CLOSED → 直接返回 ok
    - 熔断器 OPEN/HALF_OPEN → 发一个极轻量 API 调用
      - 成功 → 自动重置为 CLOSED → 返回 {recovered: true}
      - 失败 → 保持 OPEN → 返回 {recovered: false, detail: ...}
    """
    from app.engine.governance.llm_circuit import get_llm_circuit
    circuit = get_llm_circuit()
    result = await circuit.probe_and_recover()
    logger.info(f"[chat_agent] LLM circuit probe: {result}")
    return result