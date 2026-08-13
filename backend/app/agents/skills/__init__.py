"""Skills subpackage.

Exports: Skill (base) and all concrete skills (search/analyze/image_gen/publish).
"""

from app.agents.skills.base import Skill

__all__ = ["Skill"]
