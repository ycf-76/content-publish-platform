"""项目启动横幅 — 在终端打印品牌 ASCII Art 横幅。

零外部依赖，纯 ANSI 转义码 + Unicode 字符。
在 app.main lifespan 启动时调用 print_banner() 即可。
"""

import os
import subprocess

__all__ = ["print_banner"]

_R = "\033[91m"
_G = "\033[92m"
_Y = "\033[93m"
_C = "\033[96m"
_W = "\033[97m"
_B = "\033[1m"
_D = "\033[2m"
_0 = "\033[0m"


def _git_short_hash() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=2,
            cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        )
        if out.returncode == 0:
            return out.stdout.strip()
    except Exception:
        pass
    return "dev"


def _version_line() -> str:
    from app.config import get_settings
    s = get_settings()
    ver = getattr(s, "app_version", "1.0.0")
    h = _git_short_hash()
    return f"{_B}{_R}XHS Creator{_0} {_D}{ver} ({h}){_0}"


_TAGLINES = [
    "多智能体协作，一篇笔记从选题到发布全链路自动化。",
    "选题 → 企划 → 写稿 → 配图 → 发布，Agent 串起来才叫流水线。",
    "当你在喝咖啡的时候，Agent 已经把小红书笔记写好了。",
    "不是 AI 替你创作，是 AI 把你的创作力放大 10 倍。",
    "一个选题池，N 个 Agent，∞ 篇爆款。",
]


def _tagline() -> str:
    import hashlib, time
    idx = int(hashlib.md5(str(int(time.time()) // 3600).encode()).hexdigest(), 16) % len(_TAGLINES)
    return _TAGLINES[idx]


_DIAMOND = f"""{_R}     ◆◆◆◆       ◆◆◆◆     {_0}
{_R}   ◆◆◆◆◆◆◆   ◆◆◆◆◆◆◆   {_0}
{_R}  ◆◆◆◆◆◆◆◆◆ ◆◆◆◆◆◆◆◆◆  {_0}
{_R} ◆◆◆◆◆◆◆◆◆◆◆◆◆◆◆◆◆◆◆◆ {_0}
{_R}  ◆◆◆◆◆◆◆◆◆ ◆◆◆◆◆◆◆◆◆  {_0}
{_R}   ◆◆◆◆◆◆◆   ◆◆◆◆◆◆◆   {_0}
{_R}     ◆◆◆◆       ◆◆◆◆     {_0}"""

_TEXT = f"""{_W}{_B} ███╗   ██╗ ██████╗ ██╗  ██╗ █████╗ ███████╗███████╗    {_C}██████╗  ██████╗ ███████╗████████╗███████╗██████╗  {_0}
{_W}{_B} ████╗  ██║██╔═══██╗██║ ██╔╝██╔══██╗██╔════╝██╔════╝    {_C}██╔══██╗██╔═══██╗██╔════╝╚══██╔══╝██╔════╝██╔══██╗  {_0}
{_W}{_B} ██╔██╗ ██║██║   ██║█████╔╝ ███████║█████╗  ███████╗    {_C}██████╔╝██║   ██║███████╗   ██║   ███████╗██████╔╝  {_0}
{_W}{_B} ██║╚██╗██║██║   ██║██╔═██╗ ██╔══██║██╔══╝  ╚════██║    {_C}██╔══██╗██║   ██║██╔════╝   ██║   ╚════██║██╔══██╗  {_0}
{_W}{_B} ██║ ╚████║╚██████╔╝██║  ██╗██║  ██║███████╗███████║    {_C}██║  ██╗╚██████╔╝███████╗   ██║   ███████║██║  ██╗  {_0}
{_W}{_B} ╚═╝  ╚═══╝ ╚═════╝ ╚═╝  ╚═╝╚═╝  ╚═╝╚══════╝╚══════╝    {_C}╚═╝  ╚═╝ ╚═════╝ ╚══════╝   ╚═╝   ╚══════╝╚═╝  ╚═╝  {_0}"""


def print_banner() -> None:
    if os.getenv("NO_BANNER"):
        return
    print()
    print(_DIAMOND)
    print()
    print(_TEXT)
    print()
    print(f"  {_version_line()}")
    print(f"  {_D}{_tagline()}{_0}")
    print()