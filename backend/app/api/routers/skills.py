"""Skill 列表查询 + 注册 API。

供前端右侧工作区动态拉取各节点可用的 Skill 清单，
渲染模型/风格下拉框。第三方 Skill 通过 backend/skills/ 目录扫描自动加载。
支持通过上传 .py 文件动态注册第三方 Skill。
支持通过前端表单创建提示词型 Skill（.md 文件，PromptDrivenSkill）。
支持从 GitHub URL 安装 Skill（clone 仓库 → 提取 .py / SKILL.md → 注册）。
"""

import importlib
import importlib.util
import logging
import os
import re
import shutil
import subprocess
import sys
import traceback
from pathlib import Path

from fastapi import APIRouter, Depends, Query, UploadFile, File, HTTPException
from pydantic import BaseModel, Field

from app.tools.registry import SkillRegistry, ensure_builtin_skills_registered
from app.api.deps import get_current_user
from app.api.schemas.common import StandardResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/skills", tags=["skills"])

SKILLS_DIR = Path(__file__).resolve().parent.parent.parent.parent / "skills"


class SkillRegisterResult(BaseModel):
    filename: str
    skill_name: str
    node_type: str
    display_name: str
    description: str


def _load_and_register_skill(
    target_path: Path,
    filename: str,
    registry: SkillRegistry,
    before: set[str],
) -> SkillRegisterResult:
    """动态加载 .py 文件并注册到 SkillRegistry。

    模块名与 registry.py _load_module 保持一致（_file 后缀），
    避免同一文件被 scan_third_party 二次加载导致双重注册。
    """
    module_name = f"_third_party_skill_{target_path.stem}_file"
    try:
        if module_name in sys.modules:
            del sys.modules[module_name]
        spec = importlib.util.spec_from_file_location(module_name, target_path)
        if spec is None or spec.loader is None:
            raise ValueError(f"cannot load module: {target_path}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
    except Exception as e:
        if target_path.exists():
            target_path.unlink()
        logger.error(f"[skill-load] failed to load {filename}: {traceback.format_exc()}")
        raise HTTPException(status_code=422, detail=f"加载失败：{e}")

    after = set()
    for skills_map in registry._skills.values():
        after.update(skills_map.keys())

    new_names = after - before
    if not new_names:
        if target_path.exists():
            target_path.unlink()
        raise HTTPException(
            status_code=422,
            detail="文件加载成功但未注册任何 Skill（请确保使用了 @register 装饰器）",
        )

    registered_name = next(iter(new_names))
    skill_cls = None
    for skills_map in registry._skills.values():
        if registered_name in skills_map:
            skill_cls = skills_map[registered_name]
            break

    if skill_cls is None:
        raise HTTPException(status_code=500, detail="注册成功但无法找到 Skill 类")

    return SkillRegisterResult(
        filename=filename,
        skill_name=skill_cls.name,
        node_type=skill_cls.node_type,
        display_name=skill_cls.display_name or skill_cls.name,
        description=skill_cls.description,
    )


def _invalidate_skill_caches() -> None:
    """热插拔后失效全局缓存，确保新 Skill 对 Agent 可见。"""
    try:
        from app.agents.registry import _skills_cache
        import app.agents.registry as _ar
        _ar._skills_cache = None
    except Exception:
        pass
    try:
        import app.api.routers.chat_agent as _ca
        _ca._trigger_words_cache = None
    except Exception:
        pass


def _ensure_builtin_skills_registered() -> None:
    """确保内置 Skill 模块已导入并注册。

    内置 Skill 用 @register 装饰器在模块 import 时注册到 SkillRegistry。
    但 Python 模块是懒加载的，如果不显式 import，@register 不会执行。
    这里统一触发内置 Skill 模块的 import，保证 /api/skills 能返回完整列表。
    """
    ensure_builtin_skills_registered()


@router.get("")
async def list_skills(
    node_type: str | None = Query(default=None, description="按节点类型过滤（如 copywrite/image_gen/analyze/audit）"),
    user_id: str = Depends(get_current_user),
) -> StandardResponse[dict[str, list[dict]]]:
    """列出所有可用的 Skill（按 node_type 分组）。

    可选 query 参数 node_type：只返回指定节点的 Skill 列表。
    例如 GET /api/skills?node_type=copywrite 只返回文案类 Skill。

    返回结构：
    {
      "copywrite": [
        {"node_type": "copywrite", "name": "lively_girl", "display_name": "活泼少女风", "description": "...", "default_config": {}},
        ...
      ],
      "image_gen": [...],
      "analyze": [...],
      "audit": [...]
    }

    内置 Skill 在接口调用时显式触发 import 注册。
    第三方 Skill（backend/skills/ 目录下的 .py 文件）会在首次调用时自动扫描注册。
    """
    # 1. 触发内置 Skill 注册（import 即注册）
    _ensure_builtin_skills_registered()

    # 2. 触发第三方 Skill 扫描（懒加载，首次调用时执行）
    registry = SkillRegistry.instance()
    registry.scan_third_party()

    if node_type:
        # 单节点查询：返回 {node_type: [...]}
        skills_list = registry.list_by_node(node_type)
        return StandardResponse(data={node_type: skills_list})

    # 全量查询
    return StandardResponse(data=registry.list_all())


@router.post("/register", response_model=StandardResponse[SkillRegisterResult])
async def register_skill(
    file: UploadFile = File(..., description="Skill Python 文件（.py）"),
    user_id: str = Depends(get_current_user),
) -> StandardResponse[SkillRegisterResult]:
    """上传 .py 文件注册第三方 Skill。

    文件保存到 backend/skills/ 目录，动态 import 并注册到 SkillRegistry。
    文件内须定义 Skill 子类并用 @register 装饰器注册。
    """
    if not file.filename or not file.filename.endswith(".py"):
        raise HTTPException(status_code=400, detail="仅支持 .py 文件")

    filename = file.filename
    target_path = SKILLS_DIR / filename

    content = await file.read()
    if len(content) > 64 * 1024:
        raise HTTPException(status_code=400, detail="文件不能超过 64KB")

    try:
        code = content.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="文件编码须为 UTF-8")

    safety_keywords = ["os.system", "subprocess", "eval(", "exec(", "__import__", "shutil.rmtree"]
    for kw in safety_keywords:
        if kw in code:
            raise HTTPException(status_code=400, detail=f"安全限制：代码包含禁止的关键字 '{kw}'")

    SKILLS_DIR.mkdir(parents=True, exist_ok=True)
    target_path.write_bytes(content)

    _ensure_builtin_skills_registered()
    registry = SkillRegistry.instance()

    before = set()
    for skills_map in registry._skills.values():
        before.update(skills_map.keys())

    result = _load_and_register_skill(target_path, filename, registry, before)
    _invalidate_skill_caches()
    return StandardResponse(data=result, message=f"Skill '{result.skill_name}' 注册成功")


