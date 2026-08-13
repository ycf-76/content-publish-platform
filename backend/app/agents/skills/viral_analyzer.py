"""Layer 1 规则层：爆款分析（0 LLM 成本）。

职责：
- 计算派生指标：interaction_rate / viral_coefficient / quality_score
- 基于分位数的相对分类：粉丝型 / 内容型 / 双重型 / 普通
- 综合爆点分排序：viral_score = 0.5*rate_p + 0.3*viral_p + 0.2*likes_p

多平台数据兼容（三层降级）：
- fans>0（小红书/GitHub）→ 用 fans 做分母，走分位数分类
- fans=0 但 comments>0（Reddit/HN）→ 用 comments 做弱分母，走硬阈值分类
- fans=0 且 comments=0（Tavily）→ 标记 weak 信号，只按 likes 绝对值排序

红线：
- 不依赖 LLM，纯 Python 计算
- 样本量 < 5 时降级为硬阈值分类
- 不抛异常，失败降级为按 likes 排序
- 混合平台数据按平台分组分类，避免跨平台比较（小红书高赞 vs HN 低赞不可比）
"""

from __future__ import annotations

import logging
import math
from typing import Any

logger = logging.getLogger(__name__)


def _percentile(data: list[float], p: int) -> float:
    """简单分位数计算（不依赖 numpy）。"""
    if not data:
        return 0.0
    sorted_data = sorted(data)
    k = (len(sorted_data) - 1) * p / 100
    f = int(k)
    c = k - f
    if f + 1 < len(sorted_data):
        return sorted_data[f] + c * (sorted_data[f + 1] - sorted_data[f])
    return sorted_data[f]


def _percentile_rank(data: list[float], value: float) -> float:
    """返回 value 在 data 中的分位数排名（0-1）。"""
    if not data:
        return 0.0
    below = sum(1 for x in data if x <= value)
    return below / len(data)


def _has_fans_field(notes: list[dict]) -> bool:
    """检查样本是否包含有效的 author_fans 字段。"""
    valid_count = sum(
        1 for n in notes
        if n.get("author_fans") and n["author_fans"] > 0
    )
    return valid_count >= len(notes) * 0.5  # 50% 以上有粉丝数才算有效


def compute_metrics(note: dict) -> dict:
    """计算单条笔记的派生指标。

    多平台数据兼容（3 级降级）：
    1. fans>0  → 用 fans 做分母（小红书/GitHub）
    2. fans=0 但 comments>0 → 用 comments 做弱分母（Reddit/HN）
    3. fans=0 且 comments=0 → 标记 weak，interaction_rate/viral_coefficient 置 0（Tavily）
    """
    likes = max(note.get("likes", 0) or 0, 0)
    comments = max(note.get("comments", 0) or 0, 0)
    fans = max(note.get("author_fans", 0) or 0, 0)
    views = max(note.get("views", 0) or 0, 0)
    shares = max(note.get("shares", 0) or 0, 0)
    collects = max(note.get("collects", 0) or 0, 0)

    # 选择分母：优先 fans，缺失时用 comments，再缺失标记 weak
    if fans > 0:
        denominator = fans
        denom_source = "fans"
        signal_strength = "strong"
    elif comments > 0:
        denominator = comments
        denom_source = "comments"
        signal_strength = "medium"
    else:
        denominator = 1
        denom_source = "none"
        signal_strength = "weak"

    # 互动率 / 爆点系数：weak 信号时置 0，避免 likes/1 失真
    if signal_strength == "weak":
        interaction_rate = 0.0
        viral_coefficient = 0.0
    else:
        interaction_rate = likes / max(denominator, 1)
        viral_coefficient = likes / (math.sqrt(denominator) + 1)

    # 互动质量分：评论/点赞比，衡量内容深度（不依赖 fans）
    quality_score = comments / max(likes, 1)

    # 收藏率：内容实用性的核心信号（有 collects 时才算）
    collect_rate = collects / max(likes, 1) if collects else None

    return {
        **note,
        "_denominator_source": denom_source,
        "_signal_strength": signal_strength,
        "interaction_rate": round(interaction_rate, 4),
        "viral_coefficient": round(viral_coefficient, 2),
        "quality_score": round(quality_score, 4),
        "collect_rate": round(collect_rate, 4) if collect_rate is not None else None,
    }


