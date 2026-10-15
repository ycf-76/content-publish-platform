"""Wire workflow-engine Ports with real implementations from this project.

Call once at app startup (e.g. in lifespan or main.py):

    from app.adapters.workflow_wiring import wire_workflow_engine
    wire_workflow_engine()
"""
from __future__ import annotations

import logging
from typing import Any
from collections.abc import AsyncIterator

from workflow_engine.container import get_container

log = logging.getLogger("app.adapters.workflow_wiring")


class _HostedEventBus:
    def __init__(self) -> None:
        from app.services.sse_bus import sse_bus
        self._bus = sse_bus

    async def publish(self, workflow_id: str, event: str, data: dict[str, Any] | None = None) -> None:
        await self._bus.publish(workflow_id, event, data)

    async def subscribe(self, workflow_id: str) -> AsyncIterator[str]:
        return self._bus.subscribe(workflow_id)

    def has_subscribers(self, workflow_id: str) -> bool:
        return self._bus.has_subscribers(workflow_id)


class _HostedImageStore:
    async def save_workflow_images(self, workflow_id: str, images: list[dict[str, Any]]) -> list[str]:
        from app.services.image_store import save_workflow_images
        return await save_workflow_images(workflow_id, images)

    async def read_workflow_images_as_base64(self, workflow_id: str) -> list[dict[str, Any]]:
        from app.services.image_store import read_workflow_images_as_base64
        return await read_workflow_images_as_base64(workflow_id)

    async def cache_cover_image(self, url: str, workflow_id: str) -> str | None:
        from app.services.image_store import cache_cover_image
        return await cache_cover_image(url, workflow_id)

    async def cache_detail_images(self, urls: list[str], workflow_id: str) -> list[str]:
        from app.services.image_store import cache_detail_images
        return await cache_detail_images(urls, workflow_id)


class _HostedPlatformAdapter:
    async def check_platform_limits(self, content: dict[str, Any], platform: str) -> dict[str, Any]:
        from app.services.platform_adapter import check_platform_limits
        return await check_platform_limits(content, platform)

    def adapt_tags(self, tags: list[str], platform: str) -> list[str]:
        from app.services.platform_adapter import adapt_tags
        return adapt_tags(tags, platform)


class _HostedPlatformPublisher:
    async def publish_to_platform(self, content: dict[str, Any], platform: str, **kw: Any) -> dict[str, Any]:
        from app.services.platform_publisher import publish_to_platform
        return await publish_to_platform(content, platform, **kw)


class _HostedConfig:
    def get_settings(self) -> Any:
        from app.config import get_settings
        return get_settings()


class _HostedDB:
    async def get_session(self):
        from app.db.session import AsyncSessionLocal
        return AsyncSessionLocal()


class _HostedWeChatEngine:
    def __init__(self) -> None:
        from app.rpa.wechat_bot_engine import get_wechat_engine
        self._get_engine = get_wechat_engine

    async def send_text(self, **kw: Any) -> Any:
        engine = self._get_engine()
        return await engine.send_text(**kw)

    async def send_file(self, **kw: Any) -> Any:
        engine = self._get_engine()
        return await engine.send_file(**kw)


class _HostedFeishuEngine:
    def __init__(self) -> None:
        from app.rpa.feishu_bot import get_feishu_engine
        self._get_engine = get_feishu_engine

    async def send_message(self, **kw: Any) -> Any:
        engine = self._get_engine()
        return await engine.send_message(**kw)


class _HostedPerformanceCollector:
    async def record_publication(self, **kw: Any) -> None:
        from app.services.performance_collector import record_publication
        return await record_publication(**kw)


class _HostedProfileService:
    async def get_profile_cached(self, user_id: str) -> dict[str, Any] | None:
        from app.services.profile_service import get_profile_cached
        return await get_profile_cached(user_id)


class _HostedLLMFactory:
    async def __call__(self, model: str, **kw: Any) -> Any:
        from app.adapters.llm_base import create_llm
        return await create_llm(model, **kw)


