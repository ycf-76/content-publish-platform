"""应用配置：使用 pydantic-settings 读取环境变量。

所有敏感信息（API Key、数据库连接、加密密钥等）均通过环境变量注入，
严禁硬编码。详见 .env.example。
"""

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """全局配置，从环境变量 / .env 读取。"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        populate_by_name=True,
    )

    # ===== 应用 =====
    app_name: str = "multi-agent-xhs-platform"
    debug: bool = False
    environment: Literal["dev", "test", "prod"] = "dev"

    # ===== 数据库 =====
    database_url: str = Field(
        default="mysql+aiomysql://root:@127.0.0.1:3306/xhs_agent?charset=utf8mb4",
        description="异步数据库连接串（MySQL/PostgreSQL/SQLite 均可）",
    )
    db_pool_size: int = Field(default=20, description="数据库连接池大小")
    db_max_overflow: int = Field(default=40, description="连接池最大溢出")
    db_echo: bool = False

    # ===== LLM: DeepSeek =====
    deepseek_api_key: str = Field(default="", description="DeepSeek API Key")
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model_v3: str = "deepseek-chat"
    deepseek_model_r1: str = "deepseek-reasoner"

    # ===== 阿里云百炼 (Qwen-VL + 通义万相) =====
    dashscope_api_key: str = Field(default="", description="阿里云百炼 API Key")
    qwen_vl_model: str = "qwen-vl-max"
    # 通义万相文生图模型：
    # - wanx2.1-t2i-turbo：性价比最高，0.14元/张（推荐，新用户有500张免费额度）
    # - wanx2.1-t2i-plus：高质量版，0.20元/张
    # - wanx-v1：旧版，0.16元/张
    # - wan2.2-t2i-flash：2.2极速版，速度提升50%
    wanx_model: str = "wanx2.1-t2i-turbo"
    jimeng_api_key: str = Field(default="", description="即梦 API Key（备用生图）")

    # ===== 小红书 MCP =====
    xhs_mcp_plugin_url: str = Field(
        default="",
        description="浏览器插件 MCP 服务地址（HTTP），留空表示不可用",
    )
    xhs_mcp_local_cmd: str = Field(
        default="",
        description="社区 MCP 本地启动命令，留空表示不可用",
    )
    xhs_mcp_mode: Literal["plugin", "local", "disabled"] = "plugin"
    mcp_plugin_enabled: bool = Field(default=True, description="是否启用浏览器插件 MCP")

    # ===== 多平台内容源（ContentSource）=====
    # 数据源优先级：builtin（内置中文话题库，零网络依赖）> Reddit/HackerNews（官方 API，零风控）> 小红书（爬取，有风控风险）
    # 默认平台：决定工作流 search 节点从哪个平台拿数据
    default_source_platform: str = Field(
        default="builtin",
        description="默认数据源平台：builtin / tavily / zhihu / weibo / xiaohongshu_web / bilibili / douyin / pinterest / instagram / reddit / hackernews / xiaohongshu",
    )
    xhs_source_enabled: bool = Field(
        default=False,
        description="是否启用小红书内容源（默认关闭，风控风险）",
    )

    # ===== Reddit API（OAuth2 personal use script）=====
    # 申请地址：https://www.reddit.com/prefs/apps（选 script 类型）
    reddit_client_id: str = Field(default="", description="Reddit app client_id")
    reddit_client_secret: str = Field(default="", description="Reddit app client_secret")
    reddit_username: str = Field(
        default="",
        description="Reddit 用户名（script app 模式必需，用于搜索）",
    )
    reddit_password: str = Field(
        default="",
        description="Reddit 密码（script app 模式必需）",
    )

    # ===== Tavily API（全网搜索，专为 AI Agent 设计）=====
    # 申请地址：https://app.tavily.com/（新用户有免费额度）
    # 配置后搜索节点会用 Tavily 做全网搜索（Google/Bing 级覆盖面）
    tavily_api_key: str = Field(default="", description="Tavily API Key")

    # ===== GitHub API（开源项目/技术工具热点）=====
    # 无 token 时限速 60次/小时（监控10分钟一次足够）；配 token 提升到 5000次/小时
    # 申请地址：https://github.com/settings/tokens（选 classic token，无需任何 scope）
    github_token: str = Field(default="", description="GitHub Personal Access Token（可选）")

    # ===== 加密 =====
    aes_secret_key: str = Field(
        default="",
        description="AES-GCM 加密密钥（32 字节 base64），用于加密小红书 Token/Session",
    )
    jwt_secret_key: str = Field(default="", description="JWT 签名密钥")
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 30
    jwt_refresh_expire_days: int = 7

    # ===== LangGraph =====
    langgraph_checkpoint_table: str = "langgraph_checkpoints"
    recovery_max_attempts: int = 3
    recovery_circuit_failure_threshold: int = 5
    recovery_circuit_recovery_timeout: int = 60
    structural_recovery_timeout_seconds: int = 1800

    # ===== LangSmith =====
    langchain_tracing_v2: bool = Field(
        default=False,
        description="启用 LangSmith v2 追踪（所有 LangGraph 运行自动上报）",
    )
    langchain_api_key: str = Field(
        default="",
        description="LangSmith API Key（https://smith.langchain.com/ 注册获取）",
    )
    langchain_project: str = Field(
        default="multi-agent-xhs-platform",
        description="LangSmith 项目名称（控制台中分组展示）",
    )
    langchain_endpoint: str = Field(
        default="https://api.smith.langchain.com",
        description="LangSmith 服务端点（自部署时修改）",
    )

    # ===== SSE =====
    sse_heartbeat_seconds: int = 15
    sse_event_buffer_limit: int = 1000

    # ===== SMTP（邮箱验证码发送）=====
    smtp_host: str = Field(default="", description="SMTP 服务器地址（如 smtp.qq.com / smtp.gmail.com）")
    smtp_port: int = Field(default=465, description="SMTP 端口（SSL 默认 465，TLS 默认 587）")
    smtp_user: str = Field(default="", description="SMTP 登录用户名（通常就是邮箱地址）")
    smtp_pass: str = Field(default="", description="SMTP 登录密码或授权码")
    smtp_from: str = Field(default="", description="发件人地址（留空则用 smtp_user）")
    smtp_use_tls: bool = Field(default=False, description="是否使用 STARTTLS（端口 587 时通常为 True）")

    # ===== Redis =====
    redis_url: str = Field(
        default="redis://127.0.0.1:6379/0",
        description="Redis 连接地址（留空则使用内存降级缓存）",
    )
    redis_password: str = Field(default="", description="Redis 密码（留空表示无密码）")
    redis_db: int = Field(default=0, description="Redis 数据库编号（0-15）")
    redis_pool_size: int = Field(default=20, description="Redis 连接池大小")

    # ===== CORS =====
    cors_origins_str: str = Field(
        default="http://localhost:5173,http://localhost:3000,http://localhost:3001,http://127.0.0.1:3001",
        alias="CORS_ORIGINS",
        description="CORS 允许的来源列表（逗号分隔），可通过 CORS_ORIGINS 环境变量覆盖",
    )

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.cors_origins_str.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    """单例配置，避免重复读取环境变量。"""
    return Settings()