def _classify_single_platform(notes: list[dict]) -> list[dict]:
    """对单一平台的笔记做分类（已按 platform 分组后调用）。

    分类策略按信号强度降级：
    1. strong（有 fans）→ 分位数分类 / 小样本硬阈值
    2. medium（有 comments 无 fans）→ 硬阈值降级（likes P75 为高互动门槛）
    3. weak（无 fans 无 comments）→ 全部标"普通"，让 viral_score 主导
    """
    if not notes:
        return notes

    # 检查信号强度
    has_fans = _has_fans_field(notes)
    has_comments = sum(1 for n in notes if (n.get("comments") or 0) > 0) >= len(notes) * 0.5

    # weak 信号：无 fans 无 comments，无法分类
    if not has_fans and not has_comments:
        for n in notes:
            n["viral_type"] = "普通"
            n["classification_note"] = "weak_signal_no_fans_no_comments"
        return notes

    # 提取样本
    fans_list = [n.get("author_fans", 0) or 0 for n in notes]
    rate_list = [n.get("interaction_rate", 0) or 0 for n in notes]

    # 样本量 < 5：降级为硬阈值
    if len(notes) < 5:
        # 经验硬阈值：1万粉为"大V"门槛，互动率 > 5% 为高互动
        # medium 信号（无 fans）时，用 likes 绝对值 P75 作高互动门槛
        if has_fans:
            for n in notes:
                is_big = n.get("author_fans", 0) > 10000
                is_high = n.get("interaction_rate", 0) > 0.05
                if is_big and not is_high:
                    n["viral_type"] = "粉丝型"
                elif not is_big and is_high:
                    n["viral_type"] = "内容型"
                elif is_big and is_high:
                    n["viral_type"] = "双重型"
                else:
                    n["viral_type"] = "普通"
                n["classification_note"] = "hard_threshold_small_sample"
        else:
            # medium 信号硬阈值：用 likes 中位数 *2 作高互动门槛
            likes_list = [n.get("likes", 0) or 0 for n in notes]
            likes_threshold = (_percentile(likes_list, 50) or 0) * 2
            for n in notes:
                is_high = n.get("likes", 0) > max(likes_threshold, 1)
                if is_high:
                    n["viral_type"] = "内容型"
                else:
                    n["viral_type"] = "普通"
                n["classification_note"] = "hard_threshold_medium_signal"
        return notes

    # 分位数分类（仅 strong 信号走分位数）
    if has_fans:
        fans_p75 = _percentile(fans_list, 75)
        rate_p75 = _percentile(rate_list, 75)

        for n in notes:
            is_big_author = (n.get("author_fans", 0) or 0) > fans_p75
            is_high_rate = (n.get("interaction_rate", 0) or 0) > rate_p75

            if is_big_author and not is_high_rate:
                n["viral_type"] = "粉丝型"
            elif not is_big_author and is_high_rate:
                n["viral_type"] = "内容型"
            elif is_big_author and is_high_rate:
                n["viral_type"] = "双重型"
            else:
                n["viral_type"] = "普通"
            n["classification_note"] = "percentile_p75"
    else:
        # medium 信号分位数：用 likes P75 作高互动门槛
        likes_list = [n.get("likes", 0) or 0 for n in notes]
        likes_p75 = _percentile(likes_list, 75)

        for n in notes:
            is_high = (n.get("likes", 0) or 0) > likes_p75
            if is_high:
                n["viral_type"] = "内容型"
            else:
                n["viral_type"] = "普通"
            n["classification_note"] = "percentile_likes_p75_medium_signal"

    return notes


def classify_viral_type(notes: list[dict]) -> list[dict]:
    """基于样本分布的相对分类，自适应不同类目。

    多平台数据兼容：
    - 按 platform 分组分类，避免跨平台比较（小红书高赞 vs HN 低赞不可比）
    - 每组内按信号强度降级：strong(fans) / medium(comments) / weak(none)
    - 样本量 < 5 时降级为硬阈值分类
    """
    if not notes:
        return notes

    # 按平台分组（单平台时直接走原逻辑，保持兼容）
    platforms = set(n.get("platform", "") for n in notes)
    if len(platforms) <= 1:
        return _classify_single_platform(notes)

    # 多平台：按 platform 分组各算各的
    for plat in platforms:
        plat_notes = [n for n in notes if n.get("platform", "") == plat]
        _classify_single_platform(plat_notes)

    return notes


