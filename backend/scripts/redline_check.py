"""全局红线自检脚本（手册 Phase 8 Part C）。

扫描 backend 下所有 .py 文件，检查 7 项硬红线：
1. harness 子包内不 import langgraph
2. 没有用 WebSocket（必须用 SSE + HTTP POST 双通道）
3. 没有用 MemorySaver（必须用 PostgresSaver）
4. copywrite_agent 用 R1（YAML 配置）
5. 监督 Agent（软语义）用 V3（YAML 配置 + graph.py 调用）
6. 无明文 Token 存储（XhsAccount 表用 encrypted 字段）
7. User:Account 是 1:N（外键 + 索引）

用法：
    .venv\\Scripts\\python.exe scripts\\redline_check.py

退出码：
    0 = 全部通过
    1 = 至少一项违反
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import NamedTuple

# backend 根目录
BACKEND_DIR = Path(__file__).resolve().parent.parent
APP_DIR = BACKEND_DIR / "app"


class CheckResult(NamedTuple):
    """单项检查结果。"""
    name: str
    passed: bool
    detail: str


def _iter_py_files(root: Path) -> list[Path]:
    """迭代 root 下所有 .py 文件（跳过 .venv / __pycache__）。"""
    files: list[Path] = []
    for p in root.rglob("*.py"):
        rel = p.relative_to(root)
        parts = rel.parts
        if any(part in {".venv", "__pycache__", ".pytest_cache", ".ruff_cache"} for part in parts):
            continue
        files.append(p)
    return files


# ----------------------------------------------------------------------
# 检查 1: harness 子包内不 import langgraph
# ----------------------------------------------------------------------

def check_harness_no_langgraph() -> CheckResult:
    """红线 2.1: Harness 不能 import langgraph（架构分层）。"""
    harness_dir = APP_DIR / "agents" / "core" / "harness"
    if not harness_dir.exists():
        return CheckResult("harness_no_langgraph", False, f"harness dir not found: {harness_dir}")

    violations: list[str] = []
    for p in harness_dir.rglob("*.py"):
        try:
            text = p.read_text(encoding="utf-8")
        except Exception as e:
            violations.append(f"{p.name}: read failed {e}")
            continue
        # 匹配 import langgraph / from langgraph
        if re.search(r"^\s*(?:import\s+langgraph|from\s+langgraph)", text, re.MULTILINE):
            violations.append(str(p.relative_to(BACKEND_DIR)))

    if violations:
        return CheckResult(
            "harness_no_langgraph",
            False,
            f"harness 内禁止 import langgraph，违规文件: {violations}",
        )
    return CheckResult("harness_no_langgraph", True, "harness 子包未 import langgraph")


# ----------------------------------------------------------------------
# 检查 2: 没有用 WebSocket
# ----------------------------------------------------------------------

def check_no_websocket() -> CheckResult:
    """红线 5.1: 必须用 SSE + HTTP POST 双通道，禁用 WebSocket。

    精确匹配真实代码使用，排除注释/docstring 中的描述性提及。
    """
    violations: list[str] = []
    # 只匹配真实使用：import / from import / 函数调用 / 类型注解 / ws:// URL
    pattern = re.compile(
        r"^\s*(?:"
        r"import\s+(?:websockets?|fastapi\.WebSocket)"
        r"|from\s+(?:websockets?|fastapi)\s+import\s+.*\bWebSocket\b"
        r"|.*\bWebSocket\s*\("  # WebSocket() 调用
        r"|.*\bWebSocket\b\s*(?:\[|\]|:)"  # WebSocket 类型注解
        r"|.*['\"]wss?://"
        r")",
        re.MULTILINE,
    )
    for p in _iter_py_files(APP_DIR):
        try:
            text = p.read_text(encoding="utf-8")
        except Exception:
            continue
        for i, line in enumerate(text.splitlines(), 1):
            stripped = line.lstrip()
            if stripped.startswith("#"):
                continue
            # 去除行尾注释（粗略：两个空格 + # 之后视为注释）
            if "  #" in line:
                line = line.split("  #", 1)[0]
            if pattern.match(line):
                violations.append(f"{p.relative_to(BACKEND_DIR)}:{i}: {line.strip()}")

    if violations:
        return CheckResult(
            "no_websocket",
            False,
            f"禁止使用 WebSocket，违规位置: {violations[:5]}",
        )
    return CheckResult("no_websocket", True, "未发现 WebSocket 使用")


# ----------------------------------------------------------------------
# 检查 3: 没有用 MemorySaver
# ----------------------------------------------------------------------

def check_no_memory_saver() -> CheckResult:
    """红线：必须用 PostgresSaver，禁用 MemorySaver（D6 无 stale state）。

    精确匹配真实代码使用，排除注释/docstring 中的提及。
    """
    violations: list[str] = []
    # 只匹配真实使用：import / from import / 实例化调用
    pattern = re.compile(
        r"^\s*(?:"
        r"import\s+.*\bMemorySaver\b"
        r"|from\s+.*\bMemorySaver\b"
        r"|.*\bMemorySaver\s*\("  # MemorySaver() 调用
        r"|.*=\s*MemorySaver\b"  # 赋值
        r")",
        re.MULTILINE,
    )
    for p in _iter_py_files(APP_DIR):
        try:
            text = p.read_text(encoding="utf-8")
        except Exception:
            continue
        for i, line in enumerate(text.splitlines(), 1):
            stripped = line.lstrip()
            if stripped.startswith("#"):
                continue
            if "  #" in line:
                line = line.split("  #", 1)[0]
            if pattern.match(line):
                violations.append(f"{p.relative_to(BACKEND_DIR)}:{i}: {line.strip()}")

    if violations:
        return CheckResult(
            "no_memory_saver",
            False,
            f"禁止使用 MemorySaver，违规位置: {violations}",
        )
    return CheckResult("no_memory_saver", True, "未发现 MemorySaver 使用")


# ----------------------------------------------------------------------
# 检查 4: copywrite_agent 用 R1
# ----------------------------------------------------------------------

def check_copywrite_uses_r1() -> CheckResult:
    """红线 9: 文案 Agent 必须用 DeepSeek-R1。"""
    cfg = APP_DIR / "agents" / "configs" / "copywrite_agent.yaml"
    if not cfg.exists():
        return CheckResult("copywrite_uses_r1", False, f"config not found: {cfg}")

    try:
        text = cfg.read_text(encoding="utf-8")
    except Exception as e:
        return CheckResult("copywrite_uses_r1", False, f"read failed: {e}")

    # 匹配 model: deepseek-r1 或 model: deepseek-reasoner
    m = re.search(r"^model:\s*(\S+)\s*$", text, re.MULTILINE)
    if not m:
        return CheckResult("copywrite_uses_r1", False, "未找到 model 字段")
    model = m.group(1)
    if model in {"deepseek-r1", "deepseek-reasoner"}:
        return CheckResult("copywrite_uses_r1", True, f"copywrite model={model}")
    return CheckResult(
        "copywrite_uses_r1",
        False,
        f"copywrite 必须用 R1，当前 model={model}",
    )


# ----------------------------------------------------------------------
# 检查 5: 监督 Agent（软语义）用 V3
# ----------------------------------------------------------------------

def check_supervisor_uses_v3() -> CheckResult:
    """红线 9 + 2.3: 监督软语义必须用 DeepSeek-V3，禁止用 R1。"""
    # 5.1: analyze/audit 的 YAML 配置应为 V3
    v3_configs = ["analyze_agent.yaml", "audit_agent.yaml"]
    violations: list[str] = []
    for name in v3_configs:
        cfg = APP_DIR / "agents" / "configs" / name
        if not cfg.exists():
            violations.append(f"{name} not found")
            continue
        try:
            text = cfg.read_text(encoding="utf-8")
        except Exception as e:
            violations.append(f"{name}: read failed {e}")
            continue
        m = re.search(r"^model:\s*(\S+)\s*$", text, re.MULTILINE)
        if not m:
            violations.append(f"{name}: no model field")
            continue
        model = m.group(1)
        if model not in {"deepseek-v3", "deepseek-chat"}:
            violations.append(f"{name}: model={model} (应为 v3)")

    # 5.2: graph.py 的软语义节点应调 get_deepseek_llm（V3 默认）
    graph_py = APP_DIR / "agents" / "graph.py"
    if graph_py.exists():
        text = graph_py.read_text(encoding="utf-8")
        if "get_deepseek_llm" not in text:
            violations.append("graph.py: soft semantic 未通过 get_deepseek_llm 调 V3")
        # 软语义节点不应显式用 R1
        if re.search(r"deepseek[-_]r1|deepseek[-_]reasoner", text, re.IGNORECASE):
            violations.append("graph.py: 软语义节点疑似使用 R1")

    if violations:
        return CheckResult(
            "supervisor_uses_v3",
            False,
            f"监督软语义必须用 V3，违规: {violations}",
        )
    return CheckResult("supervisor_uses_v3", True, "监督软语义用 V3")


# ----------------------------------------------------------------------
# 检查 6: 无明文 Token 存储
# ----------------------------------------------------------------------

def check_no_plaintext_token() -> CheckResult:
    """红线 3.3: XhsAccount 表 Token 必须加密存储。"""
    models_py = APP_DIR / "db" / "models.py"
    if not models_py.exists():
        return CheckResult("no_plaintext_token", False, "models.py not found")

    try:
        text = models_py.read_text(encoding="utf-8")
    except Exception as e:
        return CheckResult("no_plaintext_token", False, f"read failed: {e}")

    # 检查 XhsAccount 类的字段：session_data / refresh_token 必须是 *_encrypted
    # 简化：检查是否含有明文 token / cookie 字段（非 encrypted 后缀）
    violations: list[str] = []

    # 找 XhsAccount class 段
    m = re.search(
        r"class\s+XhsAccount\b.*?(?=\nclass\s|\Z)",
        text,
        re.DOTALL,
    )
    if not m:
        violations.append("XhsAccount class not found")
    else:
        cls_text = m.group(0)
        # 找所有 mapped_column 字段名
        field_pattern = re.compile(r"^(\w+):\s*Mapped.*=.*mapped_column", re.MULTILINE)
        for fm in field_pattern.finditer(cls_text):
            field_name = fm.group(1)
            # 关键字段必须以 _encrypted 结尾或不含敏感关键字
            sensitive_keywords = ["session_data", "refresh_token", "access_token", "cookie"]
            for kw in sensitive_keywords:
                if kw in field_name.lower() and not field_name.endswith("_encrypted"):
                    violations.append(f"XhsAccount.{field_name} 应加密存储")

    if violations:
        return CheckResult(
            "no_plaintext_token",
            False,
            f"发现明文 Token 字段: {violations}",
        )
    return CheckResult("no_plaintext_token", True, "Token 字段均加密存储")


# ----------------------------------------------------------------------
# 检查 7: User:Account 是 1:N
# ----------------------------------------------------------------------

def check_user_account_one_to_many() -> CheckResult:
    """红线 7.1: User 与 XhsAccount 必须是 1:N 关系（DB 预留多账号）。"""
    models_py = APP_DIR / "db" / "models.py"
    if not models_py.exists():
        return CheckResult("user_account_1n", False, "models.py not found")

    try:
        text = models_py.read_text(encoding="utf-8")
    except Exception as e:
        return CheckResult("user_account_1n", False, f"read failed: {e}")

    violations: list[str] = []

    # 检查 XhsAccount 有 user_id 外键指向 users.id
    if not re.search(
        r"ForeignKey\(\s*[\"']users\.id[\"']\s*,\s*ondelete\s*=\s*[\"']CASCADE[\"']",
        text,
    ):
        violations.append("XhsAccount 缺少指向 users.id 的外键")

    # 检查有 ix_xhs_accounts_user_id 索引
    if "ix_xhs_accounts_user_id" not in text:
        violations.append("XhsAccount 缺少 user_id 索引")

    if violations:
        return CheckResult(
            "user_account_1n",
            False,
            f"User:Account 关系异常: {violations}",
        )
    return CheckResult("user_account_1n", True, "User:Account = 1:N (外键 + 索引)")


# ----------------------------------------------------------------------
# 主入口
# ----------------------------------------------------------------------

def run_all_checks() -> int:
    """运行全部 7 项检查，返回退出码。"""
    checks = [
        check_harness_no_langgraph,
        check_no_websocket,
        check_no_memory_saver,
        check_copywrite_uses_r1,
        check_supervisor_uses_v3,
        check_no_plaintext_token,
        check_user_account_one_to_many,
    ]

    print("=" * 70)
    print("全局红线自检（手册 Phase 8 Part C）")
    print("=" * 70)
    print(f"Backend root: {BACKEND_DIR}")
    print()

    all_passed = True
    for fn in checks:
        result = fn()
        status = "[PASS]" if result.passed else "[FAIL]"
        print(f"{status} {result.name}: {result.detail}")
        if not result.passed:
            all_passed = False

    print()
    print("=" * 70)
    if all_passed:
        print("=== 全部红线检查通过 ===")
        return 0
    print("=== 存在红线违反，请修复后再发布 ===")
    return 1


if __name__ == "__main__":
    sys.exit(run_all_checks())
