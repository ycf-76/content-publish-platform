"""SimHash 64位指纹计算与相似度比较。

自实现（不引入第三方依赖）：
1. 文本分词（中文 2-gram + 英文按词），提升语义粒度
2. 每个 token 计算 MD5 取前 64 位作为哈希
3. 按位投票累加（位为1则 +1，为0则 -1）
4. 归一化符号（>0 取1，否则取0）得到 64 位指纹
5. 汉明距离 ≤ 阈值（默认 8）视为相似，对应相似度 > 85%
"""
from __future__ import annotations

import hashlib
import re

_WORD_RE = re.compile(r"[\w\u4e00-\u9fa5]+", re.UNICODE)


def _tokenize(text: str) -> list[str]:
    """分词：中文连续段做 2-gram，英文按整词，单字符直接保留。"""
    tokens: list[str] = []
    for raw in _WORD_RE.findall(text or ""):
        if len(raw) <= 1:
            tokens.append(raw)
            continue
        for i in range(len(raw) - 1):
            tokens.append(raw[i : i + 2])
        tokens.append(raw)
    return tokens


def _hash64(token: str) -> int:
    """对单个 token 计算 64 位哈希（MD5 前 16 个十六进制位）。"""
    h = hashlib.md5(token.encode("utf-8")).hexdigest()
    return int(h[:16], 16)


def simhash(text: str) -> str:
    """计算文本的 64 位 SimHash 指纹，返回 16 位十六进制字符串。"""
    tokens = _tokenize(text)
    if not tokens:
        return "0" * 16

    v = [0] * 64
    for tok in tokens:
        h = _hash64(tok)
        for i in range(64):
            v[i] += 1 if (h >> i) & 1 else -1

    fingerprint = 0
    for i in range(64):
        if v[i] > 0:
            fingerprint |= 1 << i
    return format(fingerprint, "016x")


def hamming_distance(fp1: str, fp2: str) -> int:
    """计算两个指纹的汉明距离。非法输入返回 64（视为完全不相似）。"""
    try:
        i1 = int(fp1, 16)
        i2 = int(fp2, 16)
    except (ValueError, TypeError):
        return 64
    return bin(i1 ^ i2).count("1")


def is_similar(fp1: str, fp2: str, threshold: int = 8) -> bool:
    """判断两个指纹是否相似（汉明距离 ≤ 阈值）。"""
    return hamming_distance(fp1, fp2) <= threshold
