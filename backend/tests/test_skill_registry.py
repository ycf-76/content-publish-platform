"""Tests for SkillRegistry — skill registration, lookup, and discovery.

Covers:
1. Register a valid Skill subclass
2. Register rejects non-Skill types
3. Register rejects Skill without node_type or name
4. Get skill by (node_type, skill_name)
5. Get default skill for a node_type
6. List skills by node_type
7. Override existing skill (hot-update scenario)
8. Singleton pattern
"""

import pytest

from app.tools.base import Skill
from app.tools.registry import SkillRegistry


class _DummySearchSkill(Skill):
    node_type = "search"
    name = "dummy_search"
    display_name = "Dummy Search"
    description = "A dummy search skill for testing"

    async def execute(self, inputs):
        return {"results": []}


class _DummyCopywriteSkill(Skill):
    node_type = "copywrite"
    name = "dummy_copywrite"
    display_name = "Dummy Copywrite"
    description = "A dummy copywrite skill for testing"

    async def execute(self, inputs):
        return {"title": "test", "content": "test", "tags": []}


class _AnotherSearchSkill(Skill):
    node_type = "search"
    name = "another_search"
    display_name = "Another Search"
    description = "Another search skill"

    async def execute(self, inputs):
        return {"results": []}


class _NoNodeTypeSkill(Skill):
    node_type = ""
    name = "orphan"
    display_name = "Orphan"
    description = "Missing node_type"

    async def execute(self, inputs):
        return {}


class _NoNameSkill(Skill):
    node_type = "search"
    name = ""
    display_name = "No Name"
    description = "Missing name"

    async def execute(self, inputs):
        return {}


@pytest.fixture
def registry():
    return SkillRegistry()


class TestSkillRegistryRegister:
    def test_register_valid_skill(self, registry):
        registry.register(_DummySearchSkill)
        skill = registry.get("search", "dummy_search")
        assert skill is _DummySearchSkill

    def test_register_rejects_non_skill_type(self, registry):
        with pytest.raises(TypeError, match="Skill subclass"):
            registry.register(str)

    def test_register_rejects_missing_node_type(self, registry):
        with pytest.raises(ValueError, match="non-empty"):
            registry.register(_NoNodeTypeSkill)

    def test_register_rejects_missing_name(self, registry):
        with pytest.raises(ValueError, match="non-empty"):
            registry.register(_NoNameSkill)

    def test_register_as_decorator(self, registry):
        @registry.register
        class _DecoratedSkill(Skill):
            node_type = "audit"
            name = "decorated_audit"
            display_name = "Decorated Audit"
            description = "Registered via decorator"

            async def execute(self, inputs):
                return {}

        skill = registry.get("audit", "decorated_audit")
        assert skill is not None
        assert skill.name == "decorated_audit"

    def test_register_override_existing(self, registry):
        registry.register(_DummySearchSkill)

        class _UpdatedSearchSkill(Skill):
            node_type = "search"
            name = "dummy_search"
            display_name = "Updated Search"
            description = "Updated version"

            async def execute(self, inputs):
                return {"results": [], "extra": True}

        registry.register(_UpdatedSearchSkill)
        skill = registry.get("search", "dummy_search")
        assert skill is _UpdatedSearchSkill
        assert skill.display_name == "Updated Search"


class TestSkillRegistryGet:
    def test_get_existing_skill(self, registry):
        registry.register(_DummySearchSkill)
        assert registry.get("search", "dummy_search") is _DummySearchSkill

    def test_get_nonexistent_skill_returns_none(self, registry):
        assert registry.get("search", "nonexistent") is None

    def test_get_nonexistent_node_type_returns_none(self, registry):
        assert registry.get("nonexistent_type", "some_skill") is None


class TestSkillRegistryGetDefault:
    def test_get_default_returns_first_registered(self, registry):
        registry.register(_DummySearchSkill)
        registry.register(_AnotherSearchSkill)
        default = registry.get_default("search")
        assert default is not None
        assert default.node_type == "search"

    def test_get_default_empty_node_type_returns_none(self, registry):
        assert registry.get_default("nonexistent") is None


class TestSkillRegistryList:
    def test_list_by_node(self, registry):
        registry.register(_DummySearchSkill)
        registry.register(_AnotherSearchSkill)
        skills = registry.list_by_node("search")
        assert len(skills) == 2
        names = [s["name"] for s in skills]
        assert "dummy_search" in names
        assert "another_search" in names

    def test_list_by_node_empty(self, registry):
        skills = registry.list_by_node("nonexistent")
        assert skills == []

    def test_list_all(self, registry):
        registry.register(_DummySearchSkill)
        registry.register(_DummyCopywriteSkill)
        all_skills = registry.list_all()
        assert "search" in all_skills
        assert "copywrite" in all_skills


class TestSkillRegistryFind:
    def test_find_by_name(self, registry):
        registry.register(_DummySearchSkill)
        results = registry.find_by_name("dummy_search")
        assert len(results) == 1
        assert results[0] is _DummySearchSkill

    def test_find_by_name_no_match(self, registry):
        results = registry.find_by_name("nonexistent")
        assert results == []


class TestSkillRegistrySingleton:
    def test_instance_returns_same_object(self):
        r1 = SkillRegistry.instance()
        r2 = SkillRegistry.instance()
        assert r1 is r2