@router.delete("/{node_type}/{skill_name}", response_model=StandardResponse[str])
async def unregister_skill(
    node_type: str,
    skill_name: str,
    user_id: str = Depends(get_current_user),
) -> StandardResponse[str]:
    """注销第三方 Skill 并删除对应文件。

    内置 Skill（app/agents/skills/ 下的）不可删除。
    """
    _ensure_builtin_skills_registered()
    registry = SkillRegistry.instance()

    skill_cls = registry.get(node_type, skill_name)
    if skill_cls is None:
        raise HTTPException(status_code=404, detail=f"Skill '{node_type}.{skill_name}' 不存在")

    module_name = getattr(skill_cls, "__module__", "")
    if not module_name.startswith("_third_party_skill_"):
        raise HTTPException(status_code=403, detail="内置 Skill 不可删除")

    if module_name and module_name in sys.modules:
        mod = sys.modules[module_name]
        file_path = getattr(mod, "__file__", None)
        if file_path:
            p = Path(file_path).resolve()
            if not str(p).startswith(str(SKILLS_DIR.resolve())):
                logger.warning(f"[unregister_skill] file {p} outside skills dir, skipping deletion")
            else:
                target_dir = p.parent if p.name == "__init__.py" else None
                if p.exists():
                    p.unlink()
                    logger.info(f"[unregister_skill] deleted file {p}")
                if target_dir and target_dir.exists():
                    import shutil
                    shutil.rmtree(target_dir, ignore_errors=True)
                    logger.info(f"[unregister_skill] deleted dir {target_dir}")
        del sys.modules[module_name]
        logger.info(f"[unregister_skill] removed module {module_name} from sys.modules")

    registry.unregister(node_type, skill_name)
    _invalidate_skill_caches()

    return StandardResponse(data=skill_name, message=f"Skill '{skill_name}' 已注销")


