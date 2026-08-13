"""选题池监控模块配置。

继承项目全局 Settings（复用 database_url / deepseek_api_key / deepseek_base_url），
扩展选题池专用配置项。LLM_API_KEY 留空时自动复用 deepseek_api_key，
避免重复配置。
"""
from __future__ import annotations

from functools import lru_cache
from typing import List

from pydantic import Field

from app.config import Settings


class PoolSettings(Settings):
    """选题池监控配置（继承全局 Settings，读取同一份 .env）。"""

    # ===== 抓取调度 =====
    crawl_interval_minutes: int = Field(default=10, description="抓取间隔（分钟）")
    max_fetch_per_run: int = Field(default=10, description="单次抓取条数上限")
    max_pool_size: int = Field(default=200, description="池子最大容量")
    pool_min_threshold: int = Field(
        default=150, description="池子最低水位，低于此值触发紧急补抓"
    )
    pool_startup_threshold: int = Field(
        default=50, description="启动时若池子低于此值立即触发一次抓取"
    )

    # ===== 评分阈值 =====
    heat_score_threshold: float = Field(default=60.0, description="入池热度分阈值")
    score_likes_baseline: int = Field(
        default=5000, description="互动量满分基准（赞数达到此值得满分，小红书量级）"
    )
    # 各平台动态评分基准（不同平台互动量级差异大，统一基准会导致小众平台全被过滤）
    # 未列出的平台回退到 score_likes_baseline
    platform_score_baselines: dict = Field(
        default_factory=lambda: {
            "xiaohongshu": 5000,   # 小红书赞量级大
            "hackernews": 100,     # HN score 通常几十到几百，100+ 算热门
            "reddit": 500,         # Reddit score 几百到几千
            "tavily": 200,         # Tavily likes=score*1000，最多1000
            "builtin": 5000,       # 内置话题库预设互动量高
            "github": 500,         # GitHub stars 50+算热门，500+算很热门
        },
        description="各平台互动量满分基准（赞数达到此值得满分）",
    )

    # ===== 去重 =====
    simhash_hamming_threshold: int = Field(
        default=8, description="SimHash 汉明距离阈值，≤则视为重复（对应相似度 > 85%）"
    )

    # ===== 清理 =====
    cleanup_hour: int = Field(default=2, description="每日清理任务执行小时（0-23）")
    cleanup_expire_hours: int = Field(default=72, description="超过此小时数视为过期")
    cleanup_expire_score: float = Field(
        default=40.0, description="过期清理的热度分上限（< 此值且超时才删）"
    )

    # ===== LLM 分类 =====
    # 留空时自动复用全局 deepseek_api_key，避免重复配置
    llm_api_key: str = Field(
        default="", description="分类用 LLM API Key，留空则复用 deepseek_api_key"
    )
    llm_model: str = Field(default="deepseek-chat", description="分类用模型名")
    llm_timeout_seconds: int = Field(default=30, description="LLM 调用超时")

    # ===== 随机 UA 池 =====
    user_agent_list: List[str] = Field(
        default_factory=lambda: [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) "
            "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1",
        ],
        description="随机 UA 池（Playwright 抓取时使用）",
    )


@lru_cache
def get_pool_settings() -> PoolSettings:
    """单例配置，避免重复读取环境变量。"""
    return PoolSettings()


def get_effective_llm_api_key() -> str:
    """获取实际生效的 LLM API Key：优先 llm_api_key，否则复用 deepseek_api_key。"""
    s = get_pool_settings()
    return (s.llm_api_key or s.deepseek_api_key or "").strip()