def wire_workflow_engine() -> None:
    """Wire all workflow-engine Ports with real implementations from this project.

    Must be called AFTER the host app has finished its own startup
    (db pools, config loaded, etc.).
    """
    c = get_container()

    c._event_bus = _HostedEventBus()
    c._image_store = _HostedImageStore()
    c._platform_adapter = _HostedPlatformAdapter()
    c._platform_publisher = _HostedPlatformPublisher()
    c._config = _HostedConfig()
    c._db = _HostedDB()
    c._wechat_engine = _HostedWeChatEngine()
    c._feishu_engine = _HostedFeishuEngine()
    c._performance_collector = _HostedPerformanceCollector()
    c._profile_service = _HostedProfileService()
    c._llm_factory = _HostedLLMFactory()

    c.register("FeishuClient", _lazy("app.adapters.feishu", "FeishuClient"))
    c.register("FeishuAPIError", _lazy("app.adapters.feishu", "FeishuAPIError"))
    c.register("current_workflow_id", _lazy("app.services.context", "current_workflow_id"))
    c.register("agent_memory", _lazy("app.services", "agent_memory"))
    c.register("harness_factory_mod", _lazy("app.engine", "factory"))
    c.register("TopicPoolItem", _lazy("app.db.models", "TopicPoolItem"))
    c.register("UserProfile", _lazy("app.api.schemas.profile", "UserProfile"))
    c.register("UserProfileSchema", _lazy("app.api.schemas.profile", "UserProfile"))
    c.register("LLMProtocol", _lazy("app.adapters.llm_base", "LLMProtocol"))
    c.register("BaseLLM", _lazy("app.adapters.llm_base", "BaseLLM"))
    c.register("build_artifact", _lazy("app.services.creative_artifact", "build_artifact"))
    c.register("save_artifact", _lazy("app.services.creative_artifact", "save_artifact"))
    c.register("TemplateRegistry", _lazy("app.templates.registry", "TemplateRegistry"))
    c.register("get_template_registry", _lazy("app.templates.registry", "get_template_registry"))
    c.register("catalog_prompt_section", _lazy("app.templates.component_catalog", "catalog_prompt_section"))
    c.register("run_quality_gate", _lazy("app.services.quality_gate", "run_quality_gate"))
    c.register("get_valid_user_access_token", _lazy("app.services.feishu_oauth", "get_valid_user_access_token"))
    c.register("get_github_installer", _lazy("app.services.github_installer", "get_github_installer"))
    c.register("get_global_plugin_manager", _lazy("app.core.plugin_manager", "get_global_plugin_manager"))
    c.register("get_workflow_service", _lazy("app.services.workflow", "get_workflow_service"))
    c.register("QwenVLAdapter", _lazy("app.adapters.qwen_vl", "QwenVLAdapter"))
    c.register("redis_client", _lazy("app.cache.redis", "redis_client"))
    c.register("get_model_router", _lazy("app.adapters.model_router", "get_model_router"))
    c.register("EVENT_DRAFT_PATCH", _lazy("app.services.sse_bus", "EVENT_DRAFT_PATCH"))
    c.register("chat_session", _lazy("app.services", "chat_session"))
    c.register("guard_or_die", _lazy("app.services.content_guard", "guard_or_die"))
    c.register("ContentGuardError", _lazy("app.services.content_guard", "ContentGuardError"))
    c.register("check_xhs", _lazy("app.services.wordcount", "check_xhs"))
    c.register("count", _lazy("app.services.wordcount", "count"))
    c.register("scan", _lazy("app.services.content_guard", "scan"))
    c.register("get_feishu_engine", _lazy("app.rpa.feishu_bot", "get_feishu_engine"))
    c.register("get_profile_cached", _lazy("app.services.profile_service", "get_profile_cached"))
    c.register("get_current_weights", _lazy("app.services.performance_collector", "get_current_weights"))

    log.info("Workflow engine wired with hosted implementations")


def _lazy(module_path: str, attr_name: str):
    """Create a lazy loader that imports on first call/attribute access."""
    import importlib
    _resolved = None

    class _Lazy:
        def __call__(self, *args, **kwargs):
            nonlocal _resolved
            if _resolved is None:
                mod = importlib.import_module(module_path)
                _resolved = getattr(mod, attr_name)
            return _resolved(*args, **kwargs)

        def __getattr__(self, name):
            nonlocal _resolved
            if _resolved is None:
                mod = importlib.import_module(module_path)
                _resolved = getattr(mod, attr_name)
            return getattr(_resolved, name)

    return _Lazy()