# ============================================================================
# 提示词型 Skill（.md）API
# ============================================================================

PROMPT_SKILLS_DIR = Path(__file__).resolve().parent.parent.parent / "agents" / "prompts" / "skills"


class PromptSkillCreateRequest(BaseModel):
    node_type: str = Field(..., description="节点类型，如 quality_gate / topic_evaluator / analyze")
    name: str = Field(..., description="Skill 唯一标识（英文小写+下划线），如 my_checker")
    display_name: str = Field(..., description="前端展示名，如 我的检查器")
    description: str = Field(default="", description="Skill 描述")
    trigger_words: list[str] = Field(default_factory=list, description="触发词列表，如 ['检查', '审核']")
    prompt_guidance: str = Field(default="", description="给 Agent 的简短提示，说明何时使用此 Skill")
    skill_body: str = Field(..., description="SKILL.md 正文（提示词内容，YAML frontmatter 后的部分）")


class PromptSkillCreateResult(BaseModel):
    filename: str
    skill_name: str
    node_type: str
    display_name: str
    description: str


@router.post("/prompt", response_model=StandardResponse[PromptSkillCreateResult])
async def create_prompt_skill(
    body: PromptSkillCreateRequest,
    user_id: str = Depends(get_current_user),
) -> StandardResponse[PromptSkillCreateResult]:
    """创建提示词型 Skill（.md 文件，PromptDrivenSkill）。

    用户在前端填写表单，后端自动组装 YAML frontmatter + SKILL.md 正文，
    保存为 .md 文件到 prompts/skills/ 目录并即时注册到 SkillRegistry。
    无需重启后端，创建后立即可用。
    """
    import re as _re

    if not _re.match(r"^[a-z][a-z0-9_]*$", body.name):
        raise HTTPException(
            status_code=400,
            detail="name 只允许小写英文字母、数字和下划线，且以字母开头",
        )

    if not body.node_type.strip():
        raise HTTPException(status_code=400, detail="node_type 不能为空")

    if not body.skill_body.strip():
        raise HTTPException(status_code=400, detail="Skill 正文不能为空")

    _ensure_builtin_skills_registered()

    filename = f"{body.name}.md"

    frontmatter_lines = [
        "---",
        f"node_type: {body.node_type}",
        f"name: {body.name}",
        f"display_name: {body.display_name}",
        f"description: {body.description}",
    ]
    if body.trigger_words:
        tw_str = ", ".join(f'"{w}"' for w in body.trigger_words)
        frontmatter_lines.append(f"trigger_words: [{tw_str}]")
    if body.prompt_guidance:
        frontmatter_lines.append(f"prompt_guidance: {body.prompt_guidance}")
    frontmatter_lines.append("---")

    content = "\n".join(frontmatter_lines) + "\n\n" + body.skill_body.strip() + "\n"

    try:
        from app.tools.prompt_skills import register_prompt_skill_from_content

        skill_cls = register_prompt_skill_from_content(filename, content)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"[create_prompt_skill] failed: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"创建失败: {e}")

    _invalidate_skill_caches()

    result = PromptSkillCreateResult(
        filename=filename,
        skill_name=skill_cls.name,
        node_type=skill_cls.node_type,
        display_name=skill_cls.display_name or skill_cls.name,
        description=skill_cls.description,
    )
    return StandardResponse(data=result, message=f"提示词型 Skill '{result.display_name}' 创建成功")


