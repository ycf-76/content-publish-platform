"""
Crab Companion Plugin
螃蟹伴侣插件 - 前端交互组件，后端仅提供配置管理
"""

import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)


class CrabCompanionPlugin:
    """螃蟹伴侣插件入口类"""

    PLUGIN_ID = "crab-companion"

    def __init__(self):
        self.config = {
            "crab_size": 48,
            "speech_enabled": True,
        }
        logger.info(f"[{self.PLUGIN_ID}] plugin loaded")

    def get_config(self) -> Dict[str, Any]:
        return self.config.copy()

    def update_config(self, new_config: Dict[str, Any]) -> None:
        self.config.update(new_config)
        logger.info(f"[{self.PLUGIN_ID}] config updated: {new_config}")

    def on_enable(self) -> None:
        logger.info(f"[{self.PLUGIN_ID}] enabled")

    def on_disable(self) -> None:
        logger.info(f"[{self.PLUGIN_ID}] disabled")