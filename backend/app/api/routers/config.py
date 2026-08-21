"""Config routers."""

import os
from pathlib import Path

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.api.deps import get_current_user
from app.api.schemas.common import StandardResponse
from app.config import get_settings

router = APIRouter(prefix="/api/agents", tags=["config"])


class LLMConfigResponse(BaseModel):
    deepseek_api_key_set: bool = Field(description="DeepSeek API Key 是否已配置")
    deepseek_base_url: str = Field(description="DeepSeek API Base URL")
    deepseek_model_v3: str = Field(description="DeepSeek V3 模型名称")
    deepseek_model_r1: str = Field(description="DeepSeek R1 模型名称")
    dashscope_api_key_set: bool = Field(description="阿里云百炼 API Key 是否已配置")
    qwen_vl_model: str = Field(description="通义千问 VL 模型名称")
    wanx_model: str = Field(description="通义万相文生图模型名称")


class DeepSeekConfigUpdate(BaseModel):
    deepseek_api_key: str = Field(default="", description="DeepSeek API Key")
    deepseek_base_url: str = Field(default="", description="DeepSeek API Base URL")
    deepseek_model_v3: str = Field(default="", description="DeepSeek V3 模型名称")
    deepseek_model_r1: str = Field(default="", description="DeepSeek R1 模型名称")


class DashscopeConfigUpdate(BaseModel):
    dashscope_api_key: str = Field(default="", description="阿里云百炼 API Key")
    qwen_vl_model: str = Field(default="", description="通义千问 VL 模型名称")
    wanx_model: str = Field(default="", description="通义万相文生图模型名称")


def _update_env_file(updates: dict[str, str]) -> None:
    env_path = Path(__file__).resolve().parent.parent.parent.parent / ".env"
    raw_lines: list[str] = []
    key_line_map: dict[str, int] = {}

    if env_path.exists():
        for idx, line in enumerate(env_path.read_text(encoding="utf-8").splitlines()):
            raw_lines.append(line)
            stripped = line.strip()
            if stripped and not stripped.startswith("#") and "=" in stripped:
                key = stripped.split("=", 1)[0].strip()
                key_line_map[key] = idx

    for key, value in updates.items():
        if not value:
            continue
        if key in key_line_map:
            raw_lines[key_line_map[key]] = f"{key}={value}"
        else:
            raw_lines.append(f"{key}={value}")

    with open(env_path, "w", encoding="utf-8") as f:
        for line in raw_lines:
            f.write(line + "\n")

    for key, value in updates.items():
        if value:
            os.environ[key] = value

    get_settings.cache_clear()


@router.get("/configs")
async def list_agent_configs() -> StandardResponse[list[dict]]:
    """List all agent configurations."""
    return StandardResponse(data=[])


@router.put("/configs/{agent_id}")
async def update_agent_config(
    agent_id: str,
    config: dict,
) -> StandardResponse[dict]:
    """Update agent configuration."""
    return StandardResponse(data={}, message="Config updated")


@router.get("/llm-config")
async def get_llm_config(
    user_id: str = Depends(get_current_user),
) -> StandardResponse[LLMConfigResponse]:
    """获取 LLM 配置（API Key 只返回是否已设置，不返回明文）"""
    s = get_settings()
    return StandardResponse(data=LLMConfigResponse(
        deepseek_api_key_set=bool(s.deepseek_api_key),
        deepseek_base_url=s.deepseek_base_url,
        deepseek_model_v3=s.deepseek_model_v3,
        deepseek_model_r1=s.deepseek_model_r1,
        dashscope_api_key_set=bool(s.dashscope_api_key),
        qwen_vl_model=s.qwen_vl_model,
        wanx_model=s.wanx_model,
    ))


@router.put("/llm-config/deepseek")
async def update_deepseek_config(
    request: DeepSeekConfigUpdate,
    user_id: str = Depends(get_current_user),
) -> StandardResponse[dict]:
    """保存 DeepSeek 配置到 .env 文件"""
    updates = {}
    if request.deepseek_api_key:
        updates["DEEPSEEK_API_KEY"] = request.deepseek_api_key
    if request.deepseek_base_url:
        updates["DEEPSEEK_BASE_URL"] = request.deepseek_base_url
    if request.deepseek_model_v3:
        updates["DEEPSEEK_MODEL_V3"] = request.deepseek_model_v3
    if request.deepseek_model_r1:
        updates["DEEPSEEK_MODEL_R1"] = request.deepseek_model_r1

    if updates:
        _update_env_file(updates)

    return StandardResponse(data={"updated": list(updates.keys())}, message="DeepSeek 配置已保存")


@router.put("/llm-config/dashscope")
async def update_dashscope_config(
    request: DashscopeConfigUpdate,
    user_id: str = Depends(get_current_user),
) -> StandardResponse[dict]:
    """保存阿里云百炼配置到 .env 文件"""
    updates = {}
    if request.dashscope_api_key:
        updates["DASHSCOPE_API_KEY"] = request.dashscope_api_key
    if request.qwen_vl_model:
        updates["QWEN_VL_MODEL"] = request.qwen_vl_model
    if request.wanx_model:
        updates["WANX_MODEL"] = request.wanx_model

    if updates:
        _update_env_file(updates)

    return StandardResponse(data={"updated": list(updates.keys())}, message="阿里云百炼配置已保存")