@router.post("/prompt/upload", response_model=StandardResponse[PromptSkillCreateResult])
async def upload_prompt_skill(
    file: UploadFile = File(..., description="Skill Markdown 文件（.md），含 YAML frontmatter + SKILL.md 正文"),
    user_id: str = Depends(get_current_user),
) -> StandardResponse[PromptSkillCreateResult]:
    """上传 .md 文件注册提示词型 Skill。

    文件须包含 YAML frontmatter（node_type / name / display_name / description），
    后跟 SKILL.md 正文。保存到 prompts/skills/ 目录并即时注册。
    """
    if not file.filename or not file.filename.endswith(".md"):
        raise HTTPException(status_code=400, detail="仅支持 .md 文件")

    content_bytes = await file.read()
    if len(content_bytes) > 256 * 1024:
        raise HTTPException(status_code=400, detail="文件不能超过 256KB")

    try:
        content = content_bytes.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="文件编码须为 UTF-8")

    _ensure_builtin_skills_registered()

    filename = file.filename

    try:
        from app.tools.prompt_skills import register_prompt_skill_from_content

        skill_cls = register_prompt_skill_from_content(filename, content)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"[upload_prompt_skill] failed: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"上传注册失败: {e}")

    _invalidate_skill_caches()

    result = PromptSkillCreateResult(
        filename=filename,
        skill_name=skill_cls.name,
        node_type=skill_cls.node_type,
        display_name=skill_cls.display_name or skill_cls.name,
        description=skill_cls.description,
    )
    return StandardResponse(data=result, message=f"提示词型 Skill '{result.display_name}' 上传注册成功")


@router.delete("/prompt/{node_type}/{skill_name}", response_model=StandardResponse[str])
async def delete_prompt_skill(
    node_type: str,
    skill_name: str,
    user_id: str = Depends(get_current_user),
) -> StandardResponse[str]:
    """删除提示词型 Skill（.md 文件）并从 SkillRegistry 注销。

    只能删除 prompts/skills/ 下的 .md 文件创建的 Skill，
    内置 Skill 不可删除。
    """
    _ensure_builtin_skills_registered()
    registry = SkillRegistry.instance()

    skill_cls = registry.get(node_type, skill_name)
    if skill_cls is None:
        raise HTTPException(status_code=404, detail=f"Skill '{node_type}.{skill_name}' 不存在")

    module_name = getattr(skill_cls, "__module__", "")
    if not module_name.startswith("app.tools.prompt_skills."):
        raise HTTPException(status_code=403, detail="仅支持删除提示词型 Skill（.md 文件创建的）")

    md_filename = getattr(skill_cls, "skill_md_path", "")
    if not md_filename:
        raise HTTPException(status_code=403, detail="无法定位 Skill 对应的 .md 文件")

    md_path = PROMPT_SKILLS_DIR / md_filename
    if md_path.exists():
        md_path.unlink()
        logger.info(f"[delete_prompt_skill] deleted {md_path}")
    else:
        logger.warning(f"[delete_prompt_skill] file not found: {md_path}")

    registry.unregister(node_type, skill_name)
    _invalidate_skill_caches()

    return StandardResponse(data=skill_name, message=f"提示词型 Skill '{skill_name}' 已删除")


