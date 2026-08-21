"""fish-plugin 后端入口（UI 主题插件）。

平台规范要点：
- category=ui_theme，对应基类 BasePlugin；同时实现示例 C 风格的
  get_config / update_config / on_enable / on_disable，兼容两种加载方式
- UI 主题插件后端只负责配置管理与生命周期，不做任何渲染
- 前端组件 frontend/FishWidget.vue 需手动集成到前端代码（见文件头注释）
"""

import logging
from typing import Any, Dict, Optional

from app.core.base_interfaces import BasePlugin, PluginContext

logger = logging.getLogger(__name__)

# 配置边界，与 plugin.json 的 config_schema 保持一致
_SIZE_RANGE = (48, 200)
_SPEED_RANGE = (0.5, 2.0)
_PLACEMENTS = ("left", "right")

_DEFAULT_CONFIG: Dict[str, Any] = {
    "size": 96,            # 鱼的宽度 px
    "speed": 1.0,          # 动画速度倍率
    "bubble": True,        # 是否显示气泡
    "placement": "right",  # 鱼在输入框的哪一侧
}


def _sanitize_config(raw: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """清洗配置：类型或边界不合法的项回退默认值，保证传给前端的数据始终可用。

    注意 isinstance(True, int) 为 True，数值字段需额外排除布尔型。
    """
    clean = dict(_DEFAULT_CONFIG)
    if not isinstance(raw, dict):
        return clean

    size = raw.get("size")
    if isinstance(size, (int, float)) and not isinstance(size, bool):
        if _SIZE_RANGE[0] <= size <= _SIZE_RANGE[1]:
            clean["size"] = int(size)

    speed = raw.get("speed")
    if isinstance(speed, (int, float)) and not isinstance(speed, bool):
        if _SPEED_RANGE[0] <= speed <= _SPEED_RANGE[1]:
            clean["speed"] = round(float(speed), 2)

    if isinstance(raw.get("bubble"), bool):
        clean["bubble"] = raw["bubble"]

    if raw.get("placement") in _PLACEMENTS:
        clean["placement"] = raw["placement"]

    return clean


class FishPlugin(BasePlugin):
    """DeepSeek 动态鱼：输入框旁的蓝色小鱼装饰主题。"""

    def __init__(self) -> None:
        self.config: Dict[str, Any] = dict(_DEFAULT_CONFIG)

    # ---------- BasePlugin 必需属性 ----------

    @property
    def plugin_id(self) -> str:
        return "fish-plugin"

    @property
    def plugin_name(self) -> str:
        return "DeepSeek 动态鱼"

    # ---------- 完整生命周期（BasePlugin 协议） ----------

    async def setup(self, ctx: PluginContext) -> None:
        """安装/启用时调用：读取并清洗平台下发的配置。"""
        self.config = _sanitize_config(ctx.config)
        ctx.logger.info("[%s] setup 完成，config=%s", self.plugin_id, self.config)

    async def teardown(self) -> None:
        """卸载时调用：UI 主题无外部资源，仅记日志。"""
        logger.info("[%s] teardown", self.plugin_id)

    async def health_check(self) -> tuple[bool, str]:
        """UI 主题插件无外部依赖，恒为健康。"""
        return True, "运行正常"

    # ---------- 简单模式兼容接口（对应 SDK 示例 C 的加载方式） ----------

    def get_config(self) -> Dict[str, Any]:
        """返回当前配置副本，前端集成时由此读取 size/speed/bubble/placement。"""
        return self.config.copy()

    def update_config(self, new_config: Dict[str, Any]) -> None:
        """合并更新配置，统一走清洗，杜绝越界值入库。"""
        if isinstance(new_config, dict):
            self.config = _sanitize_config({**self.config, **new_config})

    def on_enable(self) -> None:
        logger.info("[%s] enabled", self.plugin_id)

    def on_disable(self) -> None:
        logger.info("[%s] disabled", self.plugin_id)
