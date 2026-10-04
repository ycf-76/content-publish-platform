"""出站内容安全闸门（确定性扫描）.

Agent 会把生成的文案真实发布到公开平台。从 agent 生成文本到真发之间，
一旦 agent 把内部设置误写进内容（API key、内部 URL、代理 IP、模型名等），
就会公开泄露且删不掉。

本模块扫描任意「要发到公开平台的文本」，检出疑似内部设置泄露。
发布节点在真发前调用 `guard_or_die(...)`。

两级强制（见 BLOCK_CATEGORIES）：
- BLOCK 级 = 真·敏感信息（密钥/内部域名/代理IP/内部路径/env名）
  → fail-closed 阻止发布
- WARN 级 = AI 措辞（"由AI生成"/模型名等）
  → 只告警、绝不拦截（论文/科普里可能是正常内容）

设计原则：纯 stdlib、可移植、带 selftest；不联网、不改文件。

借鉴 Easel content_guard.py 的扫描逻辑和分级机制，
但适配我们的项目：去掉小红书内部域名，加上通用敏感模式，
改为抛 ContentGuardError 而非 sys.exit（适配 async 工作流）。
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path


class ContentGuardError(Exception):
    """出站内容安全闸门拦截异常。

    发布节点捕获此异常后应阻止发布、记录日志、通知用户。
    """
    def __init__(self, findings: list["Finding"]):
        self.findings = findings
        block = [f for f in findings if f.category in BLOCK_CATEGORIES]
        super().__init__(
            f"出站内容安全闸门拦截：检测到 {len(block)} 处敏感信息泄露，已阻止发布"
        )


EXIT_LEAK = 7


def _p(pat: str, flags: int = 0) -> "re.Pattern[str]":
    return re.compile(pat, flags)


SECRET_PATTERNS: list[tuple[str, str, "re.Pattern[str]", str]] = [
    ("api-key", "high", _p(r"\bsk-[A-Za-z0-9_\-]{16,}\b"), "疑似 API key（sk- 开头）"),
    ("api-key", "high", _p(r"(?i)\b(?:api[_-]?key|auth[_-]?token|access[_-]?key|"
                           r"secret[_-]?key|app[_-]?secret|secret)\b\s*[:=]\s*['\"]?[A-Za-z0-9/_\-\.]{8,}"),
     "键值形式的密钥/令牌"),
    ("api-key", "high", _p(r"(?i)\bBearer\s+[A-Za-z0-9/_\-\.]{12,}"), "Bearer 令牌"),
    ("api-key", "high", _p(r"(?i)\b(?:AK|SK)\s*[:=]\s*['\"]?[A-Za-z0-9]{16,}"), "云厂商 AK/SK"),
    ("internal-host", "med", _p(r"(?i)\b(?:localhost|127\.0\.0\.1|0\.0\.0\.0)(?::\d+)?\b"),
     "本地服务地址"),
    ("internal-host", "med", _p(r"(?i)\b[a-z0-9\-]+\.internal\.[a-z]+\b"), "内部域名"),
    ("internal-host", "med", _p(r"(?i)\b[a-z0-9\-]+\.corp\.[a-z]+\b"), "企业内网域名"),
    ("internal-host", "med", _p(r"\bapi-version=[0-9]"), "API 版本查询串"),
    ("proxy-ip", "med", _p(r"\b(?:10|192\.168|172\.(?:1[6-9]|2\d|3[01]))"
                           r"(?:\.\d{1,3}){2,3}(?::\d+)?\b"), "私网/代理 IP"),
    ("proxy-ip", "med", _p(r":3128\b"), "代理端口 3128"),
    ("proxy-ip", "med", _p(r":1080\b"), "代理端口 1080"),
    ("internal-path", "med", _p(r"(?:~|/root)?/\.ssh\S*"), "SSH 配置路径"),
    ("internal-path", "med", _p(r"/etc/(?:passwd|shadow|hosts)\b"), "系统敏感文件路径"),
    ("internal-path", "med", _p(r"(?i)(?:~|/root)?/\.env\b"), ".env 文件路径"),
    ("env-name", "med", _p(r"\bANTHROPIC_[A-Z_]+\b"), "Anthropic env 变量名"),
    ("env-name", "med", _p(r"\bOPENAI_[A-Z_]+\b"), "OpenAI env 变量名"),
    ("env-name", "med", _p(r"\bDEEPSEEK_[A-Z_]+\b"), "DeepSeek env 变量名"),
    ("env-name", "med", _p(r"(?i)\b(?:DATABASE_URL|REDIS_URL|MONGO_URI|SECRET_KEY|JWT_SECRET)\b"),
     "数据库/密钥 env 变量名"),
    ("model-name", "low", _p(r"\bclaude-[a-z0-9][a-z0-9.\-\[\]]*\b", re.I), "Claude 模型 ID"),
    ("model-name", "low", _p(r"\bdeepseek-[a-z0-9][a-z0-9.\-\[\]]*\b", re.I), "DeepSeek 模型 ID"),
    ("model-name", "low", _p(r"\bgpt-[a-z0-9][a-z0-9.\-]*\b", re.I), "GPT 模型 ID"),
    ("model-name", "low", _p(r"\b(?:Claude|GPT|DeepSeek|Anthropic)\b"), "模型厂商/系列名"),
    ("ai-disclosure", "low", _p(r"由\s*AI\s*(?:生成|创作|撰写|制作|完成)"), "「由 AI 生成」类措辞"),
    ("ai-disclosure", "low", _p(r"(?i)(?:append-)?system[\s\-]?prompt"), "系统提示词字样"),
    ("ai-disclosure", "low", _p(r"(?:我(?:们)?是|作为|身为|本|自称)(?:一[个只])?(?:大语言模型|大模型)"
                                r"|(?:大语言模型|大模型)(?:生成|创作|撰写|制作)"), "自曝为大模型"),
]

BLOCK_CATEGORIES = {
    "api-key", "env-value", "internal-host", "proxy-ip", "internal-path", "env-name",
}

_SENSITIVE_ENV_NAME = re.compile(
    r"(?:API_KEY|AUTH_TOKEN|_TOKEN|SECRET|ACCESS_KEY|BASE_URL|AUTH|DATABASE|REDIS|MONGO|JWT)",
    re.I,
)


@dataclass
class Finding:
    category: str
    severity: str
    hint: str
    snippet: str
    span: tuple[int, int]


def _mask(value: str) -> str:
    v = value.strip()
    if len(v) <= 8:
        return v[0] + "***" if v else "***"
    return f"{v[:4]}***{v[-2:]}"


def _snippet(text: str, start: int, end: int, ctx: int = 12) -> str:
    lo = max(0, start - ctx)
    hi = min(len(text), end + ctx)
    before = text[lo:start].replace("\n", " ")
    after = text[end:hi].replace("\n", " ")
    hit = _mask(text[start:end])
    pre = "…" if lo > 0 else ""
    suf = "…" if hi < len(text) else ""
    return f"{pre}{before}【{hit}】{after}{suf}"


def load_env_literals(root: str | Path | None = None) -> set[str]:
    """读项目 .env，把敏感键的字面值收进扫描集。"""
    candidates: list[Path] = []
    if root:
        candidates.append(Path(root))
    here = Path(__file__).resolve()
    candidates.extend([here.parent, here.parent.parent, Path.cwd()])

    literals: set[str] = set()
    seen: set[Path] = set()
    for base in candidates:
        env_path = base / ".env"
        try:
            rp = env_path.resolve()
        except OSError:
            continue
        if rp in seen or not env_path.is_file():
            continue
        seen.add(rp)
        for raw in env_path.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            name, _, value = line.partition("=")
            name, value = name.strip(), value.strip().strip('"').strip("'")
            if len(value) >= 6 and _SENSITIVE_ENV_NAME.search(name):
                literals.add(value)
    return literals


def scan(text: str, extra_literals: set[str] | None = None) -> list[Finding]:
    """扫描出站文本，返回所有命中。正则 + .env 字面值双路。"""
    if not text:
        return []
    findings: list[Finding] = []

    literals = set(extra_literals) if extra_literals else set()
    literals |= load_env_literals()
    for lit in literals:
        idx = text.find(lit)
        while idx != -1:
            findings.append(Finding("env-value", "high", ".env 里的真实敏感值",
                                    _snippet(text, idx, idx + len(lit)),
                                    (idx, idx + len(lit))))
            idx = text.find(lit, idx + len(lit))

    for category, severity, pat, hint in SECRET_PATTERNS:
        for m in pat.finditer(text):
            s, e = m.span()
            if e == s:
                continue
            findings.append(Finding(category, severity, hint, _snippet(text, s, e), (s, e)))

    findings.sort(key=lambda f: (f.span[0], -(f.span[1] - f.span[0])))
    deduped: list[Finding] = []
    for f in findings:
        if any(f.span[0] >= d.span[0] and f.span[1] <= d.span[1] for d in deduped):
            continue
        deduped.append(f)
    return deduped


def redact(text: str, extra_literals: set[str] | None = None) -> tuple[str, list[Finding]]:
    """把命中片段替换成 [已隐藏]，返回 (脱敏文本, 命中列表)。"""
    findings = scan(text, extra_literals)
    out = text
    for f in sorted(findings, key=lambda x: x.span[0], reverse=True):
        s, e = f.span
        out = out[:s] + "[已隐藏]" + out[e:]
    return out, findings


def guard_or_die(
    parts: str | list[str] | None,
    *,
    allow_unsafe: bool = False,
    label: str = "发布内容",
    extra_literals: set[str] | None = None,
) -> list[Finding]:
    """发布节点在真发前调用的安全闸门。

    parts: 出站文本片段（title/content/tags/comment…），None/空自动跳过。
    返回 WARN 级命中列表（供日志记录）。

    BLOCK 级命中 + 非 allow_unsafe → 抛 ContentGuardError。
    allow_unsafe → 全部只告警、不拦。
    无命中 → 返回空列表。
    """
    if parts is None:
        return []
    if isinstance(parts, str):
        parts = [parts]
    text = "\n".join(str(p) for p in parts if p)
    if not text:
        return []

    findings = scan(text, extra_literals)
    if not findings:
        return []

    block = [f for f in findings if f.category in BLOCK_CATEGORIES]
    warn = [f for f in findings if f.category not in BLOCK_CATEGORIES]

    if not allow_unsafe and block:
        raise ContentGuardError(block)

    return warn


def selftest() -> bool:
    """自测：BLOCK 正例必拦 / WARN 正例只提醒不拦 / 反例放行。"""
    block_positives = [
        ("api-key sk", "我的 key 是 sk-ABCDefgh12345678ijkl 记得保密"),
        ("kv secret", "配置 api_key=abcd1234efgh5678"),
        ("bearer", "Authorization: Bearer abcdef1234567890xyz"),
        ("localhost", "调用 http://localhost:8080/api"),
        ("proxy ip", "代理设成 10.140.24.177:3128 就行"),
        ("port 3128", "端口 :3128 是代理"),
        ("ssh path", "私钥在 ~/.ssh/id_rsa"),
        ("env name", "把 DEEPSEEK_API_KEY 填到 .env"),
        ("env openai", "设 OPENAI_API_KEY 就能用"),
        ("db url", "DATABASE_URL=postgres://user:pass@localhost/db"),
    ]
    warn_positives = [
        ("model claude", "用的是 claude-4.8-opus 模型"),
        ("model deepseek", "走 deepseek-chat 模型"),
        ("ai disclosure", "本文由 AI 生成，仅供参考"),
        ("paper explainer", "这期解读这篇大模型论文，对比了 Claude 和 GPT 的推理能力"),
        ("self disclosure", "作为一个大模型，我来帮你分析一下这个问题。"),
    ]
    negatives = [
        "今天分享 3 个提效小技巧，记得点赞收藏～",
        "这家咖啡店的手冲真的绝，氛围也好，强烈安利给周末想放松的姐妹",
        "新品上线啦！前 100 名下单送小样，评论区抽 3 位送正装",
        "客服热线 400-820-8820，官网 www.example.com 了解更多",
        "Transformer 是所有大模型的共同底座，值得每个开发者了解。",
    ]
    failed = 0

    for name, txt in block_positives:
        try:
            guard_or_die([txt], allow_unsafe=False)
            print(f"  ✗ BLOCK 正例未拦截: {name}", flush=True)
            failed += 1
        except ContentGuardError:
            pass

    for name, txt in warn_positives:
        try:
            result = guard_or_die([txt], allow_unsafe=False)
            if not result:
                print(f"  ✗ WARN 正例漏检: {name}", flush=True)
                failed += 1
        except ContentGuardError:
            print(f"  ✗ WARN 正例被误拦: {name}", flush=True)
            failed += 1

    for txt in negatives:
        result = guard_or_die([txt], allow_unsafe=False)
        if result:
            print(f"  ✗ 反例误报: {txt} :: {[h.category for h in result]}", flush=True)
            failed += 1

    clean, fnd = redact("正常开头 sk-ABCDefgh12345678ijkl 正常结尾")
    if "sk-ABCDefgh" in clean or "[已隐藏]" not in clean or not fnd:
        print(f"  ✗ redact 未生效: {clean!r}", flush=True)
        failed += 1

    if failed:
        print(f"selftest 失败：{failed} 项", flush=True)
        return False
    print(f"selftest 通过（BLOCK {len(block_positives)} 必拦 / "
          f"WARN {len(warn_positives)} 只提醒 / 反例 {len(negatives)} 放行 + redact）",
          flush=True)
    return True