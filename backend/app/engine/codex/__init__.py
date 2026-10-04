"""Codex sub-package: lightweight ReAct loop + thin primitives.

Re-exports from sub-modules for backward compatibility:
    from app.engine.codex import CodexSession, Primitive, ...
"""

from app.engine.codex.session import CodexSession, build_codex_session
from app.engine.codex.prompt import build_tool_descriptions, get_codex_system_prompt, CODEX_SYSTEM_PROMPT_TEMPLATE
from app.engine.codex.primitives import (
    Primitive,
    ALL_PRIMITIVES,
    PRIMITIVES_BY_NAME,
    FileReadPrimitive,
    FileWritePrimitive,
    FileEditPrimitive,
    BashPrimitive,
    GlobPrimitive,
    GrepPrimitive,
    XhsSearchPrimitive,
    ImageGenPrimitive,
    ImageReadPrimitive,
    ImageAnalyzePrimitive,
    LLMGeneratePrimitive,
    ViralScorePrimitive,
    ContentCheckPrimitive,
)

__all__ = [
    "CodexSession",
    "build_codex_session",
    "build_tool_descriptions",
    "get_codex_system_prompt",
    "CODEX_SYSTEM_PROMPT_TEMPLATE",
    "Primitive",
    "ALL_PRIMITIVES",
    "PRIMITIVES_BY_NAME",
    "FileReadPrimitive",
    "FileWritePrimitive",
    "FileEditPrimitive",
    "BashPrimitive",
    "GlobPrimitive",
    "GrepPrimitive",
    "XhsSearchPrimitive",
    "ImageGenPrimitive",
    "ImageReadPrimitive",
    "ImageAnalyzePrimitive",
    "LLMGeneratePrimitive",
    "ViralScorePrimitive",
    "ContentCheckPrimitive",
]