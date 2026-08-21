from app.agents.skills.base import Skill
from app.agents.core.schemas import Permission


def test_skill_default_execution_policy_is_direct():
    assert Skill.execution_policy == "direct"


def test_skill_subclass_can_override_execution_policy():
    class SandboxSkill(Skill):
        node_type = "test"
        name = "sandbox_skill"
        execution_policy = "sandbox"

        async def execute(self, inputs: dict) -> dict:
            return {}

    assert SandboxSkill.execution_policy == "sandbox"