@router.post("/import", response_model=StandardResponse[SkillRegisterResult])
async def import_skill(
    file: UploadFile = File(..., description="Skill Python 文件（.py）"),
    user_id: str = Depends(get_current_user),
) -> StandardResponse[SkillRegisterResult]:
    """导入第三方 Skill：AST 安全校验 + 权限门控 + 动态注册。

    比 /register 更安全：
    1. AST 级别检查（不仅匹配字符串，而是遍历语法树）
    2. 需要 SKILL_IMPORT 权限
    3. 100KB 文件大小限制
    """
    import ast as _ast

    from app.engine.schemas import PermissionDeniedError, WorkflowContext
    from app.tools.permissions import permission_gate, Permission

    context = WorkflowContext(workflow_id="", node_id="skill_import", user_id=user_id, account_id="")
    try:
        await permission_gate.require([Permission.SKILL_IMPORT], context)
    except PermissionDeniedError as e:
        raise HTTPException(status_code=403, detail=str(e))

    if not file.filename or not file.filename.endswith(".py"):
        raise HTTPException(status_code=400, detail="仅支持 .py 文件")

    content = await file.read()
    if len(content) > 100_000:
        raise HTTPException(status_code=413, detail="Skill 文件过大（最大 100KB）")

    try:
        code = content.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="文件编码须为 UTF-8")

    try:
        tree = _ast.parse(code)
    except SyntaxError as e:
        raise HTTPException(status_code=400, detail=f"语法错误: {e}")

    DANGEROUS_ATTRS = {"system", "popen", "call", "run", "eval", "exec", "__import__"}
    for node in _ast.walk(tree):
        if isinstance(node, _ast.Call):
            if isinstance(node.func, _ast.Attribute) and node.func.attr in DANGEROUS_ATTRS:
                raise HTTPException(
                    status_code=400,
                    detail=f"禁止的危险调用: {node.func.attr}",
                )

    filename = file.filename
    target_path = SKILLS_DIR / filename
    SKILLS_DIR.mkdir(parents=True, exist_ok=True)
    target_path.write_bytes(content)

    _ensure_builtin_skills_registered()
    registry = SkillRegistry.instance()

    before = set()
    for skills_map in registry._skills.values():
        before.update(skills_map.keys())

    result = _load_and_register_skill(target_path, filename, registry, before)
    _invalidate_skill_caches()
    return StandardResponse(data=result, message=f"Skill '{result.skill_name}' 导入成功")


class GitHubInstallRequest(BaseModel):
    url: str
    subpath: str = ""


class GitHubInstallResult(BaseModel):
    repo: str
    skill_name: str
    node_type: str
    display_name: str
    description: str
    skill_md: str = ""
    installed_files: list[str] = []


