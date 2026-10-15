"""Video compose adapter — ffmpeg-based deterministic composition.

设计依据：
  Easel assemble.py 的确定性合成流程（分镜素材 → 成品短视频），拓展为你项目的
  Adapter 模式。核心逻辑逐行对齐 Easel assemble.py，改进点：
  1. 异步 I/O：Easel subprocess.run 同步阻塞 → asyncio.create_subprocess_exec 异步非阻塞
  2. 结构化错误：Easel fail() → sys.exit(1) → 本模块 ComposeError 异常
  3. 临时目录：Easel tempfile.TemporaryDirectory → 本模块同样用 tempfile，但异步清理
  4. 输出：Easel 写文件 → 本模块返回 bytes，由 Skill 层存 asset_library

合成流程（依据 Easel assemble.py cmd_assemble L289-490）：
  storyboard JSON → 逐镜生成片段 → concat 拼接 → 配音+BGM 混音 → 烧字幕 → 成片
"""

from __future__ import annotations

import asyncio
import json
import logging
import shutil
import tempfile
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class ComposeError(Exception):
    """视频合成错误。"""

    def __init__(self, error_type: str, message: str):
        self.error_type = error_type
        self.message = message
        super().__init__(message)


def _check_ffmpeg() -> None:
    """检查 ffmpeg/ffprobe 是否可用（依据 Easel assemble.py _check_ffmpeg L29-32）。"""
    for tool in ("ffmpeg", "ffprobe"):
        if shutil.which(tool) is None:
            raise ComposeError(
                "missing_ffmpeg",
                f"未找到 {tool}，请先安装 ffmpeg（含 ffprobe）",
            )


async def _ensure_ffmpeg() -> str | None:
    """确保 ffmpeg 可用，返回可执行文件路径；不可用时返回 None（不抛异常）。

    P0-3 修复（2026-10-13）：video_pipeline 的 _overlay_bgm/_overlay_subtitle
    一直 import 本函数，但此前只存在同步的 _check_ffmpeg，导致 BGM/字幕叠加
    100% ImportError 后被 except 吞掉、静默降级。两者分工：
      - _check_ffmpeg：compose_video 等硬路径，缺工具直接 ComposeError 中断
      - _ensure_ffmpeg：video_pipeline 的 BGM/字幕叠加等软路径，缺工具降级跳过
    """
    return shutil.which("ffmpeg")


async def _run(cmd: list[str], cwd: str | None = None) -> str:
    """异步执行 ffmpeg 命令（依据 Easel assemble.py _run L35-38，改为异步）。

    Easel 原版：subprocess.run(cmd, capture_output=True, text=True) 同步阻塞
    本版：asyncio.create_subprocess_exec 异步非阻塞，不卡事件循环

    cwd: 子进程工作目录。字幕烧录专用——Windows ffmpeg 的 subtitles 滤镜
    解析不了带盘符冒号的绝对路径（见 _subtitle_vf 注释），需切到 ass
    所在目录用相对文件名。
    """
    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=cwd,
    )
    stdout, stderr = await process.communicate()
    if process.returncode != 0:
        tail = "\n".join((stderr.decode(errors="replace") or "").splitlines()[-12:])
        raise ComposeError("ffmpeg_failed", f"ffmpeg 执行失败：\n{tail}")
    return stdout.decode(errors="replace")


def _subtitle_vf(ass_path: Path) -> tuple[str, str]:
    """字幕烧录用的 -vf 参数 + ffmpeg cwd。

    Windows 实测（2026-10-13，本机 ffmpeg 9.x）三种绝对路径写法全部失败：
      - "D\\:\\...\\sub.ass"（Easel 原版 Linux 式 \\: + 单引号）：
        libass 收到 "D:My_Project...sub.ass"，冒号和反斜杠被吃
      - "D\\:/.../sub.ass"（正斜杠 + \\:）：路径被 : 截断，后半被当成
        filter 选项解析（original_size 报错）
      - filename= 形式：同上
    唯一可靠：cwd 切到 ass 所在目录，滤镜里只传纯文件名
    （无冒号/无反斜杠/无空格）。输入输出均为绝对路径，不受 cwd 影响。

    返回: (vf 字符串, cwd)
    """
    return f"subtitles={ass_path.name}", str(ass_path.parent)


