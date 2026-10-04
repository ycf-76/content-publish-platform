"""OS 原生沙箱包（Windows L1：Low IL + ML 标签 + Job Object）。

公开接口见 win_native.py。使用方式：
    from app.sandbox import spawn_sandboxed, init_sandbox, build_env_block
"""

from app.sandbox.win_native import (
    SandboxError,
    SandboxResult,
    build_env_block,
    build_low_integrity_token,
    create_job_object,
    default_workspace_root,
    init_sandbox,
    label_dir_low_writable,
    label_file_no_read_up,
    label_tree_low_writable,
    spawn_sandboxed,
)

__all__ = [
    "SandboxError",
    "SandboxResult",
    "build_env_block",
    "build_low_integrity_token",
    "create_job_object",
    "default_workspace_root",
    "init_sandbox",
    "label_dir_low_writable",
    "label_file_no_read_up",
    "label_tree_low_writable",
    "spawn_sandboxed",
]