@router.post("/install-github", response_model=StandardResponse[GitHubInstallResult])
async def install_skill_from_github(
    body: GitHubInstallRequest,
    user_id: str = Depends(get_current_user),
) -> StandardResponse[GitHubInstallResult]:
    """从 GitHub URL 安装 Skill。

    支持:
    - https://github.com/owner/repo
    - https://github.com/owner/repo/tree/branch/subpath

    流程:
    1. git clone 到临时目录
    2. 扫描 .py 文件（含 @register 装饰器）→ 复制到 backend/skills/ 并注册
    3. 扫描 SKILL.md → 保存到 backend/skills/{repo_name}/SKILL.md
    4. 返回安装结果
    """
    url = body.url.strip().rstrip("/")
    subpath = body.subpath.strip()

    # 解析 GitHub URL
    # 格式: https://github.com/owner/repo 或 https://github.com/owner/repo/tree/branch/subpath
    gh_pattern = r"https?://github\.com/([^/]+)/([^/]+)(?:/tree/([^/]+)(/.*)?)?"
    m = re.match(gh_pattern, url)
    if not m:
        raise HTTPException(status_code=400, detail="无效的 GitHub URL，格式: https://github.com/owner/repo")

    owner = m.group(1)
    repo_name = m.group(2)
    branch = m.group(3) or "main"
    url_subpath = (m.group(4) or "").strip("/")
    effective_subpath = url_subpath or subpath

    clone_url = f"https://github.com/{owner}/{repo_name}.git"
    logger.info(f"[install-github] installing {owner}/{repo_name} (branch={branch}, subpath={effective_subpath})")

    import tempfile
    import zipfile
    import io
    tmp_dir = tempfile.mkdtemp(prefix="skill_install_")
    try:
        # Strategy 1: Download zip via GitHub API (no git required, works without proxy)
        zip_url = f"https://api.github.com/repos/{owner}/{repo_name}/zipball/{branch}"
        logger.info(f"[install-github] downloading zip: {zip_url}")
        import httpx as _httpx
        try:
            async with _httpx.AsyncClient(timeout=60, follow_redirects=True) as client:
                resp = await client.get(zip_url)
                if resp.status_code != 200:
                    raise RuntimeError(f"GitHub API returned {resp.status_code}: {resp.text[:200]}")
                zip_bytes = resp.content
        except Exception as e:
            logger.warning(f"[install-github] zip download failed: {e}, trying git clone")

            # Strategy 2: git clone fallback
            env = os.environ.copy()
            git_cmd = "git"
            if os.name == "nt":
                git_paths = [
                    r"C:\Program Files\Git\cmd\git.exe",
                    r"C:\Program Files (x86)\Git\cmd\git.exe",
                ]
                for gp in git_paths:
                    if os.path.isfile(gp):
                        git_cmd = gp
                        break
                git_dir = os.path.dirname(git_cmd)
                if git_dir not in env.get("PATH", ""):
                    env["PATH"] = git_dir + os.pathsep + env.get("PATH", "")

            result = subprocess.run(
                [git_cmd, "clone", "--depth", "1", "--branch", branch, clone_url, tmp_dir],
                capture_output=True, text=True, timeout=60, env=env,
            )
            if result.returncode != 0:
                raise HTTPException(
                    status_code=422,
                    detail=f"git clone 失败: {result.stderr[:500]}",
                )
            zip_bytes = None

        if zip_bytes:
            # Extract zip to tmp_dir
            with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
                zf.extractall(tmp_dir)
            # GitHub zipballs have a top-level dir like "owner-repo-abc123", find it
            entries = os.listdir(tmp_dir)
            if len(entries) == 1 and os.path.isdir(os.path.join(tmp_dir, entries[0])):
                # Move contents up one level
                inner_dir = os.path.join(tmp_dir, entries[0])
                for item in os.listdir(inner_dir):
                    shutil.move(os.path.join(inner_dir, item), os.path.join(tmp_dir, item))
                os.rmdir(inner_dir)

        # 定位 skill 目录
        if effective_subpath:
            skill_src_dir = Path(tmp_dir) / effective_subpath
        else:
            skill_src_dir = Path(tmp_dir)

        if not skill_src_dir.exists():
            raise HTTPException(
                status_code=400,
                detail=f"子路径 '{effective_subpath}' 不存在于仓库中",
            )

        # 目标目录: backend/skills/{repo_name}/
        target_dir = SKILLS_DIR / repo_name
        target_dir.mkdir(parents=True, exist_ok=True)

        installed_files = []
        skill_md_content = ""
        py_files_found = []

        # 1. 扫描并复制 .py 文件
        for py_file in skill_src_dir.rglob("*.py"):
            if py_file.name.startswith("__") and py_file.name == "__init__.py":
                continue
            # 安全检查
            code = py_file.read_text(encoding="utf-8", errors="ignore")
            safety_keywords = ["os.system", "subprocess", "eval(", "exec(", "__import__", "shutil.rmtree"]
            for kw in safety_keywords:
                if kw in code:
                    logger.warning(f"[install-github] skipping {py_file.name}: contains '{kw}'")
                    continue

            rel = py_file.relative_to(skill_src_dir)
            dest = target_dir / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(py_file, dest)
            installed_files.append(str(rel))
            py_files_found.append(dest)

        # 2. 扫描 SKILL.md
        skill_md_path = skill_src_dir / "SKILL.md"
        if skill_md_path.exists():
            skill_md_content = skill_md_path.read_text(encoding="utf-8", errors="ignore")
            dest_md = target_dir / "SKILL.md"
            shutil.copy2(skill_md_path, dest_md)
            installed_files.append("SKILL.md")

        # 3. 复制 references/ 目录（如果有）
        refs_src = skill_src_dir / "references"
        if refs_src.exists() and refs_src.is_dir():
            refs_dest = target_dir / "references"
            if refs_dest.exists():
                shutil.rmtree(refs_dest)
            shutil.copytree(refs_src, refs_dest)
            for f in refs_dest.rglob("*"):
                if f.is_file():
                    installed_files.append(str(f.relative_to(target_dir)))

        # 4. 复制 scripts/ 目录（如果有）
        scripts_src = skill_src_dir / "scripts"
        if scripts_src.exists() and scripts_src.is_dir():
            scripts_dest = target_dir / "scripts"
            if scripts_dest.exists():
                shutil.rmtree(scripts_dest)
            shutil.copytree(scripts_src, scripts_dest)
            for f in scripts_dest.rglob("*"):
                if f.is_file():
                    installed_files.append(str(f.relative_to(target_dir)))

        # 5. 复制 Node.js skill 核心目录（bin/ src/ examples/）
        for core_dir_name in ("bin", "src", "examples"):
            core_src = skill_src_dir / core_dir_name
            if core_src.exists() and core_src.is_dir():
                core_dest = target_dir / core_dir_name
                if core_dest.exists():
                    shutil.rmtree(core_dest)
                shutil.copytree(core_src, core_dest)
                for f in core_dest.rglob("*"):
                    if f.is_file():
                        installed_files.append(str(f.relative_to(target_dir)))

        # 6. 如果有 package.json，也复制（Node.js skill）
        pkg_json = skill_src_dir / "package.json"
        if pkg_json.exists():
            shutil.copy2(pkg_json, target_dir / "package.json")
            installed_files.append("package.json")
            # npm install (optional, skip if npm not found)
            try:
                npm_result = subprocess.run(
                    ["npm", "install"],
                    cwd=str(target_dir),
                    capture_output=True, text=True, timeout=120,
                )
                if npm_result.returncode != 0:
                    logger.warning(f"[install-github] npm install failed: {npm_result.stderr[:300]}")
            except FileNotFoundError:
                logger.info("[install-github] npm not found, skipping npm install")

        # 7. 注册 Python Skill 到 SkillRegistry
        _ensure_builtin_skills_registered()
        registry = SkillRegistry.instance()

        before = set()
        for skills_map in registry._skills.values():
            before.update(skills_map.keys())

        # 强制重新扫描第三方 skill
        registry.scan_third_party(force=True)

        after = set()
        for skills_map in registry._skills.values():
            after.update(skills_map.keys())

        new_names = after - before

        # 确定注册信息
        if new_names:
            registered_name = next(iter(new_names))
            skill_cls = None
            for skills_map in registry._skills.values():
                if registered_name in skills_map:
                    skill_cls = skills_map[registered_name]
                    break
            if skill_cls:
                result = GitHubInstallResult(
                    repo=f"{owner}/{repo_name}",
                    skill_name=skill_cls.name,
                    node_type=skill_cls.node_type,
                    display_name=skill_cls.display_name or skill_cls.name,
                    description=skill_cls.description,
                    skill_md=skill_md_content[:2000],
                    installed_files=installed_files,
                )
                _invalidate_skill_caches()
                return StandardResponse(data=result, message=f"Skill '{skill_cls.name}' 安装成功")
        else:
            # 没有 Python @register，但有 SKILL.md 或其他文件
            # 从 SKILL.md 提取 skill name
            extracted_name = repo_name
            if skill_md_content:
                name_match = re.search(r"^#\s+(.+)", skill_md_content, re.MULTILINE)
                if name_match:
                    extracted_name = name_match.group(1).strip()

            result = GitHubInstallResult(
                repo=f"{owner}/{repo_name}",
                skill_name=extracted_name,
                node_type="external",
                display_name=extracted_name,
                description=f"GitHub Skill from {owner}/{repo_name}",
                skill_md=skill_md_content[:2000],
                installed_files=installed_files,
            )
            return StandardResponse(data=result, message=f"Skill '{extracted_name}' 安装成功（非 Python Skill，文件已保存）")

    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=422, detail="git clone 超时（60秒）")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[install-github] failed: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"安装失败: {e}")
    finally:
        # 清理临时目录
        try:
            shutil.rmtree(tmp_dir, ignore_errors=True)
        except Exception:
            pass