def compute_viral_score(notes: list[dict]) -> list[dict]:
    """综合爆点分排序，优先内容型爆款，粉丝型噪音下沉。

    viral_score = 0.5*rate_percentile + 0.3*viral_percentile + 0.2*likes_percentile
    对粉丝型爆款施加 0.7 惩罚系数（让大V日常下沉）。

    多平台数据兼容：
    - weak 信号（无 fans 无 comments）→ 只按 likes_percentile 排序，避免失真分位数为 0
    - strong/medium 信号 → 走原有加权逻辑
    """
    if not notes:
        return notes

    rates = [n.get("interaction_rate", 0) or 0 for n in notes]
    virals = [n.get("viral_coefficient", 0) or 0 for n in notes]
    likes_list = [n.get("likes", 0) or 0 for n in notes]

    for n in notes:
        signal = n.get("_signal_strength", "strong")

        # 归一化到 0-1（用分位数，避免极值拉偏）
        rate_p = _percentile_rank(rates, n.get("interaction_rate", 0) or 0)
        viral_p = _percentile_rank(virals, n.get("viral_coefficient", 0) or 0)
        likes_p = _percentile_rank(likes_list, n.get("likes", 0) or 0)

        if signal == "weak":
            # weak 信号：rate/viral 都是 0，分位数排名无意义，只用 likes 排序
            base_score = likes_p
        else:
            # 加权：互动率权重最高（内容引爆信号）
            base_score = rate_p * 0.5 + viral_p * 0.3 + likes_p * 0.2

        # 粉丝型惩罚：大V日常水文下沉（仅当能分类时才惩罚）
        if n.get("viral_type") == "粉丝型":
            base_score *= 0.7
        # 内容型加权：可复制爆款上浮
        elif n.get("viral_type") == "内容型":
            base_score = min(1.0, base_score * 1.1)

        n["viral_score"] = round(base_score, 4)

    # 按 viral_score 降序
    notes.sort(key=lambda n: n.get("viral_score", 0), reverse=True)
    return notes


def analyze_viral(results: list[dict]) -> tuple[list[dict], dict]:
    """Layer 1 主入口：执行完整规则层分析。

    Args:
        results: search 节点返回的原始笔记列表

    Returns:
        (with_metrics, layer1_stats)
        - with_metrics: 带 viral_type / viral_score / 派生指标的 top N 笔记
        - layer1_stats: 分类统计 + 数据质量信息
    """
    if not results:
        return [], {
            "total": 0,
            "has_author_fans": False,
            "classification_method": "none",
            "type_distribution": {},
        }

    try:
        # ① 计算派生指标
        with_metrics = [compute_metrics(n) for n in results]

        # ② 分类
        with_metrics = classify_viral_type(with_metrics)

        # ③ 排序
        with_metrics = compute_viral_score(with_metrics)

        # 统计
        has_fans = _has_fans_field(results)
        type_dist: dict[str, int] = {}
        signal_dist: dict[str, int] = {}
        method = "none"
        for n in with_metrics:
            vt = n.get("viral_type", "普通")
            type_dist[vt] = type_dist.get(vt, 0) + 1
            sig = n.get("_signal_strength", "strong")
            signal_dist[sig] = signal_dist.get(sig, 0) + 1
        if with_metrics:
            method = with_metrics[0].get("classification_note", "unknown")

        stats = {
            "total": len(with_metrics),
            "has_author_fans": has_fans,
            "classification_method": method,
            "type_distribution": type_dist,
            "signal_distribution": signal_dist,
            "top_viral_score": with_metrics[0].get("viral_score", 0) if with_metrics else 0,
        }

        logger.info(
            f"[viral_analyzer] Layer1: {len(with_metrics)} notes, "
            f"has_fans={has_fans}, method={method}, "
            f"signal={signal_dist}, distribution={type_dist}"
        )
        return with_metrics, stats

    except Exception as e:
        logger.exception(f"[viral_analyzer] Layer1 failed: {e}")
        # 降级：按 likes 排序
        fallback = sorted(results, key=lambda n: n.get("likes", 0), reverse=True)
        return fallback, {
            "total": len(fallback),
            "has_author_fans": _has_fans_field(results),
            "classification_method": "fallback_likes_sort",
            "type_distribution": {},
            "error": str(e),
        }
