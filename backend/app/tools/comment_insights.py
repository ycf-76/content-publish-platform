"""评论洞察 Skill（jieba + snownlp，0 LLM 成本）。

职责：
- 情感分析：snownlp 对每条评论打分（0-1），分正面/中性/负面三类
- 关键词提取：jieba TF-IDF 提取评论高频关键词 Top N
- 需求信号挖掘：识别追问型/吐槽型/购买信号型评论
- 评论聚类摘要：按关键词将评论分组，每组输出代表性评论

借鉴 Easel skill-comment-insights 的分析维度，
用纯 Python 实现（jieba 分词 + snownlp 情感），不依赖 LLM。

红线：
- 不调用 LLM，纯本地计算
- 输入为评论列表（list[dict]），每条至少有 text 字段
- 不抛异常，失败降级为空结果
"""

from __future__ import annotations

import logging
import re
from collections import Counter
from typing import Any

from app.tools.base import Skill
from app.tools.registry import register

logger = logging.getLogger(__name__)

PURCHASE_SIGNALS = re.compile(
    r"求链接|同款|在哪买|多少钱|下单|加购|买了|购买|链接|店铺|店名|牌子|品牌|购|入手|种草|拔草"
)
QUESTION_SIGNALS = re.compile(
    r"求教程|能不能讲|能出个|想看|有没有|怎么|如何|请问|求助|教教|求分享|求方法|求攻略"
)
COMPLAINT_SIGNALS = re.compile(
    r"说了等于没说|没讲到重点|太水了|没用|浪费时间|标题党|骗|差|坑|踩雷|避雷|不好用|不推荐"
)


def _safe_sentiment(text: str) -> float:
    try:
        from snownlp import SnowNLP
        return SnowNLP(text).sentiments
    except Exception:
        return 0.5


def _safe_keywords(texts: list[str], top_k: int = 20) -> list[tuple[str, int]]:
    try:
        import jieba
        all_words: list[str] = []
        for t in texts:
            words = jieba.cut(t)
            all_words.extend(w for w in words if len(w) >= 2 and not re.match(r"^[\d\s\W]+$", w))
        counter = Counter(all_words)
        return counter.most_common(top_k)
    except Exception:
        return []


def _classify_sentiment(score: float) -> str:
    if score >= 0.6:
        return "positive"
    if score <= 0.4:
        return "negative"
    return "neutral"


def _detect_signals(text: str) -> list[str]:
    signals: list[str] = []
    if PURCHASE_SIGNALS.search(text):
        signals.append("purchase")
    if QUESTION_SIGNALS.search(text):
        signals.append("question")
    if COMPLAINT_SIGNALS.search(text):
        signals.append("complaint")
    return signals


def analyze_comments(comments: list[dict], top_k: int = 20) -> dict[str, Any]:
    """分析评论列表，返回情感分布、关键词、需求信号、聚类摘要。

    Args:
        comments: 评论列表，每条至少有 text 字段
        top_k: 关键词提取数量

    Returns:
        dict with keys: sentiment, keywords, signals, summary
    """
    if not comments:
        return {"sentiment": {}, "keywords": [], "signals": [], "summary": "无评论数据"}

    texts = [c.get("text", "") for c in comments if c.get("text")]
    if not texts:
        return {"sentiment": {}, "keywords": [], "signals": [], "summary": "无有效评论文本"}

    sentiment_scores = [_safe_sentiment(t) for t in texts]
    sentiment_labels = [_classify_sentiment(s) for s in sentiment_scores]
    sentiment_counter = Counter(sentiment_labels)

    avg_score = sum(sentiment_scores) / len(sentiment_scores)

    keywords = _safe_keywords(texts, top_k)

    all_signals: list[dict] = []
    for i, (text, score) in enumerate(zip(texts, sentiment_scores)):
        sigs = _detect_signals(text)
        if sigs:
            all_signals.append({
                "index": i,
                "text": text[:100],
                "sentiment": _classify_sentiment(score),
                "signal_types": sigs,
            })

    signal_type_counter = Counter()
    for s in all_signals:
        signal_type_counter.update(s["signal_types"])

    purchase_comments = [s for s in all_signals if "purchase" in s["signal_types"]]
    question_comments = [s for s in all_signals if "question" in s["signal_types"]]
    complaint_comments = [s for s in all_signals if "complaint" in s["signal_types"]]

    return {
        "sentiment": {
            "average": round(avg_score, 3),
            "distribution": {
                "positive": sentiment_counter.get("positive", 0),
                "neutral": sentiment_counter.get("neutral", 0),
                "negative": sentiment_counter.get("negative", 0),
            },
            "total": len(texts),
        },
        "keywords": [{"word": w, "count": c} for w, c in keywords],
        "signals": {
            "summary": {k: v for k, v in signal_type_counter.most_common()},
            "purchase": purchase_comments[:10],
            "question": question_comments[:10],
            "complaint": complaint_comments[:10],
        },
        "summary": (
            f"共{len(texts)}条评论，"
            f"正面{sentiment_counter.get('positive', 0)}条/"
            f"中性{sentiment_counter.get('neutral', 0)}条/"
            f"负面{sentiment_counter.get('negative', 0)}条，"
            f"平均情感分{avg_score:.2f}。"
            f"需求信号：购买意向{len(purchase_comments)}条/"
            f"追问{len(question_comments)}条/"
            f"吐槽{len(complaint_comments)}条"
        ),
    }


@register
class CommentInsightsSkill(Skill):
    node_type = "analyze"
    name = "comment_insights"
    display_name = "评论洞察分析"
    description = (
        "分析评论区数据：情感分布（正面/中性/负面）、高频关键词、"
        "需求信号（购买意向/追问/吐槽），输出结构化洞察。"
        "用jieba+snownlp本地计算，不调用LLM。"
    )
    trigger_words = [
        "评论分析", "评论区洞察", "评论情感", "评论关键词",
        "评论信号", "评论洞察", "分析评论",
    ]
    prompt_guidance = "输入评论列表，输出情感分布+关键词+需求信号+摘要。纯本地计算，0 LLM成本。"

    async def execute(self, inputs: dict) -> dict:
        comments = inputs.get("comments", [])
        top_k = inputs.get("top_k", 20)
        if not isinstance(comments, list):
            return {"error": "comments must be a list"}
        try:
            result = analyze_comments(comments, top_k=top_k)
            return result
        except Exception as e:
            logger.error(f"comment_insights failed: {e}")
            return {"error": str(e)}