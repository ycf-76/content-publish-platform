from app.adapters.llm_base import BaseLLM
from app.agents.registry import AgentRegistry


class _FakeSettings:
    def __init__(self, api_key: str = "sk-test"):
        self.deepseek_api_key = api_key
        self.deepseek_base_url = "https://api.deepseek.com"
        self.deepseek_model_v3 = "deepseek-chat"


def _patch_settings(monkeypatch):
    import app.config as config_mod

    monkeypatch.setattr(config_mod, "get_settings", lambda: _FakeSettings())


def test_registry_has_all_builtin_agents():
    registry = AgentRegistry()
    assert len(registry.list_agents()) == 10
    assert registry.get("search").llm_model == "deepseek-v3"
    assert registry.get("copywrite").llm_model == "deepseek-r1"


def test_build_harness_locks_specific_model(monkeypatch):
    _patch_settings(monkeypatch)
    registry = AgentRegistry()

    search_harness = registry.build_harness("search")
    assert isinstance(search_harness.llm, BaseLLM)
    assert search_harness.llm.model_name == "deepseek-chat"

    copywrite_harness = registry.build_harness("copywrite")
    assert copywrite_harness.llm.model_name == "deepseek-reasoner"


def test_build_harness_assembles_skills(monkeypatch):
    _patch_settings(monkeypatch)
    registry = AgentRegistry()

    search_harness = registry.build_harness("search")
    assert [skill.name for skill in search_harness.skills] == ["trending_search"]

    publish_harness = registry.build_harness("publish")
    assert [skill.name for skill in publish_harness.skills] == ["xhs_publish"]


def test_build_harness_explore_agent(monkeypatch):
    _patch_settings(monkeypatch)
    registry = AgentRegistry()

    assert registry.get("explore") is not None
    explore_harness = registry.build_harness("explore")
    assert [skill.name for skill in explore_harness.skills] == [
        "trending_search",
        "vl_analyze",
        "lively_girl",
    ]


def test_build_harness_has_prompt_template(monkeypatch):
    _patch_settings(monkeypatch)
    registry = AgentRegistry()

    analyze_harness = registry.build_harness("analyze")
    assert "{topic}" in analyze_harness.prompt_template

    copywrite_harness = registry.build_harness("copywrite")
    assert "{topic}" in copywrite_harness.prompt_template