async def _probe_duration(path: str) -> float:
    """探测视频时长（依据 Easel assemble.py _probe_duration L41-48）。"""
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=nw=1:nk=1", path,
    ]
    try:
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await process.communicate()
        return float(stdout.decode().strip())
    except (ValueError, OSError):
        return 0.0


async def _has_audio(path: str) -> bool:
    """探测视频是否含音轨（依据 Easel assemble.py _has_audio L51-56）。"""
    cmd = [
        "ffprobe", "-v", "error",
        "-select_streams", "a:0",
        "-show_entries", "stream=codec_name",
        "-of", "csv=p=0", path,
    ]
    try:
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await process.communicate()
        return process.returncode == 0 and bool(stdout.decode().strip())
    except OSError:
        return False


def _fmt_ts(sec: float) -> str:
    """秒 → SRT 时间戳（依据 Easel assemble.py _fmt_ts L59-61）。"""
    h = int(sec // 3600)
    m = int((sec % 3600) // 60)
    s = int(sec % 60)
    ms = int((sec - int(sec)) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _auto_srt(shots: list[dict], durations: list[float], srt_path: Path) -> None:
    """用各 shot 的 caption + 时长自动生成 SRT（依据 Easel assemble.py _auto_srt L64-75）。"""
    lines = []
    t = 0.0
    idx = 1
    for shot, dur in zip(shots, durations):
        cap = (shot.get("caption") or "").strip()
        if cap:
            lines.append(f"{idx}\n{_fmt_ts(t)} --> {_fmt_ts(t + dur)}\n{cap}\n")
            idx += 1
        t += dur
    srt_path.write_text("\n".join(lines), encoding="utf-8")


def _ass_ts(srt_ts: str) -> str:
    """SRT 时间戳 → ASS 时间戳（依据 Easel assemble.py _ass_ts L82-88）。"""
    srt_ts = srt_ts.strip().replace(".", ",")
    hms, _, ms = srt_ts.partition(",")
    h, m, s = (hms.split(":") + ["0", "0", "0"])[:3]
    cs = int(round(int((ms or "0").ljust(3, "0")[:3]) / 10))
    return f"{int(h)}:{int(m):02d}:{int(s):02d}.{cs:02d}"


def _char_units(ch: str) -> float:
    """单字符占的横向宽度单位（依据 Easel assemble.py _char_units L91-92）。"""
    return 1.0 if ord(ch) > 0x2E80 else 0.5


def wrap_caption(text: str, max_units: float) -> list[str]:
    """按显示宽度把一行字幕确定性折成多行（依据 Easel assemble.py wrap_caption L95-120）。"""
    flat = " ".join(
        seg.strip()
        for seg in str(text).replace("\\N", "\n").split("\n")
        if seg.strip()
    )
    if not flat:
        return []
    out: list[str] = []
    cur = ""
    cur_u = 0.0
    for ch in flat:
        cu = _char_units(ch)
        if cur and cur_u + cu > max_units:
            if ch != " " and " " in cur.rstrip():
                head, _, tail = cur.rstrip().rpartition(" ")
                if head:
                    out.append(head)
                    cur = tail
                    cur_u = sum(_char_units(c) for c in tail)
                else:
                    out.append(cur)
                    cur = ""
                    cur_u = 0.0
            else:
                out.append(cur)
                cur = ""
                cur_u = 0.0
        if ch == " " and not cur:
            continue
        cur += ch
        cur_u += cu
    if cur.strip():
        out.append(cur.rstrip())
    return out or [flat]


DEFAULT_SUB_FONT = "Noto Sans SC"

# P2-15 修复（2026-10-13）：字幕字体候选表（fontconfig family 名 + Windows 字体文件名）。
# 旧值 "Noto Sans CJK SC" 本机没装（装的是 "Noto Sans SC"），libass 只能
# fallback 到随机中文字体，字形不可控。按候选顺序挑第一个真实存在的。
_SUB_FONT_CANDIDATES: list[tuple[str, str]] = [
    ("Noto Sans SC", "Noto Sans SC (TrueType).otf"),
    ("Microsoft YaHei", "msyh.ttc"),
    ("DengXian", "Deng.ttf"),
    ("SimHei", "simhei.ttf"),
]


def _pick_sub_font(preferred: str | None = None) -> str:
    """挑一个本机真实存在的字幕字体；显式传入的 preferred 优先。"""
    if preferred:
        return preferred
    font_dir = Path("C:/Windows/Fonts")
    for family, filename in _SUB_FONT_CANDIDATES:
        if (font_dir / filename).exists():
            return family
    return DEFAULT_SUB_FONT  # 兜底：让 libass 自己 fallback


def _srt_to_ass(
    srt_path: Path,
    ass_path: Path,
    w: int,
    h: int,
    font: str | None = None,
    font_size: int | None = None,
    margin_v: int | None = None,
) -> Path:
    """SRT → 带完整样式的 ASS（依据 Easel assemble.py _srt_to_ass L123-165）。

    关键：显式 PlayResX/Y = 视频尺寸，字号就是像素级别。
    默认字号 ≈ 短边*0.05，Alignment=2 底部居中。
    font=None 时按 _pick_sub_font() 探测本机可用中文字体。
    """
    font = _pick_sub_font(font)
    fs = int(font_size if font_size else round(min(w, h) * 0.05))
    mv = int(margin_v if margin_v is not None else round(h * 0.07))
    mh = int(round(w * 0.06))
    max_units = max(6.0, (w - 2 * mh) / fs * 0.94)

    header = (
        "[Script Info]\n"
        "ScriptType: v4.00+\n"
        f"PlayResX: {w}\nPlayResY: {h}\n"
        "WrapStyle: 0\nScaledBorderAndShadow: yes\n\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, "
        "BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, "
        "BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
        f"Style: Default,{font},{fs},&H00FFFFFF,&H000000FF,&H00000000,&H00000000,"
        f"0,0,0,0,100,100,0,0,1,2,0,2,{mh},{mh},{mv},1\n\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )

    events: list[str] = []
    blocks = [
        b
        for b in srt_path.read_text(encoding="utf-8").replace("\r", "").split("\n\n")
        if b.strip()
    ]
    for b in blocks:
        rows = [r for r in b.split("\n") if r.strip() != ""]
        ts_line = next((r for r in rows if "-->" in r), None)
        if not ts_line:
            continue
        start, _, end = ts_line.partition("-->")
        txt_rows = rows[rows.index(ts_line) + 1 :]
        raw = " ".join(t.strip() for t in txt_rows) if txt_rows else ""
        wrapped = wrap_caption(raw, max_units)
        if not wrapped:
            continue
        text = "\\N".join(wrapped)
        events.append(
            f"Dialogue: 0,{_ass_ts(start)},{_ass_ts(end)},Default,,0,0,0,,{text}"
        )
    ass_path.write_text(header + "\n".join(events) + "\n", encoding="utf-8")
    return ass_path


MAX_STRETCH = 2.0


def _image_filter(motion: str, w: int, h: int, frames: int) -> str:
    """图片 → 视频滤镜（依据 Easel assemble.py _image_filter L168-175）。"""
    if motion == "static":
        return (
            f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
            f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:black,setsar=1,fps=30"
        )
    if motion == "ken-burns":
        return (
            f"scale={w * 2}:{h * 2}:force_original_aspect_ratio=increase,"
            f"crop={w * 2}:{h * 2},"
            f"zoompan=z='min(zoom+0.0008,1.08)':d={frames}:s={w}x{h}:fps=30,"
            f"setsar=1"
        )
    raise ComposeError("bad_motion", f"shot motion 不支持：{motion}（只能是 static / ken-burns）")


async def _make_shot_clip(
    shot: dict,
    dur: float,
    w: int,
    h: int,
    out: Path,
    workdir: Path,
    pad_mode: str = "auto",
    include_audio: bool = False,
    preserve_audio: bool = False,
    image_motion: str = "ken-burns",
) -> None:
    """把单个 shot 做成 w×h、时长 dur 的片段（依据 Easel assemble.py _make_shot_clip L178-260）。"""
    base_vf = (
        f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
        f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:black,setsar=1"
    )

    if shot.get("video"):
        src = shot["video"]
        if not Path(src).is_file():
            raise ComposeError("missing_file", f"shot 视频不存在：{src}")
        src_dur = await _probe_duration(src)

        if src_dur >= dur - 0.05 or src_dur <= 0:
            await _run([
                "ffmpeg", "-y", "-i", src, "-t", f"{dur:.3f}",
                "-vf", f"{base_vf},fps=30", "-an",
                "-c:v", "libx264", "-pix_fmt", "yuv420p", str(out),
            ])
            return

        factor = dur / src_dur
        mode = pad_mode
        if mode == "trim":
            raise ComposeError(
                "clip_too_short",
                f"视频片段仅 {src_dur:.2f}s 但该镜要 {dur:.2f}s——trim 模式禁止冻结/拉伸/循环",
            )
        if mode == "auto":
            mode = "stretch" if factor <= MAX_STRETCH else "loop"
        if mode == "stretch":
            await _run([
                "ffmpeg", "-y", "-i", src,
                "-vf", f"{base_vf},setpts={factor:.4f}*PTS,fps=30",
                "-t", f"{dur:.3f}", "-an",
                "-c:v", "libx264", "-pix_fmt", "yuv420p", str(out),
            ])
        elif mode == "freeze":
            await _run([
                "ffmpeg", "-y", "-i", src,
                "-vf", f"{base_vf},fps=30,tpad=stop_mode=clone:stop_duration={dur:.3f}",
                "-t", f"{dur:.3f}", "-an",
                "-c:v", "libx264", "-pix_fmt", "yuv420p", str(out),
            ])
        else:
            await _run([
                "ffmpeg", "-y", "-stream_loop", "-1", "-i", src,
                "-t", f"{dur:.3f}",
                "-vf", f"{base_vf},fps=30", "-an",
                "-c:v", "libx264", "-pix_fmt", "yuv420p", str(out),
            ])
    else:
        src = shot.get("image")
        if not src or not Path(src).is_file():
            raise ComposeError("missing_file", f"shot 图片不存在：{src}")
        frames = max(1, int(dur * 30))
        motion = str(shot.get("motion") or image_motion)
        vf = _image_filter(motion, w, h, frames)
        await _run([
            "ffmpeg", "-y", "-loop", "1", "-i", src,
            "-t", f"{dur:.3f}", "-vf", vf, "-an",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", str(out),
        ])


async def compose_video(
    storyboard: dict[str, Any],
    output_path: str,
    pad_mode: str = "auto",
    sub_font: str | None = None,
) -> Path:
    """分镜素材 → 成品短视频（依据 Easel assemble.py cmd_assemble L289-490）。

    storyboard 结构（依据 Easel auto-short-video SKILL.md L44-58）：
    {
      "size": "1080x1920",
      "image_motion": "ken-burns",
      "shots": [
        {"image": "shot1.png", "duration": 3, "caption": "第一句"},
        {"video": "clip2.mp4", "caption": "第二句"}
      ],
      "narration": "voice.mp3",
      "bgm": "bgm.mp3",
      "bgm_volume": 0.25,
      "subtitle": "sub.srt"
    }
    """
    _check_ffmpeg()

    shots = storyboard.get("shots") or []
    if not shots:
        raise ComposeError("empty_shots", "storyboard.shots 为空")

    image_motion = str(storyboard.get("image_motion") or "ken-burns")
    if image_motion not in {"static", "ken-burns"}:
        raise ComposeError("bad_motion", "storyboard.image_motion 只能是 static / ken-burns")

    size = str(storyboard.get("size") or "1080x1920")
    try:
        w, h = (int(x) for x in size.lower().split("x"))
    except ValueError:
        raise ComposeError("bad_size", f"size 格式错误：{size}（应如 1080x1920）")

    narration = storyboard.get("narration")
    if narration and not Path(narration).is_file():
        raise ComposeError("missing_file", f"配音文件不存在：{narration}")

    durations: list[float] = []
    explicit = [float(s["duration"]) for s in shots if s.get("duration")]
    if narration and len(explicit) < len(shots):
        total = await _probe_duration(narration)
        per = max(1.0, total / len(shots)) if total > 0 else 3.0
        durations = [float(s.get("duration") or per) for s in shots]
    else:
        durations = [float(s.get("duration") or 3.0) for s in shots]

    # resolve 成绝对路径（2026-10-14 修）：字幕烧录步骤会把 ffmpeg 的 cwd
    # 切到 ass 所在临时目录（Windows ffmpeg 吃不了绝对路径的字幕文件），
    # 若 out 是相对路径会被解析到临时目录里导致 "No such file or directory"。
    # 生产链路都传绝对路径，但这里统一 resolve 根治此类脆弱点。
    out = Path(output_path).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as td:
        workdir = Path(td)

        clips = []
        for i, (shot, dur) in enumerate(zip(shots, durations)):
            clip = workdir / f"clip_{i:03d}.mp4"
            logger.info(f"合成分镜 {i + 1}/{len(shots)}（{dur:.1f}s）")
            await _make_shot_clip(
                shot, dur, w, h, clip, workdir,
                pad_mode=pad_mode,
                image_motion=image_motion,
            )
            clips.append(clip)

        concat_list = workdir / "list.txt"
        concat_list.write_text(
            "".join(f"file '{c}'\n" for c in clips), encoding="utf-8"
        )
        silent = workdir / "silent.mp4"
        await _run([
            "ffmpeg", "-y", "-f", "concat", "-safe", "0",
            "-i", str(concat_list),
            "-c:v", "libx264", "-pix_fmt", "yuv420p", str(silent),
        ])

        video_dur = sum(durations)

        sub_path = None
        if storyboard.get("subtitle") and Path(storyboard["subtitle"]).is_file():
            sub_path = Path(storyboard["subtitle"])
        elif any(s.get("caption") for s in shots):
            sub_path = workdir / "auto.srt"
            _auto_srt(shots, durations, sub_path)

        stage = silent
        if narration or storyboard.get("bgm"):
            stage2 = workdir / "with_audio.mp4"
            inputs = ["-i", str(silent)]
            filters = []
            amix_srcs = []
            ai = 1

            inputs += [
                "-f", "lavfi", "-t", f"{video_dur:.3f}",
                "-i", "anullsrc=r=48000:cl=stereo",
            ]
            filters.append(
                f"[{ai}:a]aformat=sample_fmts=fltp:channel_layouts=stereo[abase]"
            )
            ai += 1

            if narration:
                inputs += ["-i", narration]
                filters.append(f"[{ai}:a]aresample=48000[voice]")
                amix_srcs.append("[abase]")
                amix_srcs.append("[voice]")
                ai += 1
            else:
                amix_srcs.append("[abase]")

            if storyboard.get("bgm"):
                bgm = storyboard["bgm"]
                if not Path(bgm).is_file():
                    raise ComposeError("missing_file", f"BGM 文件不存在：{bgm}")
                vol = float(storyboard.get("bgm_volume") or 0.25)
                inputs += ["-stream_loop", "-1", "-i", bgm]
                filters.append(f"[{ai}:a]aresample=44100,volume={vol}[bgm]")
                amix_srcs.append("[bgm]")
                ai += 1

            filters.append(
                f"{''.join(amix_srcs)}amix=inputs={len(amix_srcs)}:duration=first:normalize=0[aout]"
            )
            await _run([
                "ffmpeg", "-y", *inputs,
                "-filter_complex", ";".join(filters),
                "-map", "0:v", "-map", "[aout]",
                "-t", f"{video_dur:.3f}",
                "-c:v", "copy", "-c:a", "aac", str(stage2),
            ])
            stage = stage2

        if sub_path:
            if sub_path.suffix.lower() == ".ass":
                ass_path = sub_path
            else:
                ass_path = workdir / "sub.ass"
                _srt_to_ass(
                    sub_path, ass_path, w, h,
                    font=sub_font,
                )
            # Windows ffmpeg 的 subtitles 滤镜吃不了绝对路径（详见 _subtitle_vf），
            # 用 cwd + 纯文件名方案。2026-10-13 真机实测四种写法唯一可靠的解。
            sub_vf, sub_cwd = _subtitle_vf(ass_path)
            await _run([
                "ffmpeg", "-y", "-i", str(stage),
                "-vf", sub_vf,
                "-c:a", "copy", str(out),
            ], cwd=sub_cwd)
        else:
            shutil.copy(str(stage), str(out))

    logger.info(f"成片已生成：{out}（{video_dur:.1f}s，{w}x{h}）")
    return out


async def _download_to_file(url: str, dest: Path) -> None:
    """下载 URL 到本地文件。"""
    import httpx

    async with httpx.AsyncClient(timeout=120, follow_redirects=True) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        dest.write_bytes(resp.content)


async def _normalize_clip(clip: Path, norm: Path) -> None:
    """统一编码为 h264/yuv420p/30fps + AAC 48k 立体声（确保 xfade/concat 兼容）。

    P1-8 修复（2026-10-13）：旧版带 -an 把所有片段的音轨全抹掉，Ark
    native_audio 生成的带声片段拼完成片直接变无声。现改为：
      - 有音轨的片段：保留并统一音频参数
      - 无音轨的片段：补 anullsrc 静音轨，保证下游 acrossfade 链
        每条输入都有音频流（缺流会让 filter_complex 直接失败）
    """
    if await _has_audio(str(clip)):
        await _run([
            "ffmpeg", "-y", "-i", str(clip),
            "-vf", "fps=30,format=yuv420p,setsar=1",
            "-c:v", "libx264", "-c:a", "aac", "-b:a", "128k",
            "-ar", "48000", "-ac", "2", "-r", "30",
            str(norm),
        ])
    else:
        await _run([
            "ffmpeg", "-y", "-i", str(clip),
            "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo",
            "-vf", "fps=30,format=yuv420p,setsar=1",
            "-map", "0:v", "-map", "1:a",
            "-c:v", "libx264", "-c:a", "aac", "-b:a", "128k",
            "-r", "30", "-shortest",
            str(norm),
        ])


def _xfade_offsets(durations: list[float], xfade_dur: float) -> list[float]:
    """计算链式 xfade 的 offset 序列（P1-7 修复，2026-10-13）。

    第 i 次 xfade 把 clip[i+1] 拼到当前流上，offset = 当前流长 - xfade_dur。
    当前流由 clip 0..i 拼成，长度 = sum(d_j, j<=i) - i*xfade_dur
    （此前每次 xfade 已吃掉一个 xfade_dur）。
    故 offset_i = sum(d_j, j<=i) - (i+1)*xfade_dur。

    旧代码 i>0 时内循环只累加到 j<i（漏加当前片段 d_i）且又减一次
    xfade_dur，导致非首个转场的 offset 少一个片段时长、提前一个
    xfade_dur，5s 片段的转场点能错位 5 秒以上。
    """
    offsets: list[float] = []
    stream_len = 0.0
    for i in range(len(durations) - 1):
        stream_len += durations[i]
        if i > 0:
            stream_len -= xfade_dur
        offsets.append(max(0.1, stream_len - xfade_dur))
    return offsets


async def compose_video_concat(
    clip_urls: list[str],
    transitions: list[str] | None = None,
    output_path: str = "",
) -> Path:
    """拼接视频片段（支持 xfade 转场，音视频同步过渡）。

    参数：
      clip_urls: 视频片段 URL 列表（http/https 或本地路径）
      transitions: 每个片段间的转场类型（cut / dissolve / wipe），默认 cut
      output_path: 输出文件路径

    返回：输出文件 Path

    流程：
      1. 下载远程片段到临时目录
      2. 统一编码为 h264/yuv420p/30fps + AAC（_normalize_clip，保留音轨）
      3. 无转场：concat demuxer 直接拼（-c copy 不重编码）
         有转场：视频走 xfade 链 + 音频走 acrossfade 链，双 -map 输出
         （acrossfade 无 offset 参数，链式天然顺序叠加，与 xfade 对齐）
      4. 输出到 output_path
    """
    _check_ffmpeg()

    if not clip_urls:
        raise ComposeError("empty_clips", "clip_urls 为空")

    if not output_path:
        import tempfile as _tf
        output_path = str(Path(_tf.mkdtemp()) / "concat_output.mp4")

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    xfade_dur = 0.5
    xfade_map = {"dissolve": "fade", "fade": "fade", "wipe": "wipeleft", "cut": "cut"}

    with tempfile.TemporaryDirectory() as td:
        workdir = Path(td)

        local_clips: list[Path] = []
        for i, url in enumerate(clip_urls):
            clip_path = workdir / f"clip_{i:03d}.mp4"
            if url.startswith("http"):
                await _download_to_file(url, clip_path)
            else:
                src = Path(url)
                if src.is_file():
                    shutil.copy(str(src), str(clip_path))
                else:
                    raise ComposeError("missing_file", f"视频片段不存在：{url}")
            local_clips.append(clip_path)

        normalized: list[Path] = []
        for i, clip in enumerate(local_clips):
            norm = workdir / f"norm_{i:03d}.mp4"
            await _normalize_clip(clip, norm)
            normalized.append(norm)

        if len(normalized) == 1:
            shutil.copy(str(normalized[0]), str(out))
            logger.info(f"单片段直接输出（含音轨）：{out}")
            return out

        trans = (transitions or ["cut"] * (len(normalized) - 1))
        while len(trans) < len(normalized) - 1:
            trans.append("cut")

        has_xfade = any(xfade_map.get(t, "cut") != "cut" for t in trans)

        if not has_xfade:
            concat_list = workdir / "list.txt"
            concat_list.write_text(
                "".join(f"file '{c}'\n" for c in normalized),
                encoding="utf-8",
            )
            await _run([
                "ffmpeg", "-y", "-f", "concat", "-safe", "0",
                "-i", str(concat_list),
                "-c", "copy", str(out),
            ])
            logger.info(f"concat 拼接完成（无转场，音轨保留）：{out}")
            return out

        # 有转场：先批量探测时长算 offset，再构建 xfade 视频链 + acrossfade 音频链
        durations = [await _probe_duration(str(c)) for c in normalized]
        offsets = _xfade_offsets(durations, xfade_dur)

        inputs: list[str] = []
        for clip in normalized:
            inputs += ["-i", str(clip)]

        v_parts: list[str] = []
        a_parts: list[str] = []
        prev_v = "[0:v]"
        prev_a = "[0:a]"
        last = len(normalized) - 2  # 最后一级转场的索引

        for i in range(len(normalized) - 1):
            t_type = xfade_map.get(trans[i], "cut")
            out_v = f"[v{i}]" if i < last else "[vout]"
            out_a = f"[a{i}]" if i < last else "[aout]"
            v_parts.append(
                f"{prev_v}[{i + 1}:v]xfade=transition={t_type}:duration={xfade_dur:.2f}:offset={offsets[i]:.2f}{out_v}"
            )
            a_parts.append(
                f"{prev_a}[{i + 1}:a]acrossfade=d={xfade_dur:.2f}:c1=tri:c2=tri{out_a}"
            )
            prev_v, prev_a = out_v, out_a

        await _run([
            "ffmpeg", "-y", *inputs,
            "-filter_complex", ";".join(v_parts + a_parts),
            "-map", "[vout]", "-map", "[aout]",
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "128k", str(out),
        ])
        logger.info(f"xfade 拼接完成（含转场，音画同步）：{out}")
        return out


async def compose_video_concat_simple(
    clip_urls: list[str],
    output_path: str = "",
) -> Path:
    """简单拼接视频片段（无转场，直接 concat demuxer）。

    降级方案：当 xfade 拼接失败时使用。
    """
    _check_ffmpeg()

    if not clip_urls:
        raise ComposeError("empty_clips", "clip_urls 为空")

    if not output_path:
        import tempfile as _tf
        output_path = str(Path(_tf.mkdtemp()) / "concat_simple.mp4")

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as td:
        workdir = Path(td)

        local_clips: list[Path] = []
        for i, url in enumerate(clip_urls):
            clip_path = workdir / f"clip_{i:03d}.mp4"
            if url.startswith("http"):
                await _download_to_file(url, clip_path)
            else:
                src = Path(url)
                if src.is_file():
                    shutil.copy(str(src), str(clip_path))
                else:
                    raise ComposeError("missing_file", f"视频片段不存在：{url}")
            local_clips.append(clip_path)

        normalized: list[Path] = []
        for i, clip in enumerate(local_clips):
            norm = workdir / f"norm_{i:03d}.mp4"
            await _normalize_clip(clip, norm)
            normalized.append(norm)

        concat_list = workdir / "list.txt"
        concat_list.write_text(
            "".join(f"file '{c}'\n" for c in normalized),
            encoding="utf-8",
        )
        await _run([
            "ffmpeg", "-y", "-f", "concat", "-safe", "0",
            "-i", str(concat_list),
            "-c", "copy", str(out),
        ])
        logger.info(f"简单拼接完成（音轨保留）：{out}")
        return out