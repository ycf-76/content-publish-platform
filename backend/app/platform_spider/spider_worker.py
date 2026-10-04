"""Spider 运行子进程脚本。

由 runner.py 通过 subprocess.Popen 启动，
通过 stdout 输出 JSON 行与父进程通信：
  - 唯一行：{"ok": true, "items": [...]} 或 {"error": "..."}
"""
from __future__ import annotations

import json
import os
import sys
import traceback as _tb
from pathlib import Path

STORAGE_DIR = Path(__file__).resolve().parent.parent / "storage_states"

SPIDER_MAP = {
    "xiaohongshu": "app.platform_spider.xhs_spider.XhsSpider",
    "douyin": "app.platform_spider.douyin_spider.DouyinSpider",
    "bilibili": "app.platform_spider.bilibili_spider.BilibiliSpider",
}


def _emit(data: dict) -> None:
    sys.stdout.write(json.dumps(data, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def _get_spider_class(platform: str):
    class_path = SPIDER_MAP.get(platform)
    if not class_path:
        return None

    module_path, class_name = class_path.rsplit(".", 1)
    try:
        import importlib
        module = importlib.import_module(module_path)
        return getattr(module, class_name)
    except Exception as e:
        raise ImportError(f"Failed to load spider class {class_path}: {e}") from e


def main() -> None:
    if len(sys.argv) < 4:
        _emit({"error": "用法: spider_worker.py <platform> <platform_uid> <cookies_json> [user_id]"})
        return

    platform = sys.argv[1]
    platform_uid = sys.argv[2]
    cookies_json = sys.argv[3]
    user_id = sys.argv[4] if len(sys.argv) > 4 else ""

    try:
        cookies = json.loads(cookies_json) if cookies_json else {}
    except Exception:
        cookies = {}

    try:
        spider_cls = _get_spider_class(platform)
    except ImportError as e:
        _emit({"error": f"Spider类加载失败({platform}): {e}\n{_tb.format_exc()[-800:]}"})
        return
    if not spider_cls:
        _emit({"error": f"不支持的平台：{platform}"})
        return

    try:
        spider = spider_cls(
            user_id=user_id,
            platform_uid=platform_uid,
            cookies=cookies,
        )
        items = spider.start()

        serializable = []
        for item in items:
            d = {}
            for k, v in item.items():
                try:
                    json.dumps(v)
                    d[k] = v
                except Exception:
                    d[k] = str(v)
            serializable.append(d)

        _emit({"ok": True, "items": serializable})
    except Exception as e:
        _emit({"error": str(e)[:500]})


if __name__ == "__main__":
    main()