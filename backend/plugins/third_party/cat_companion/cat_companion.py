"""
Cat Companion Plugin
小猫伴侣插件 - 前端交互组件，后端仅提供配置管理
"""

import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)


class CatCompanionPlugin:
    """小猫伴侣插件入口类"""

    PLUGIN_ID = "cat-companion"

    def __init__(self):
        self.config = {
            "cat_size": 48,
            "purr_enabled": True,
            "laziness": 0.7,
        }
        logger.info(f"[{self.PLUGIN_ID}] plugin loaded")

    def get_config(self) -> Dict[str, Any]:
        return self.config.copy()

    def update_config(self, new_config: Dict[str, Any]) -> None:
        self.config.update(new_config)
        logger.info(f"[{self.PLUGIN_ID}] config updated: {new_config}")

    def on_enable(self) -> None:
        logger.info(f"[{self.PLUGIN_ID}] enabled - meow!")

    def on_disable(self) -> None:
        logger.info(f"[{self.PLUGIN_ID}] disabled - zzz...")