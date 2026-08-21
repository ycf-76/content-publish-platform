"""Skill abstract base class.

Corresponds to architecture doc Ch.5 (Layer C).
All concrete capabilities (search/analyze/image_gen/publish) inherit this.
Red line: skills layer must NOT import LangGraph or make flow decisions.

可插拔 Skill 架构（v2）：
- 每个节点（analyze/image_gen/copywrite/audit）对应一个 node_type
- 同一个 node_type 下可注册多个 Skill 实现（如 copywrite 节点下有「活泼少女」「知性优雅」等多个 Skill）
- 第三方 Skill 通过 backend/skills/ 目录扫描自动注册
- 节点运行时按 state.model_settings.skill_name 从 registry 加载对应 Skill
- 风格/温度/模型作为 Skill 构造参数注入，不再硬编码到 prompt 字符串
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Literal

from pydantic import BaseModel

from app.agents.core.schemas import Permission


class Skill(ABC):
    """Capability-layer base class.

    每个 Skill 包装一次具体的能力调用：
    - xhs_search: 小红书搜索（via MCP）
    - vl_analyze: Qwen-VL 图像理解
    - generate_image: 通义万相/即梦图片生成
    - xhs_publish: 小红书发布（via MCP）
    - analyze: 选题分析（viral_analyzer + LLM 归因）
    - copywrite: 文案生成
    - audit: 合规审核

    可插拔元数据（子类通过类属性声明）：
    - node_type: 该 Skill 服务于哪个节点（"analyze"/"copywrite"/"image_gen"/"audit"）
    - name: Skill 唯一标识（如 "lively_girl_copywrite"），用于前端选择和后端路由
    - display_name: 前端展示名（如 "活泼少女风文案"）
    - description: Skill 描述（前端 tooltip 用）
    - default_config: 默认配置（温度/模型等），可被用户在右侧工作区覆盖

    子类通过 `required_permissions` 声明所需权限，由 Executor/Harness
    在 execute() 之前调用 permission_gate.require() 做门控。
    """

    # ===== 可插拔元数据（子类必须声明） =====
    node_type: str = ""
    name: str = ""
    display_name: str = ""
    description: str = ""
    default_config: dict[str, Any] = {}

    # ===== 通用元数据 =====
    input_schema: type[BaseModel] = BaseModel
    output_schema: type[BaseModel] = BaseModel
    execution_policy: Literal["direct", "mcp", "sandbox"] = "direct"
    required_permissions: list[Permission] = []

    @abstractmethod
    async def execute(self, inputs: dict[str, Any]) -> dict[str, Any]:
        """Execute the capability call, return structured result.

        约定：实现里不再做权限校验（由调用方统一在 execute 之前门控）。
        """
        raise NotImplementedError

    @classmethod
    def metadata(cls) -> dict[str, Any]:
        """返回 Skill 元数据（供前端渲染下拉框、tooltip）。"""
        return {
            "node_type": cls.node_type,
            "name": cls.name,
            "display_name": cls.display_name or cls.name,
            "description": cls.description,
            "default_config": cls.default_config,
        }