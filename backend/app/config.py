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
        default="sqlite+aiosqlite:///./data/xhs_agent.db",
        description="异步数据库连接串（dev 默认 SQLite 零依赖；生产换 mysql+aiomysql:// 或 postgresql+asyncpg://）",
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

    # ===== LLM: OpenAI（GPT 系列，官方 API）=====
    openai_api_key: str = Field(default="", description="OpenAI API Key")
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-4o"

    # ===== LLM: Anthropic（Claude 系列，官方 API）=====
    # 需要 pip install anthropic；未安装时前端选择 Claude 会给出明确提示
    anthropic_api_key: str = Field(default="", description="Anthropic API Key（Claude）")
    anthropic_base_url: str = "https://api.anthropic.com"
    anthropic_model: str = "claude-3-5-sonnet-latest"

    # ===== LLM: Google Gemini（OpenAI 兼容端点）=====
    google_api_key: str = Field(default="", description="Google AI / Gemini API Key")
    google_base_url: str = "https://generativelanguage.googleapis.com/v1beta/openai/"
    google_model: str = "gemini-1.5-flash"

    # ===== LLM: Moonshot（Kimi，OpenAI 兼容端点）=====
    moonshot_api_key: str = Field(default="", description="Moonshot / Kimi API Key")
    moonshot_base_url: str = "https://api.moonshot.cn/v1"
    moonshot_model: str = "moonshot-v1-8k"

    # ===== LLM: 智谱 GLM（OpenAI 兼容端点）=====
    zhipu_api_key: str = Field(default="", description="智谱 GLM API Key")
    zhipu_base_url: str = "https://open.bigmodel.cn/api/paas/v4"
    zhipu_model: str = "glm-4-plus"

    # ===== LLM: 通义千问文本（DashScope OpenAI 兼容端点，复用百炼 Key）=====
    qwen_text_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    qwen_text_model: str = "qwen-max"

    # ===== 多平台内容源（ContentSource）=====
    # 数据源优先级：builtin（内置中文话题库，零网络依赖）> Reddit/HackerNews（官方 API，零风控）> 小红书（爬取，有风控风险）
    # 默认平台：决定工作流 search 节点从哪个平台拿数据
    default_source_platform: str = Field(
        default="builtin",
        description="默认数据源平台：builtin / tavily / sogou / zhihu / weibo / xiaohongshu_web / bilibili / douyin / pinterest / instagram / reddit / hackernews / xiaohongshu",
    )
    xhs_source_enabled: bool = Field(
        default=False,
        description="是否启用小红书内容源（默认关闭，风控风险）",
    )
    hotboard_enabled: bool = Field(
        default=True,
        description="是否启用可插拔热榜源（读 hotboard_sources.json，调 60s/xxapi 公益 API 拿实时热搜）",
    )
    http_proxy: str = Field(
        default="",
        alias="HTTP_PROXY",
        description=(
            "HTTP 代理地址（如 http://127.0.0.1:7897），供 httpx 访问国外 API（Reddit/HN/GitHub/Tavily/Serper）。"
            "为空不走代理。设为 'system' 时自动探测系统代理（HTTP_PROXY/HTTPS_PROXY 环境变量）"
        ),
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

    # ===== Serper API（Google SERP 数据，低价高质）=====
    # 申请地址：https://serper.dev/（2,500 次免费，无需信用卡）
    # 返回 Google 原始搜索结果（organic/knowledge graph/people-also-ask）
    # 用途：Tavily 额度用完后的降级备选 + 小红书全品类内容搜索
    serper_api_key: str = Field(default="", description="Serper API Key")

    # ===== Brave Search API（独立索引，差异化搜索）=====
    # 申请地址：https://brave.com/search/api/（2,000 次/月免费）
    # 独立爬虫索引，不依赖 Google，结果有差异化
    # 用途：交叉验证，覆盖 Google 未收录的小红书页面
    brave_api_key: str = Field(default="", description="Brave Search API Key")

    # ===== YouTube Data API v3 =====
    # 申请地址：https://console.cloud.google.com/apis/credentials（创建 API Key，启用 YouTube Data API v3）
    # 免费配额：10,000 单位/天（搜索一次 ~100 单位，约 100 次搜索/天）
    youtube_api_key: str = Field(default="", description="YouTube Data API v3 Key（可选）")

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

    # ===== 飞书集成 =====
    feishu_app_id: str = Field(default="", description="飞书自建应用 App ID")
    feishu_app_secret: str = Field(default="", description="飞书自建应用 App Secret")
    feishu_verification_token: str = Field(default="", description="飞书事件订阅验证令牌")
    feishu_encrypt_key: str = Field(default="", description="飞书事件订阅加密密钥")
    feishu_bitable_app_token: str = Field(default="", description="飞书多维表格 App Token")
    feishu_bitable_table_id: str = Field(default="", description="飞书多维表格 Table ID")
    feishu_oauth_redirect_uri: str = Field(
        default="http://localhost:8000/api/feishu/oauth/callback",
        description="飞书 OAuth 回调地址，必须与开放平台配置完全一致",
    )
    feishu_oauth_frontend_url: str = Field(
        default="http://localhost:5173",
        description="飞书 OAuth 完成后跳转的前端地址",
    )
    feishu_oauth_scopes: str = Field(
        default="offline_access wiki:wiki docx:document",
        description="飞书用户授权 scope，空格分隔",
    )

    # ===== CORS =====
    cors_origins_str: str = Field(
        default="http://localhost:5173,http://localhost:3000,http://localhost:3001,http://127.0.0.1:3001",
        alias="CORS_ORIGINS",
        description="CORS 允许的来源列表（逗号分隔），可通过 CORS_ORIGINS 环境变量覆盖",
    )

    # ===== High-risk permission allowlist =====
    permissions_allow: str = Field(
        default="",
        description="High-risk permissions allowed (comma separated), e.g. bash:exec,file:write",
    )

    # ===== Generic browser automation (G1-G4) =====
    browser_allowed_domains: str = Field(
        default="xiaohongshu.com",
        alias="BROWSER_ALLOWED_DOMAINS",
        description=(
            "通用浏览器自动化域名白名单（逗号分隔，域后缀匹配：填 a.com 即放行 "
            "a.com 与 *.a.com）。运行时可通过 POST /api/browser/domains 临时放行"
        ),
    )
    mcp_browser_token: str = Field(
        default="",
        alias="MCP_BROWSER_TOKEN",
        description="对外 MCP Server（/api/mcp/browser）的 Bearer token；为空则启动时自动生成并打印日志",
    )
    browser_proxy: str = Field(
        default="",
        alias="BROWSER_PROXY",
        description=(
            "worker Chromium 代理（如 http://127.0.0.1:7897）。为空不走代理。"
            "用于直连被 RST/超时的站点（如 GitHub）；设为 'system' 时自动探测"
            "系统代理。重启后端生效"
        ),
    )

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.cors_origins_str.split(",") if o.strip()]

    @property
    def browser_allowed_domain_list(self) -> list[str]:
        return [d.strip().lower() for d in self.browser_allowed_domains.split(",") if d.strip()]


@lru_cache
def get_settings() -> Settings:
    """单例配置，避免重复读取环境变量。"""
    return Settings()