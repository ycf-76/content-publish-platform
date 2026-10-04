"""GithubPluginSkill: 让 LLM 能自动从 GitHub 安装插件。

当用户说"帮我安装 GitHub 上的 xxx 插件"或"安装 https://github.com/xxx"时，
LLM 会调用此 Skill 自动完成安装。
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field

from app.tools.base import Skill
from app.tools.registry import register

logger = logging.getLogger(__name__)


class GithubPluginInput(BaseModel):
    """GitHub 插件安装输入"""
    
    repo_url: str = Field(
        ...,
        description="GitHub 仓库的完整 URL，如 https://github.com/username/plugin-repo"
    )
    branch: str = Field(
        default="main",
        description="要安装的分支名（默认 main）"
    )
    use_git_clone: bool = Field(
        default=False,
        description="是否使用 git clone 模式（需要系统已安装 Git），默认使用 ZIP 下载模式"
    )
    reason: str = Field(
        default="",
        description="用户要求安装此插件的原因（用于日志记录）"
    )


@register
class GithubPluginSkill(Skill):
    """从 GitHub 仓库自动安装插件到系统中。
    
    使用场景：
    - 用户说："帮我安装 GitHub 上的 xxx 插件"
    - 用户说："安装 https://github.com/user/repo 这个插件"
    - 用户需要某个功能，而该功能以插件形式存在于 GitHub
    
    支持两种安装模式：
    1. ZIP 下载（默认）：无需 Git，直接下载仓库 zip 包
    2. Git Clone：需要本地 Git，支持后续 git pull 更新
    """
    
    node_type = "utility"
    name = "install_github_plugin"
    description = (
        "从 GitHub 仓库安装插件到系统。"
        "输入 repo_url（必需）、branch（可选，默认 main）、use_git_clone（可选，默认 false）。"
        "当用户提到'安装插件'、'GitHub 插件'、'从 GitHub 安装'等关键词时使用。"
        "返回安装结果，包含 success、plugin_id、message 等信息。"
    )
    input_schema = GithubPluginInput

    async def execute(self, inputs: dict[str, Any]) -> dict[str, Any]:
        """执行 GitHub 插件安装"""
        
        try:
            in_ = GithubPluginInput.model_validate(inputs)
        except Exception as e:
            return {
                "ok": False,
                "error": f"输入参数验证失败: {e}",
                "installed": False,
            }
        
        _context = inputs.get("_context", {})
        user_id = getattr(_context, "user_id", "") if hasattr(_context, "user_id") else _context.get("user_id", "")
        
        logger.info(
            f"[github_plugin_skill] 用户 {user_id} 请求安装 GitHub 插件: "
            f"{in_.repo_url} (branch={in_.branch}, git_clone={in_.use_git_clone})"
        )
        
        try:
            from app.services.github_installer import get_github_installer
            
            installer = get_github_installer()
            
            # 执行安装
            result = await installer.install_from_github(
                repo_url=in_.repo_url,
                branch=in_.branch,
                use_git_clone=in_.use_git_clone,
            )
            
            if result.get("success"):
                # 安装成功后，尝试重新加载插件
                await self._reload_plugins()
                
                logger.info(
                    f"[github_plugin_skill] ✅ 插件安装成功: "
                    f"{result.get('plugin_name')} v{result.get('version')} "
                    f"(method={result.get('install_method')})"
                )
                
                return {
                    "ok": True,
                    "installed": True,
                    "plugin_id": result.get("plugin_id"),
                    "plugin_name": result.get("plugin_name"),
                    "version": result.get("version"),
                    "message": result.get("message", "安装成功"),
                    "install_method": result.get("install_method"),
                    "_action_taken": True,
                    "_response_template": (
                        f"✅ 已成功安装插件 **{result.get('plugin_name', 'Unknown')}** "
                        f"(v{result.get('version', '?')})！\n\n"
                        f"📦 **安装方式**: {result.get('install_method', 'unknown')}\n"
                        f"🆔 **插件 ID**: `{result.get('plugin_id', '')}`\n\n"
                        f"插件已自动加载到系统中，你现在可以使用它了！"
                        f"{'' if not in_.use_git_clone else '\n\n💡 由于使用了 Git Clone 模式，你可以随时通过「更新插件」功能获取最新版本。'}"
                    ),
                }
            else:
                # 安装失败
                logger.error(f"[github_plugin_skill] ❌ 插件安装失败: {result.get('message')}")
                
                return {
                    "ok": False,
                    "installed": False,
                    "error": result.get("message", "未知错误"),
                    "_response_template": (
                        f"❌ 插件安装失败\n\n"
                        f"**原因**: {result.get('message', '未知错误')}\n\n"
                        f"请检查：\n"
                        f"1. GitHub URL 是否正确（格式：https://github.com/user/repo）\n"
                        f"2. 仓库是否公开（暂不支持私有仓库）\n"
                        f"3. 仓库根目录是否有 `plugin.json` 文件\n"
                        f"4. 如果使用 Git Clone 模式，确认系统已安装 Git"
                    ),
                }
                
        except Exception as e:
            logger.exception(f"[github_plugin_skill] 安装过程异常: {e}")
            
            return {
                "ok": False,
                "installed": False,
                "error": str(e),
                "_response_template": (
                    f"❌ 安装过程中发生异常\n\n"
                    f"**错误信息**: {str(e)}\n\n"
                    f"这可能是网络问题或服务器内部错误，请稍后重试。"
                    f"如果问题持续存在，请联系管理员。"
                ),
            }

    async def _reload_plugins(self):
        """安装成功后重新加载插件系统"""
        try:
            from app.core.plugin_manager import get_global_plugin_manager
            
            pm = get_global_plugin_manager()
            if pm:
                await pm.discover_and_load_all()
                logger.info("[github_plugin_skill] 插件系统已重新加载")
        except Exception as e:
            logger.warning(f"[github_plugin_skill] 重新加载插件失败（非致命）: {e}")


# ==================== 意图识别辅助函数 ====================

def extract_github_url_from_message(message: str) -> str | None:
    """从用户消息中提取 GitHub URL
    
    支持的格式：
    - https://github.com/user/repo
    - https://www.github.com/user/repo
    - https://github.com/user/repo.git
    - github.com/user/repo（自动补全协议）
    """
    import re
    
    # 匹配完整 URL
    patterns = [
        r'https?://(?:www\.)?github\.com/[^/\s]+/[^/\s\.]+(?:\.git)?',
        r'github\.com/[^/\s]+/[^/\s\.]+(?:\.git)?',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, message)
        if match:
            url = match.group(0)
            # 补全协议
            if not url.startswith('http'):
                url = 'https://' + url
            # 移除 .git 后缀
            url = url.replace('.git', '')
            return url
    
    return None


def should_trigger_github_install(message: str) -> bool:
    """判断用户消息是否意图安装 GitHub 插件"""
    
    message_lower = message.lower()
    
    # 关键词匹配
    install_keywords = [
        '安装插件', 'install plugin', '安装 github',
        '从 github 安装', 'github plugin', 'clone 插件',
        '添加插件', '下载插件', '导入插件',
    ]
    
    has_keyword = any(kw in message_lower for kw in install_keywords)
    
    # 或者消息中包含 GitHub URL 且有安装相关词汇
    has_github_url = 'github.com' in message_lower
    has_install_intent = any(word in message_lower for word in ['安装', 'install', '添加', 'add', '下载', 'download'])
    
    return has_keyword or (has_github_url and has_install_intent)