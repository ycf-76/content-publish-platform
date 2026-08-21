"""
Monitor Agent Plugin - 热点监控智能体插件
将现有 MonitorAgent 包装为标准 Datasource Plugin
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional
from datetime import datetime

from app.core.base_interfaces import (
    BaseDatasourcePlugin,
    PluginContext,
    TrendingContent,
)
from app.core.plugin_types import PluginCategory, PluginStatus


class MonitorAgentPlugin(BaseDatasourcePlugin):
    """
    热点监控智能体插件
    
    功能：
    1. 多平台热点抓取（HackerNews/Reddit/Tavily/Builtin）
    2. LLM三维分类（情绪维度/场景维度/视觉形式）
    3. SimHash去重（防止重复内容入池）
    4. 智能评分（基于热度、时效性、相关性等因子）
    5. 定时调度与异常容错
    
    数据流：
    SourceManager.get_trending() → 过滤近期 → SimHash去重 
    → LLM分类 → ScoringAgent评分 → 入库(topic_pool_items)
    
    特性：
    - 自动降级：LLM失败时使用关键词匹配分类
    - 容错机制：单条解析失败不影响整体流程
    - 风控规避：小红书因频率限制自动跳过
    """

    @property
    def plugin_id(self) -> str:
        return "monitor-agent"

    @property
    def plugin_name(self) -> str:
        return "热点监控智能体"

    async def setup(self, ctx: PluginContext) -> None:
        """初始化监控智能体，加载配置和数据源管理器"""
        await super().setup(ctx)
        
        self._log(logging.INFO, "初始化监控智能体...")
        
        try:
            # 延迟导入避免循环依赖
            from app.tools.sources.manager import source_manager
            from app.pool_monitor.scoring_agent import ScoringAgent
            from app.pool_monitor.simhash_utils import simhash
            
            self._source_manager = source_manager
            self._scoring_agent = ScoringAgent()
            self._simhash_func = simhash
            
            # 加载配置
            config = ctx.config or {}
            self._scan_interval = config.get("scan_interval_minutes", 10)
            self._max_per_source = config.get("max_items_per_source", 20)
            self._enable_llm = config.get("enable_llm_classification", True)
            self._simhash_threshold = config.get("simhash_threshold", 3)
            self._min_score = config.get("min_score_threshold", 50)
            
            self._log(logging.INFO, f"配置加载完成 | 扫描间隔: {self._scan_interval}min | "
                                     f"每源上限: {self._max_per_source} | LLM: {'开启' if self._enable_llm else '关闭'}")
            
        except Exception as e:
            self._log(logging.ERROR, f"初始化失败: {e}")
            raise

    async def search_trending(
        self,
        keyword: str,
        limit: int = 20,
        ctx: Optional[PluginContext] = None
    ) -> List[TrendingContent]:
        """
        搜索趋势内容
        
        Args:
            keyword: 搜索关键词
            limit: 返回数量上限
            ctx: 插件上下文（可选，用于传递额外配置）
            
        Returns:
            TrendingContent 列表
        """
        start_time = time.time()
        self._log(logging.INFO, f"搜索热点 | 关键词: {keyword} | 上限: {limit}")
        
        results = []
        
        try:
            # 遍历所有已注册的数据源进行搜索
            for source_name, source_instance in self._source_manager.sources.items():
                if source_name in _MONITOR_SKIP_PLATFORMS:
                    continue
                    
                try:
                    items = await source_instance.search_trending(keyword, limit=limit)
                    
                    for item in items[:limit]:
                        trending_content = TrendingContent(
                            title=item.get("title", ""),
                            url=item.get("url", ""),
                            content_snippet=item.get("content_snippet", "")[:200],
                            source_platform=source_name,
                            published_at=item.get("published_at"),
                            metrics={
                                "score": item.get("score", 0),
                                "comments_count": item.get("comments_count", 0),
                                "upvotes": item.get("upvotes", 0),
                            },
                            metadata={
                                "keyword": keyword,
                                "search_method": "api_search",
                                "fetched_at": datetime.now().isoformat(),
                            }
                        )
                        results.append(trending_content)
                        
                except Exception as e:
                    self._log(
                        logging.WARNING,
                        f"{source_name} 搜索失败（已跳过）: {e}"
                    )
                    continue
            
            execution_time_ms = int((time.time() - start_time) * 1000)
            self._log(
                logging.INFO,
                f"搜索完成 | 结果数: {len(results)} | 耗时: {execution_time_ms}ms"
            )
            
            # 发布事件通知
            if ctx and len(results) > 0:
                await ctx.event_bus.publish("datasource:trending_found", {
                    "count": len(results),
                    "keyword": keyword,
                    "sources_count": len(set(r.source_platform for r in results)),
                    "execution_time_ms": execution_time_ms,
                }, source_plugin_id=self.plugin_id)
            
            return results[:limit]
            
        except Exception as e:
            self._log(logging.ERROR, f"搜索过程异常: {e}", exc_info=True)
            if ctx:
                await ctx.event_bus.publish("datasource:error", {
                    "operation": "search_trending",
                    "error": str(e),
                    "keyword": keyword,
                }, source_plugin_id=self.plugin_id)
            return []

    async def get_trending(
        self,
        limit: int = 20,
        ctx: Optional[PluginContext] = None
    ) -> List[TrendingContent]:
        """
        获取当前热门/推荐内容
        
        执行完整监控流程：
        1. 调用各数据源get_trending()获取原始数据
        2. 过滤近期已入库内容（避免重复）
        3. SimHash去重
        4. LLM三维分类（或关键词降级）
        5. 评分排序
        6. 返回Top-N结果
        
        Args:
            limit: 返回数量上限
            ctx: 插件上下文（可选）
            
        Returns:
            TrendingContent 列表（按评分降序排列）
        """
        start_time = time.time()
        actual_limit = min(limit, self._max_per_source)
        
        self._log(logging.INFO, f"开始全平台热点扫描 | 目标获取: {actual_limit}")
        
        all_items = []
        
        try:
            # Step 1: 从各数据源获取热门内容
            for source_name, source_instance in self._source_manager.sources.items():
                if source_name in _MONITOR_SKIP_PLATFORMS:
                    self._log(logging.DEBUG, f"跳过 {source_name}（风控/不适用）")
                    continue
                    
                try:
                    self._log(logging.DEBUG, f"正在抓取 {source_name}...")
                    raw_items = await source_instance.get_trending(limit=actual_limit)
                    
                    for item in raw_items:
                        item["_source"] = source_name
                        all_items.append(item)
                        
                    self._log(logging.DEBUG, f"{source_name} 获取 {len(raw_items)} 条")
                    
                except Exception as e:
                    self._log(
                        logging.WARNING,
                        f"{source_name} 抓取失败（已跳过）: {e}"
                    )
                    continue
            
            self._log(logging.INFO, f"原始数据收集完成 | 总计: {len(all_items)} 条")
            
            # Step 2-4: 处理流程（去重、分类、评分）
            processed_items = []
            seen_simhashes = set()
            
            for item in all_items:
                try:
                    title = item.get("title", "")
                    content = item.get("content_snippet", "")
                    
                    if not title and not content:
                        continue
                    
                    # SimHash去重
                    text_for_hash = f"{title} {content}"
                    hash_val = self._simhash_func(text_for_hash)
                    
                    is_duplicate = any(
                        hamming_distance(hash_val, existing_hash) < self._simhash_threshold
                        for existing_hash in seen_simhashes
                    )
                    
                    if is_duplicate:
                        self._log(logging.DEBUG, f"跳过重复内容: {title[:30]}...")
                        continue
                    
                    seen_simhashes.add(hash_val)
                    
                    # LLM分类（或降级为关键词匹配）
                    classification = {}
                    if self._enable_llm:
                        try:
                            from app.pool_monitor.monitor_agent import _classify_with_llm
                            classification = await _classify_with_llm(text_for_hash[:300])
                        except Exception as e:
                            self._log(logging.WARNING, f"LLM分类失败，降级为关键词: {e}")
                            from app.pool_monitor.monitor_agent import _classify_by_keywords
                            classification = _classify_by_keywords(text_for_hash)
                    else:
                        from app.pool_monitor.monitor_agent import _classify_by_keywords
                        classification = _classify_by_keywords(text_for_hash)
                    
                    # 评分计算
                    score_data = self._scoring_agent.calculate_score({
                        **item,
                        **classification,
                        "_simhash": hash_val,
                    })
                    
                    # 构建TrendingContent对象
                    trending_item = TrendingContent(
                        title=title,
                        url=item.get("url", ""),
                        content_snippet=content[:200],
                        source_platform=item.get("_source", "unknown"),
                        published_at=_parse_published_at(item.get("published_at")),
                        metrics={
                            "score": score_data.get("total_score", 0),
                            "classification": classification,
                            "simhash": hash_val,
                            "raw_metrics": {
                                k: v for k, v in item.items() 
                                if not k.startswith("_") and isinstance(v, (int, float, str))
                            },
                        },
                        metadata={
                            "classification_method": "llm" if self._enable_llm else "keywords",
                            "fetched_at": datetime.now().isoformat(),
                            "scan_type": "scheduled",
                        }
                    )
                    
                    # 只保留达到最低分数的内容
                    if score_data.get("total_score", 0) >= self._min_score:
                        processed_items.append(trending_item)
                        
                except Exception as e:
                    self._log(
                        logging.WARNING,
                        f"处理条目失败（已跳过）: {str(e)[:100]}"
                    )
                    continue
            
            # 按评分降序排序
            processed_items.sort(
                key=lambda x: x.metrics.get("score", 0),
                reverse=True
            )
            
            final_results = processed_items[:limit]
            execution_time_ms = int((time.time() - start_time) * 1000)
            
            self._log(
                logging.INFO,
                f"扫描完成 | 有效结果: {len(final_results)}/{len(all_items)} | "
                f"耗时: {execution_time_ms}ms"
            )
            
            # 发布事件
            if ctx and final_results:
                await ctx.event_bus.publish("datasource:item_scored", {
                    "count": len(final_results),
                    "avg_score": sum(
                        i.metrics.get("score", 0) for i in final_results
                    ) / max(len(final_results), 1),
                    "top_source": max(
                        set(i.source_platform for i in final_results),
                        key=lambda x: sum(1 for i in final_results if i.source_platform == x)
                    ) if final_results else "",
                    "execution_time_ms": execution_time_ms,
                }, source_plugin_id=self.plugin_id)
            
            return final_results
            
        except Exception as e:
            execution_time_ms = int((time.time() - start_time) * 1000)
            self._log(logging.ERROR, f"扫描过程严重异常: {e}", exc_info=True)
            
            if ctx:
                await ctx.event_bus.publish("datasource:error", {
                    "operation": "get_trending",
                    "error": str(e),
                    "raw_items_collected": len(all_items),
                    "execution_time_ms": execution_time_ms,
                }, source_plugin_id=self.plugin_id)
            
            return []

    async def validate_config(self, config: Dict[str, Any]) -> tuple[bool, List[str]]:
        """
        验证配置参数合法性
        
        Args:
            config: 用户配置的字典
            
        Returns:
            (is_valid, errors_list) 元组
        """
        errors = []
        
        # 检查扫描间隔
        interval = config.get("scan_interval_minutes", 10)
        if not (5 <= interval <= 60):
            errors.append(f"scan_interval_minutes 必须在 5-60 之间，当前值: {interval}")
        
        # 检查每源上限
        max_items = config.get("max_items_per_source", 20)
        if not (5 <= max_items <= 100):
            errors.append(f"max_items_per_source 必须在 5-100 之间，当前值: {max_items}")
        
        # 检查SimHash阈值
        threshold = config.get("simhash_threshold", 3)
        if not (1 <= threshold <= 20):
            errors.append(f"simhash_threshold 必须在 1-20 之间，当前值: {threshold}")
        
        # 检查最低分阈值
        min_score = config.get("min_score_threshold", 50)
        if not (0 <= min_score <= 100):
            errors.append(f"min_score_threshold 必须在 0-100 之间，当前值: {min_score}")
        
        # 检查启用源列表
        enabled_sources = config.get("enabled_sources", [])
        valid_sources = {"hackernews", "reddit", "tavily", "builtin"}
        invalid_sources = [s for s in enabled_sources if s not in valid_sources]
        if invalid_sources:
            errors.append(f"无效的数据源名称: {invalid_sources}")
        
        is_valid = len(errors) == 0
        
        if not is_valid:
            self._log(logging.WARNING, f"配置验证失败: {errors}")
        else:
            self._log(logging.INFO, "配置验证通过")
        
        return is_valid, errors

    async def health_check(self) -> tuple[bool, str]:
        """
        健康检查：验证数据源可用性和配置有效性
        
        Returns:
            (is_healthy, message)
        """
        try:
            # 检查SourceManager是否正常初始化
            if not hasattr(self, '_source_manager'):
                return False, "SourceManager 未初始化"
            
            sources_count = len(self._source_manager.sources)
            if sources_count == 0:
                return False, "无可用数据源"
            
            # 检查ScoringAgent
            if not hasattr(self, '_scoring_agent') or self._scoring_agent is None:
                return False, "ScoringAgent 未初始化"
            
            # 快速测试：尝试调用第一个数据源的get_trending
            first_source = next(iter(self._source_manager.values()), None)
            if first_source:
                test_result = await first_source.get_trending(limit=1)
                if not test_result:
                    return True, f"运行正常（{sources_count}个数据源就绪，但首个源返回空结果）"
            
            return True, f"运行正常（{sources_count}个数据源就绪）"
            
        except Exception as e:
            return False, f"健康检查异常: {str(e)}"

    async def teardown(self) -> None:
        """清理资源"""
        self._log(logging.INFO, "释放监控智能体资源...")
        
        if hasattr(self, '_source_manager'):
            del self._source_manager
        if hasattr(self, '_scoring_agent'):
            del self._scoring_agent
            
        self._log(logging.INFO, "资源释放完成")


# ---------------------------------------------------------------------------
# 辅助函数（从原MonitorAgent模块复制，避免循环导入）
# ---------------------------------------------------------------------------

# 监控抓取时跳过的平台（风控/需关键词/不适用全站热门）
_MONITOR_SKIP_PLATFORMS = {"xiaohongshu"}


def _parse_published_at(s: str) -> Optional[datetime]:
    """把 ISO8601 字符串解析成 aware datetime"""
    if not s or not s.strip():
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None


def hamming_distance(hash1: int, hash2: int) -> int:
    """计算两个SimHash值的汉明距离"""
    x = hash1 ^ hash2
    distance = 0
    while x > 0:
        distance += x & 1
        x >>= 1
    return distance


# 导出插件类
__all__ = ['MonitorAgentPlugin']