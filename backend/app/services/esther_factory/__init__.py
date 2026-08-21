"""Esther Template Factory — LLM 驱动的视觉模板生产工厂。

核心理念：
- esther-design-system 是知识库，不是代码库
- 工厂负责组装上下文 → 调 LLM 生产 Jinja2 模板 → 质检 → 存入模板库
- 消费者拿到模板包后，用 Jinja2 填数据渲染，不再依赖工厂和 LLM

产出物（Template Package）：
  templates/<template_id>/
    ├── schema.json     # 模板需要什么字段
    ├── template.html   # Jinja2 模板
    └── meta.json       # 场景/组件/品牌信息
"""

from .engine import EstherFactory

factory = EstherFactory()

__all__ = ["factory", "EstherFactory"]