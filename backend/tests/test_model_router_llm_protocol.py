import asyncio

from app.engine.schemas import LLMProtocol
from app.core.sandbox.model_router import ChatResponse, ModelRouter


def _router_with_stubbed_route():
    router = ModelRouter()

    async def fake_route(request):
        return ChatResponse.ok(
            content="hello",
            tokens_used=10,
            model_used="fake-model",
            provider_used=None,
        )

    router.route = fake_route
    return router


def test_model_router_conforms_to_llm_protocol():
    assert isinstance(ModelRouter(), LLMProtocol)


def test_model_router_exposes_model_name():
    router = ModelRouter()
    assert hasattr(router, "model_name")
    assert router.model_name == "model-router"


def test_model_router_chat_returns_protocol_shape():
    async def run():
        router = _router_with_stubbed_route()
        result = await router.chat([{"role": "user", "content": "hi"}])
        assert result["content"] == "hello"
        assert result["reasoning_content"] is None
        assert result["token_usage"] == 10

    asyncio.run(run())


def test_model_router_stream_chat_yields_protocol_chunk():
    async def run():
        router = _router_with_stubbed_route()
        chunks = []
        async for chunk in router.stream_chat([{"role": "user", "content": "hi"}]):
            chunks.append(chunk)
        assert len(chunks) == 1
        assert chunks[0]["content"] == "hello"
        assert chunks[0]["is_final"] is True
        assert chunks[0]["token_usage"] == 10

    asyncio.run(run())
