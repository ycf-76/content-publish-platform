"""Codex-style thin primitives: one function, one input, one output.

Each primitive wraps an existing Skill or direct API call into a minimal,
composable unit that the CodexSession's ReAct loop can dispatch.
No prompt templates, no fallback logic, no orchestration — just raw capability.

Three domains:
  Domain 1 — File ops (Codex-native): read/write/edit/bash/glob/grep
  Domain 2 — Platform API (XHS-specific): search/publish/image_gen/image_analyze
  Domain 3 — LLM reasoning (universal): llm_generate
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any

from app.engine.schemas import Permission

logger = logging.getLogger(__name__)


class Primitive(ABC):
    """Thin primitive base class.

    Unlike Skill, a Primitive:
    - Has no prompt template, no fallback, no internal orchestration
    - Does one thing and returns a dict
    - Is composable: the LLM decides which primitives to call in what order
    """

    name: str = ""
    description: str = ""
    required_permissions: list[Permission] = []

    @abstractmethod
    async def execute(self, **kwargs: Any) -> dict[str, Any]:
        raise NotImplementedError

    def info(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "required_permissions": [p.value for p in self.required_permissions],
        }


# ============================================================================
# Domain 1: File operations (Codex-native)
# ============================================================================


class FileReadPrimitive(Primitive):
    name = "file_read"
    description = (
        "读取文件内容。输入 path（相对于工作区根目录），"
        "可选 offset（起始行号）和 limit（最多读取行数）。"
        "返回文件内容、行数、文件大小。"
    )
    required_permissions = [Permission.FILE_READ]

    async def execute(self, **kwargs: Any) -> dict[str, Any]:
        from app.tools.file_tools import FileReadSkill
        return await FileReadSkill().execute(kwargs)


class FileWritePrimitive(Primitive):
    name = "file_write"
    description = (
        "写入文件（原子写入，不会写到一半崩溃）。"
        "输入 path 和 content。返回写入结果。"
    )
    required_permissions = [Permission.FILE_WRITE]

    async def execute(self, **kwargs: Any) -> dict[str, Any]:
        from app.tools.file_tools import FileWriteSkill
        return await FileWriteSkill().execute(kwargs)


class FileEditPrimitive(Primitive):
    name = "file_edit"
    description = (
        "精确替换文件中的文本片段。"
        "输入 path、old_string、new_string。"
        "old_string 必须在文件中唯一匹配，否则拒绝替换。"
    )
    required_permissions = [Permission.FILE_WRITE]

    async def execute(self, **kwargs: Any) -> dict[str, Any]:
        from app.tools.file_tools import FileEditSkill
        return await FileEditSkill().execute(kwargs)


class BashPrimitive(Primitive):
    name = "bash"
    description = (
        "执行 shell 命令。白名单限制：git/python/pip/node/npm/ls/cat/echo/rg/find/grep 等。"
        "输入 command，可选 cwd（工作目录）和 timeout（超时秒数，默认15）。"
        "返回 stdout、stderr、exit_code。"
    )
    required_permissions = [Permission.BASH_EXEC]

    async def execute(self, **kwargs: Any) -> dict[str, Any]:
        from app.tools.dev_tools import BashSkill
        return await BashSkill().execute(kwargs)


class GlobPrimitive(Primitive):
    name = "glob"
    description = (
        "按模式搜索文件路径。输入 pattern（如 **/*.py, src/**/*.tsx），"
        "可选 path（根目录）和 limit（最大匹配数）。返回文件路径列表。"
    )
    required_permissions = [Permission.FILE_READ]

    async def execute(self, **kwargs: Any) -> dict[str, Any]:
        from app.tools.dev_tools import GlobSkill
        return await GlobSkill().execute(kwargs)


class GrepPrimitive(Primitive):
    name = "grep"
    description = (
        "按正则搜索文件内容。输入 pattern（正则表达式）和 path（文件或目录），"
        "可选 glob（文件名过滤）、ignore_case、max_matches。返回匹配行。"
    )
    required_permissions = [Permission.FILE_READ]

    async def execute(self, **kwargs: Any) -> dict[str, Any]:
        from app.tools.dev_tools import GrepSkill
        return await GrepSkill().execute(kwargs)


# ============================================================================
# Domain 2: Platform API (XHS-specific)
# ============================================================================


class XhsSearchPrimitive(Primitive):
    name = "xhs_search"
    description = (
        "搜索小红书/各平台笔记。输入 keyword，可选 platform（xhs/bing/tavily/"
        "hackernews/reddit，空=默认平台）、limit（返回条数）、"
        "time_range（day/week/month/year/all）、min_interactions（最低互动量）。"
        "返回笔记列表（标题、点赞、评论等）。"
    )
    required_permissions = [Permission.XHS_SEARCH]

    async def execute(self, **kwargs: Any) -> dict[str, Any]:
        from app.tools.trending_search import TrendingSearchSkill
        return await TrendingSearchSkill().execute(kwargs)


class ImageGenPrimitive(Primitive):
    name = "image_gen"
    description = (
        "根据文字描述生成图片。输入 prompt（图片描述），"
        "可选 style（风格）、count（生成数量，默认3）。返回图片 URL 列表。"
    )
    required_permissions = [Permission.NET_HTTP_POST]

    async def execute(self, **kwargs: Any) -> dict[str, Any]:
        from app.tools.mcp.write_helper import generate_image_with_wanx
        prompt = kwargs.get("prompt", "")
        style = kwargs.get("style", "default")
        count = kwargs.get("count", 3)
        try:
            result = await generate_image_with_wanx(prompt=prompt, style=style, count=count)
            return {"ok": True, "images": result}
        except Exception as e:
            return {"ok": False, "error": str(e)}


class ImageReadPrimitive(Primitive):
    name = "image_read"
    description = (
        "读取本地图片文件并转为 Base64。输入 path（本地图片路径，如 "
        "C:/Users/xxx/photo.jpg 或 ./素材/咖啡.jpg），"
        "返回 base64 字符串和文件信息（大小、格式）。"
        "读取后可将 base64 传给 image_analyze 进行 AI 分析。"
    )
    required_permissions = [Permission.FILE_READ]

    _SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".tiff", ".svg"}

    async def execute(self, **kwargs: Any) -> dict[str, Any]:
        import base64
        from pathlib import Path as _Path

        path_str = kwargs.get("path", "")
        if not path_str:
            return {"ok": False, "error": "path is required"}

        p = _Path(path_str).expanduser().resolve()

        if not p.exists():
            return {"ok": False, "error": f"file not found: {p}"}

        if not p.is_file():
            return {"ok": False, "error": f"not a file: {p}"}

        ext = p.suffix.lower()
        if ext not in self._SUPPORTED_EXTENSIONS:
            return {
                "ok": False,
                "error": f"unsupported image format: {ext}. supported: {sorted(self._SUPPORTED_EXTENSIONS)}",
            }

        max_size = 20 * 1024 * 1024  # 20MB
        file_size = p.stat().st_size
        if file_size > max_size:
            return {"ok": False, "error": f"file too large: {file_size} bytes (max 20MB)"}

        try:
            raw = p.read_bytes()
            b64 = base64.b64encode(raw).decode("ascii")
            mime_map = {
                ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
                ".png": "image/png", ".gif": "image/gif",
                ".bmp": "image/bmp", ".webp": "image/webp",
                ".tiff": "image/tiff", ".svg": "image/svg+xml",
            }
            mime = mime_map.get(ext, "image/jpeg")
            return {
                "ok": True,
                "base64": b64,
                "mime": mime,
                "data_url": f"data:{mime};base64,{b64}",
                "file_size": file_size,
                "file_name": p.name,
                "extension": ext,
                "width_height_note": "use image_analyze to get dimensions and content",
            }
        except Exception as e:
            logger.exception(f"[image_read] failed to read {p}")
            return {"ok": False, "error": str(e)}


class ImageAnalyzePrimitive(Primitive):
    name = "image_analyze"
    description = (
        "用视觉语言模型理解图片内容。支持两种输入方式：\n"
        "1. image_base64 — 直接传 Base64 编码的图片\n"
        "2. path — 传本地图片路径（如 C:/Users/xxx/photo.jpg），"
        "会自动读取并转为 Base64\n"
        "可选 question（提问，默认'描述这张图片'）。"
        "返回图片的标签、情绪、构图、色彩等分析结果。"
    )
    required_permissions = [Permission.FILE_READ]

    async def execute(self, **kwargs: Any) -> dict[str, Any]:
        import base64
        from pathlib import Path as _Path

        image_base64 = kwargs.get("image_base64", "")
        path_str = kwargs.get("path", "")
        question = kwargs.get("question", "描述这张图片的内容，包括主体、场景、色彩、构图、情绪")

        if not image_base64 and not path_str:
            return {"ok": False, "error": "either image_base64 or path is required"}

        if path_str and not image_base64:
            p = _Path(path_str).expanduser().resolve()
            if not p.exists():
                return {"ok": False, "error": f"file not found: {p}"}
            supported = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".tiff"}
            if p.suffix.lower() not in supported:
                return {"ok": False, "error": f"unsupported format: {p.suffix}"}
            try:
                raw = p.read_bytes()
                image_base64 = base64.b64encode(raw).decode("ascii")
            except Exception as e:
                return {"ok": False, "error": f"failed to read image: {e}"}

        try:
            from app.adapters.qwen_vl import QwenVLAdapter
            from app.config import get_settings

            settings = get_settings()
            api_key = settings.dashscope_api_key
            if not api_key:
                return {"ok": False, "error": "DASHSCOPE_API_KEY not configured"}

            adapter = QwenVLAdapter(api_key=api_key, model=settings.qwen_vl_model)

            data_url = f"data:image/jpeg;base64,{image_base64}"
            messages = [
                {
                    "role": "user",
                    "content": [
                        {"image": data_url},
                        {"text": question},
                    ],
                },
            ]

            result = await adapter.chat(messages)
            content = result.get("content", "")

            return {
                "ok": True,
                "analysis": content,
                "question": question,
                "token_usage": result.get("token_usage", 0),
            }
        except Exception as e:
            logger.exception("[image_analyze] failed")
            err_msg = str(e)
            if "No module named" in err_msg or "ImportError" in type(e).__name__:
                return {"ok": False, "error": f"dependency missing: {err_msg}"}
            return {"ok": False, "error": err_msg}


# ============================================================================
# Domain 3: LLM reasoning (universal)
# ============================================================================


class LLMGeneratePrimitive(Primitive):
    name = "llm_generate"
    description = (
        "调用大语言模型生成文本。可用于任何文本任务："
        "文案撰写、内容分析、合规审核、翻译、规划、代码生成等。"
        "输入 prompt（你构造的提示词），可选 max_tokens（默认2000）、"
        "temperature（默认0.7）。返回生成的文本和 token 用量。"
    )
    required_permissions = []

    async def execute(self, **kwargs: Any) -> dict[str, Any]:
        from app.engine.factory import get_deepseek_llm

        prompt = kwargs.get("prompt", "")
        max_tokens = kwargs.get("max_tokens", 2000)
        temperature = kwargs.get("temperature", 0.7)

        if not prompt:
            return {"ok": False, "error": "prompt is required"}

        llm = get_deepseek_llm(temperature=temperature)
        if llm is None:
            return {"ok": False, "error": "LLM unavailable (no API key or adapter)"}

        try:
            result = await llm.chat(
                messages=[{"role": "user", "content": prompt}],
            )
            return {
                "ok": True,
                "text": result.get("content", ""),
                "reasoning_content": result.get("reasoning_content"),
                "token_usage": result.get("token_usage", 0),
            }
        except Exception as e:
            logger.exception("[llm_generate] LLM call failed")
            return {"ok": False, "error": str(e)}


class ViralScorePrimitive(Primitive):
    name = "viral_score"
    description = (
        "对搜索结果做爆款因子评分（纯规则计算，0 LLM token 消耗）。"
        "输入 results（搜索结果列表）。返回带评分指标的结果和排序。"
    )
    required_permissions = []

    async def execute(self, **kwargs: Any) -> dict[str, Any]:
        from app.tools.viral_analyzer import analyze_viral

        results = kwargs.get("results", [])
        if not results:
            return {"ok": False, "error": "results is required and must be non-empty"}

        try:
            scored = analyze_viral(results)
            return {"ok": True, "results": scored}
        except Exception as e:
            logger.exception("[viral_score] analysis failed")
            return {"ok": False, "error": str(e)}


class ContentCheckPrimitive(Primitive):
    name = "content_check"
    description = (
        "内容合规检查（纯规则，0 LLM token 消耗）。"
        "输入 text（待检查文本）。返回是否通过和具体问题列表。"
    )
    required_permissions = []

    _SENSITIVE_PATTERNS: list[str] = [
        "包治百病",
        "根治",
        "特效药",
        "投资回报",
        "稳赚不赔",
        "年化收益",
        "包过",
        "代考",
    ]

    async def execute(self, **kwargs: Any) -> dict[str, Any]:
        text = kwargs.get("text", "")
        if not text:
            return {"ok": True, "passed": True, "issues": []}

        issues: list[dict[str, str]] = []
        for pattern in self._SENSITIVE_PATTERNS:
            if pattern in text:
                issues.append({
                    "type": "sensitive_word",
                    "pattern": pattern,
                    "severity": "high",
                })

        return {
            "ok": True,
            "passed": len(issues) == 0,
            "issues": issues,
        }


# ============================================================================
# All primitives registry
# ============================================================================

ALL_PRIMITIVES: list[Primitive] = [
    FileReadPrimitive(),
    FileWritePrimitive(),
    FileEditPrimitive(),
    BashPrimitive(),
    GlobPrimitive(),
    GrepPrimitive(),
    XhsSearchPrimitive(),
    ImageGenPrimitive(),
    ImageReadPrimitive(),
    ImageAnalyzePrimitive(),
    LLMGeneratePrimitive(),
    ViralScorePrimitive(),
    ContentCheckPrimitive(),
]

PRIMITIVES_BY_NAME: dict[str, Primitive] = {p.name: p for p in ALL_PRIMITIVES}