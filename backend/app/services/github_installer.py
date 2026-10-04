"""
GitHub Plugin Installer - 从 GitHub 仓库安装插件

支持两种模式：
1. Git Clone 模式（需要本地安装 git）
2. GitHub API 下载模式（无需 git，下载 zip 包）

使用方式：
    installer = GithubInstaller()
    result = await installer.install_from_github("https://github.com/user/plugin-repo")
"""

import asyncio
import logging
import re
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Any, Optional

import httpx

from app.core.plugin_types import PluginManifest

logger = logging.getLogger(__name__)

_GITHUB_API_BASE = "https://api.github.com"
_GITHUB_RAW_BASE = "https://raw.githubusercontent.com"

# 支持的 GitHub URL 格式
_GITHUB_URL_PATTERN = re.compile(
    r"https?://(?:www\.)?github\.com/([^/]+)/([^/]+?)(?:\.git)?/?$"
)


class GithubInstaller:
    """GitHub 插件安装器
    
    从 GitHub 仓库下载并安装到插件系统
    """

    def __init__(
        self,
        target_dir: Optional[Path] = None,
        github_token: Optional[str] = None,
    ):
        """
        初始化安装器
        
        Args:
            target_dir: 目标插件目录（默认为 plugins/third_party）
            github_token: GitHub Personal Access Token（可选，提升速率限制）
        """
        if target_dir is None:
            # 默认安装到 third_party 目录
            base_dir = Path(__file__).parent.parent.parent / "plugins"
            self.target_dir = base_dir / "third_party"
        else:
            self.target_dir = Path(target_dir)
        
        self.github_token = (github_token or "").strip()
        self._client: Optional[httpx.AsyncClient] = None
    
    async def _get_client(self) -> httpx.AsyncClient:
        """获取或创建 HTTP 客户端"""
        if self._client is None:
            headers = {
                "User-Agent": "multi-agent-xhs-platform/1.0",
                "Accept": "application/vnd.github+json",
            }
            if self.github_token:
                headers["Authorization"] = f"Bearer {self.github_token}"
            
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(60.0),
                headers=headers,
                follow_redirects=True,
            )
        return self._client
    
    async def close(self):
        """关闭 HTTP 客户端"""
        if self._client:
            await self._client.aclose()
            self._client = None
    
    async def install_from_github(
        self,
        repo_url: str,
        branch: str = "main",
        use_git_clone: bool = False,
    ) -> dict[str, Any]:
        """
        从 GitHub 仓库安装插件
        
        Args:
            repo_url: GitHub 仓库 URL（如 https://github.com/user/plugin-repo）
            branch: 分支名（默认 main）
            use_git_clone: 是否使用 git clone（需要本地安装 git）
        
        Returns:
            {
                "success": bool,
                "plugin_id": str | None,
                "plugin_name": str | None,
                "version": str | None,
                "message": str,
                "install_method": "git" | "zip" | "error"
            }
        """
        # 1. 解析并验证 URL
        owner, repo_name = self._parse_github_url(repo_url)
        if not owner or not repo_name:
            return {
                "success": False,
                "message": f"无效的 GitHub URL: {repo_url}",
                "install_method": "error",
            }
        
        logger.info(f"[github_installer] 开始安装: {owner}/{repo_name} (branch={branch})")
        
        # 2. 选择安装方法
        if use_git_clone and await self._check_git_available():
            return await self._install_via_git_clone(owner, repo_name, branch)
        else:
            return await self._install_via_zip_download(owner, repo_name, branch)
    
    def _parse_github_url(self, url: str) -> tuple[Optional[str], Optional[str]]:
        """解析 GitHub URL 为 (owner, repo_name)"""
        match = _GITHUB_URL_PATTERN.match(url.strip())
        if match:
            return match.group(1), match.group(2)
        return None, None
    
    async def _check_git_available(self) -> bool:
        """检查系统是否安装了 git"""
        try:
            proc = await asyncio.create_subprocess_exec(
                "git", "--version",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()
            return proc.returncode == 0
        except FileNotFoundError:
            return False
        except Exception as e:
            logger.warning(f"[github_installer] 检查 git 失败: {e}")
            return False
    
    async def _install_via_git_clone(
        self,
        owner: str,
        repo_name: str,
        branch: str,
    ) -> dict[str, Any]:
        """使用 git clone 安装插件"""
        plugin_id = f"{owner}__{repo_name}".lower().replace("-", "_")
        dest_path = self.target_dir / plugin_id
        
        try:
            # 如果已存在，先删除
            if dest_path.exists():
                shutil.rmtree(dest_path)
                logger.info(f"[github_installer] 删除旧版本: {dest_path}")
            
            # 执行 git clone（浅克隆，只取最新提交）
            cmd = [
                "git", "clone",
                "--depth", "1",          # 浅克隆，节省空间和时间
                "--single-branch",       # 只克隆指定分支
                "--branch", branch,
                f"https://github.com/{owner}/{repo_name}.git",
                str(dest_path),
            ]
            
            logger.info(f"[github_installer] 执行: {' '.join(cmd)}")
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()
            
            if proc.returncode != 0:
                error_msg = stderr.decode("utf-8", errors="replace").strip()
                logger.error(f"[github_installer] git clone 失败: {error_msg}")
                return {
                    "success": False,
                    "message": f"Git clone 失败: {error_msg}",
                    "install_method": "error",
                }
            
            # 验证 plugin.json
            manifest = self._validate_plugin(dest_path)
            if not manifest:
                shutil.rmtree(dest_path)
                return {
                    "success": False,
                    "message": "无效的插件仓库：缺少或格式错误的 plugin.json",
                    "install_method": "error",
                }
            
            logger.info(f"[github_installer] ✅ Git clone 成功: {manifest.id}")
            return {
                "success": True,
                "plugin_id": manifest.id,
                "plugin_name": manifest.name,
                "version": manifest.version,
                "message": f"插件 {manifest.name} v{manifest.version} 安装成功（Git Clone）",
                "install_method": "git",
            }
            
        except Exception as e:
            logger.exception(f"[github_installer] Git clone 异常: {e}")
            # 清理可能残留的目录
            if dest_path.exists():
                shutil.rmtree(dest_path, ignore_errors=True)
            return {
                "success": False,
                "message": f"安装异常: {str(e)}",
                "install_method": "error",
            }
    
    async def _install_via_zip_download(
        self,
        owner: str,
        repo_name: str,
        branch: str,
    ) -> dict[str, Any]:
        """通过 GitHub API 下载 zip 包安装插件"""
        client = await self._get_client()
        plugin_id = f"{owner}__{repo_name}".lower().replace("-", "_")
        
        try:
            # 1. 尝试获取最新 release 的 zip
            zip_url = None
            
            try:
                resp = await client.get(
                    f"{_GITHUB_API_BASE}/repos/{owner}/{repo_name}/releases/latest",
                )
                
                if resp.status_code == 200:
                    release_data = resp.json()
                    zip_url = release_data.get("zipball_url")
                    logger.info(f"[github_installer] 找到最新 Release: {release_data.get('tag_name', 'unknown')}")
                elif resp.status_code == 404:
                    logger.info(f"[github_installer] 无 Release，使用分支 ZIP")
                else:
                    logger.warning(f"[github_installer] 获取 Release 失败: {resp.status_code}")
            except Exception as e:
                logger.warning(f"[github_installer] 查询 Release 异常: {e}")
            
            # 2. 如果没有 release，下载分支 zip
            if not zip_url:
                zip_url = f"https://github.com/{owner}/{repo_name}/archive/refs/heads/{branch}.zip"
            
            # 3. 下载 zip 文件
            logger.info(f"[github_installer] 下载: {zip_url}")
            resp = await client.get(zip_url)
            
            if resp.status_code != 200:
                return {
                    "success": False,
                    "message": f"下载失败: HTTP {resp.status_code}",
                    "install_method": "error",
                }
            
            zip_content = resp.content
            
            # 4. 解压到临时目录
            with tempfile.TemporaryDirectory(prefix="plugin_install_") as tmpdir:
                tmp_path = Path(tmpdir)
                zip_path = tmp_path / "plugin.zip"
                zip_path.write_bytes(zip_content)
                
                # 解压
                with zipfile.ZipFile(zip_path, 'r') as zf:
                    zf.extractall(tmpdir)
                
                # 5. 查找 plugin.json 所在目录
                plugin_folder = self._find_plugin_folder(tmp_path)
                if not plugin_folder:
                    return {
                        "success": False,
                        "message": "无效的插件仓库：未找到 plugin.json",
                        "install_method": "error",
                    }
                
                # 6. 验证 manifest
                manifest = self._validate_plugin(plugin_folder)
                if not manifest:
                    return {
                        "success": False,
                        "message": "插件验证失败：plugin.json 格式错误",
                        "install_method": "error",
                    }
                
                # 7. 移动到目标目录
                final_id = manifest.id or plugin_id
                dest_path = self.target_dir / final_id
                
                if dest_path.exists():
                    shutil.rmtree(dest_path)
                    logger.info(f"[github_installer] 删除旧版本: {dest_path}")
                
                shutil.move(str(plugin_folder), str(dest_path))
                
                logger.info(f"[github_installer] ✅ ZIP 下载成功: {final_id}")
                return {
                    "success": True,
                    "plugin_id": final_id,
                    "plugin_name": manifest.name,
                    "version": manifest.version,
                    "message": f"插件 {manifest.name} v{manifest.version} 安装成功（ZIP 下载）",
                    "install_method": "zip",
                }
                
        except httpx.TimeoutException:
            return {
                "success": False,
                "message": "下载超时，请检查网络连接",
                "install_method": "error",
            }
        except Exception as e:
            logger.exception(f"[github_installer] ZIP 下载异常: {e}")
            return {
                "success": False,
                "message": f"安装异常: {str(e)}",
                "install_method": "error",
            }
    
    def _find_plugin_folder(self, base_dir: Path) -> Optional[Path]:
        """递归查找包含 plugin.json 的目录"""
        for manifest_path in base_dir.rglob("plugin.json"):
            return manifest_path.parent
        return None
    
    def _validate_plugin(self, plugin_folder: Path) -> Optional[PluginManifest]:
        """验证并解析插件的 plugin.json"""
        manifest_path = plugin_folder / "plugin.json"
        
        if not manifest_path.exists():
            logger.warning(f"[github_installer] 未找到 plugin.json: {manifest_path}")
            return None
        
        try:
            import json
            with open(manifest_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            manifest = PluginManifest.from_dict(data)
            
            # 验证必填字段
            is_valid, errors = manifest.validate()
            if not is_valid:
                logger.error(f"[github_installer] Manifest 验证失败: {errors}")
                return None
            
            return manifest
            
        except json.JSONDecodeError as e:
            logger.error(f"[github_installer] JSON 解析错误: {e}")
            return None
        except Exception as e:
            logger.error(f"[github_installer] Manifest 读取错误: {e}")
            return None
    
    async def update_plugin(
        self,
        plugin_id: str,
        use_git_pull: bool = False,
    ) -> dict[str, Any]:
        """更新已安装的 GitHub 插件
        
        Args:
            plugin_id: 插件 ID（如 user__repo-name）
            use_git_pull: 是否使用 git pull（仅限 git clone 安装的插件）
        
        Returns:
            更新结果字典
        """
        plugin_path = self.target_dir / plugin_id
        
        if not plugin_path.exists():
            return {
                "success": False,
                "message": f"插件不存在: {plugin_id}",
            }
        
        # 检查是否是 git 仓库
        git_dir = plugin_path / ".git"
        if git_dir.exists() and use_git_pull:
            return await self._git_pull_update(plugin_path)
        else:
            # 非 git 仓库，重新下载
            # 尝试从路径反推 GitHub URL
            # 格式: user__repo-name -> https://github.com/user/repo-name
            parts = plugin_id.split("__", 1)
            if len(parts) == 2:
                owner = parts[0].replace("_", "-")
                repo = parts[1].replace("_", "-")
                repo_url = f"https://github.com/{owner}/{repo}"
                return await self.install_from_github(repo_url)
            else:
                return {
                    "success": False,
                    "message": "无法确定原始 GitHub 仓库地址，请手动重新安装",
                }
    
    async def _git_pull_update(self, plugin_path: Path) -> dict[str, Any]:
        """使用 git pull 更新插件"""
        try:
            proc = await asyncio.create_subprocess_exec(
                "git", "pull", "--ff-only",
                cwd=str(plugin_path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()
            
            if proc.returncode == 0:
                output = stdout.decode("utf-8", errors="replace").strip()
                # 读取更新后的 version
                manifest = self._validate_plugin(plugin_path)
                version = manifest.version if manifest else "unknown"
                
                return {
                    "success": True,
                    "message": f"插件更新成功 (v{version})",
                    "details": output,
                }
            else:
                error = stderr.decode("utf-8", errors="replace").strip()
                return {
                    "success": False,
                    "message": f"Git pull 失败: {error}",
                }
                
        except Exception as e:
            return {
                "success": False,
                "message": f"更新异常: {str(e)}",
            }


# ==================== 单例实例 ====================

_installer_instance: Optional[GithubInstaller] = None


def get_github_installer() -> GithubInstaller:
    """获取全局 GithubInstaller 实例"""
    global _installer_instance
    if _installer_instance is None:
        _installer_instance = GithubInstaller()
    return _installer_instance


async def cleanup_github_installer():
    """清理全局实例（应用关闭时调用）"""
    global _installer_instance
    if _installer_instance:
        await _installer_instance.close()
        _installer_instance = None