import asyncio

from app.agents.nodes.search import _execute_search_with_recovery


class _MockSkill:
    def __init__(self, results_by_call):
        self._results = list(results_by_call)
        self.calls = []

    async def execute(self, inputs):
        self.calls.append(inputs.get("keyword"))
        idx = min(len(self.calls) - 1, len(self._results) - 1)
        return self._results[idx]


def test_search_recovery_broadens_on_empty(monkeypatch):
    import app.agents.harnesses.factory as factory_mod

    monkeypatch.setattr(factory_mod, "_make_observer", lambda wf: None)

    skill = _MockSkill([
        {"count": 0, "results": []},
        {"count": 1, "results": [{"title": "found"}]},
    ])

    async def run():
        return await _execute_search_with_recovery(
            "wf", "search", skill, {"keyword": "AI教育", "limit": 10}, 60.0
        )

    output = asyncio.run(run())
    assert output.get("count") == 1
    assert len(skill.calls) == 2


def test_search_recovery_exhausted_returns_empty(monkeypatch):
    import app.agents.harnesses.factory as factory_mod

    monkeypatch.setattr(factory_mod, "_make_observer", lambda wf: None)

    skill = _MockSkill([
        {"count": 0, "results": []},
        {"count": 0, "results": []},
    ])

    async def run():
        return await _execute_search_with_recovery(
            "wf", "search", skill, {"keyword": "AI教育", "limit": 10}, 60.0
        )

    output = asyncio.run(run())
    assert output.get("count") == 0
    assert output.get("_error_type") == "no_results"
