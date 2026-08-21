"""Template registry package.

Phase 1: builtin template manifests and query APIs.
Later phases: user templates, format plans, asset library.
"""

from app.templates.registry import TemplateRegistry, get_template_registry

__all__ = ["TemplateRegistry", "get_template_registry"]
