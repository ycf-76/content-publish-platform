"""社媒文案字数统计与目标字数校验（纯标准库）。

借鉴 Easel wordcount.py 的统计口径和校验逻辑，
适配我们的项目：作为库函数供 copywrite 后处理管线调用。

口径：社媒主要看"计数字符数"，
即中文字符 + 英文单词（每个英文词计 1）+ 数字串（每串计 1），
这也是微博/小红书等平台的常见计法。
"""

import re

_CJK = (
    r"㐀-䶿"
    r"一-鿿"
    r"豈-﫿"
    r"\U00020000-\U0002ffff"
)
_CJK_RE = re.compile(f"[{_CJK}]")
_WORD_RE = re.compile(r"[A-Za-z]+(?:['\-][A-Za-z]+)*")
_NUM_RE = re.compile(r"\d+(?:[.,]\d+)*")
_PUNCT_RE = re.compile(f"[^\\s0-9A-Za-z{_CJK}]")


def count(text: str) -> dict:
    """统计文本各口径字数。"""
    cjk = len(_CJK_RE.findall(text))
    en_words = len(_WORD_RE.findall(text))
    num_groups = len(_NUM_RE.findall(text))
    punct = len(_PUNCT_RE.findall(text))
    total_chars = len(text)
    no_space_chars = len(re.sub(r"\s", "", text))
    social = cjk + en_words + num_groups + punct
    return {
        "cjk_chars": cjk,
        "en_words": en_words,
        "num_groups": num_groups,
        "punct": punct,
        "total_chars": total_chars,
        "no_space_chars": no_space_chars,
        "social_count": social,
    }


def check(text: str, target: int, tolerance: float = 0.05, metric: str = "social_count") -> dict:
    """校验文本是否命中目标字数 ±tolerance。"""
    stats = count(text)
    actual = stats[metric]
    margin = round(target * tolerance)
    low = target - margin
    high = target + margin

    if actual < low:
        status = "under"
        diff = low - actual
        advice = f"少了，至少再补 {diff} 字（当前 {actual}，下限 {low}）"
    elif actual > high:
        status = "over"
        diff = actual - high
        advice = f"超了，至少再删 {diff} 字（当前 {actual}，上限 {high}）"
    else:
        status = "ok"
        diff = 0
        advice = f"达标（{low} ≤ {actual} ≤ {high}）"

    return {
        "pass": status == "ok",
        "status": status,
        "metric": metric,
        "target": target,
        "tolerance": tolerance,
        "range": [low, high],
        "actual": actual,
        "adjust": diff,
        "advice": advice,
        "stats": stats,
    }


XHS_CONTENT_LIMITS = {
    "title_max": 20,
    "content_soft_max": 600,
    "content_hard_max": 1000,
}


def check_xhs(title: str, content: str) -> dict:
    """小红书平台字数校验快捷方法。"""
    title_stats = count(title)
    content_stats = count(content)
    limits = XHS_CONTENT_LIMITS

    title_ok = title_stats["social_count"] <= limits["title_max"]
    content_soft = content_stats["social_count"] <= limits["content_soft_max"]
    content_hard = content_stats["social_count"] <= limits["content_hard_max"]

    return {
        "title": {
            "count": title_stats["social_count"],
            "max": limits["title_max"],
            "ok": title_ok,
        },
        "content": {
            "count": content_stats["social_count"],
            "soft_max": limits["content_soft_max"],
            "hard_max": limits["content_hard_max"],
            "soft_ok": content_soft,
            "hard_ok": content_hard,
        },
        "pass": title_ok and content_hard,
    }


def selftest() -> bool:
    failed = 0
    s = count("你好世界")
    if not (s["cjk_chars"] == 4 and s["social_count"] == 4):
        failed += 1
    s = count("Hello world")
    if not (s["en_words"] == 2 and s["social_count"] == 2):
        failed += 1
    s = count("我有 3 只猫 and 2 dogs")
    if not (s["cjk_chars"] == 4 and s["en_words"] == 2 and s["num_groups"] == 2):
        failed += 1
    c = check("你好世界", target=4, tolerance=0.05)
    if not c["pass"]:
        failed += 1
    c = check("你好世界", target=10, tolerance=0.05)
    if c["pass"]:
        failed += 1
    xhs = check_xhs("短标题", "这是一段正文内容")
    if not xhs["pass"]:
        failed += 1
    if failed:
        print(f"wordcount selftest failed: {failed}", flush=True)
        return False
    print("wordcount selftest passed", flush=True)
    return True