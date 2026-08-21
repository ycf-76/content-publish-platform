from app.adapters.llm_base import BaseLLM
from app.core.sandbox.model_router import ModelRouter


class _FakeSettings:
    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.deepseek.com",
        model_v3: str = "deepseek-chat",
    ):
        self.deepseek_api_key = api_key
        self.deepseek_base_url = base_url
        self.deepseek_model_v3 = model_v3


def _patch_settings(monkeypatch, settings: _FakeSettings):
    import app.config as config_mod

    monkeypatch.setattr(config_mod, "get_settings", lambda: settings)


def test_resolve_llm_returns_none_without_api_key(monkeypatch):
    _patch_settings(monkeypatch, _FakeSettings(api_key=""))
    router = ModelRouter()
    assert router.resolve_llm() is None


def test_resolve_llm_returns_base_llm_with_api_key(monkeypatch):
    _patch_settings(monkeypatch, _FakeSettings(api_key="sk-test"))
    router = ModelRouter()
    llm = router.resolve_llm()
    assert isinstance(llm, BaseLLM)
    assert llm.model_name == "deepseek-chat"


def test_resolve_llm_respects_model_and_temperature(monkeypatch):
    _patch_settings(monkeypatch, _FakeSettings(api_key="sk-test"))
    router = ModelRouter()
    llm = router.resolve_llm(model="deepseek-reasoner", temperature=0.2)
    assert llm.model_name == "deepseek-reasoner"
