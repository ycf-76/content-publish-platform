"""HTML to PNG export using Playwright.

Usage:
  python -m app.agents.prompts.scripts.html2png -i card.html -o card.png --width 1080 --height 1440
  python -m app.agents.prompts.scripts.html2png --html "<h1>Hello</h1>" -o out.png
"""

from __future__ import annotations

import argparse
import tempfile
from pathlib import Path

from playwright.sync_api import sync_playwright


def html_to_png(
    html_path: str | Path | None = None,
    html_content: str | None = None,
    output_path: str | Path = "output.png",
    width: int = 1080,
    height: int = 1440,
    scale: float = 2.0,
) -> Path:
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(
            viewport={"width": width, "height": height},
            device_scale_factor=scale,
        )
        if html_path:
            page.goto(f"file:///{Path(html_path).resolve().as_posix()}")
        elif html_content:
            page.set_content(html_content)
        else:
            raise ValueError("Provide html_path or html_content")

        page.wait_for_load_state("networkidle")
        page.screenshot(path=str(out), full_page=False)
        browser.close()

    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="HTML to PNG export")
    parser.add_argument("-i", "--input", help="HTML file path")
    parser.add_argument("--html", help="HTML content directly")
    parser.add_argument("-o", "--output", default="output.png")
    parser.add_argument("--width", type=int, default=1080)
    parser.add_argument("--height", type=int, default=1440)
    parser.add_argument("--scale", type=float, default=2.0)

    args = parser.parse_args()
    out = html_to_png(
        html_path=args.input,
        html_content=args.html,
        output_path=args.output,
        width=args.width,
        height=args.height,
        scale=args.scale,
    )
    print(f"Saved: {out}")


if __name__ == "__main__":
    main()