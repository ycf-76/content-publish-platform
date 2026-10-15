"""Markdown to HTML/PDF/PNG conversion.

Uses python-markdown for HTML rendering, Playwright for PDF/PNG export.

Usage:
  python -m app.agents.prompts.scripts.doc_convert -i doc.md -o doc.html
  python -m app.agents.prompts.scripts.doc_convert -i doc.md -o doc.pdf --format pdf
  python -m app.agents.prompts.scripts.doc_convert -i doc.md -o doc.png --format png
"""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

import markdown

_CSS = """
<style>
body {
  font-family: -apple-system, "Microsoft YaHei", "PingFang SC", sans-serif;
  max-width: 800px; margin: 0 auto; padding: 2em;
  line-height: 1.8; color: #333; font-size: 16px;
}
h1 { font-size: 1.8em; border-bottom: 2px solid #eee; padding-bottom: 0.3em; }
h2 { font-size: 1.4em; border-bottom: 1px solid #eee; padding-bottom: 0.2em; }
h3 { font-size: 1.2em; }
code { background: #f5f5f5; padding: 2px 6px; border-radius: 3px; font-size: 0.9em; }
pre { background: #f5f5f5; padding: 1em; border-radius: 6px; overflow-x: auto; }
blockquote { border-left: 4px solid #ddd; margin-left: 0; padding-left: 1em; color: #666; }
table { border-collapse: collapse; width: 100%; }
th, td { border: 1px solid #ddd; padding: 8px 12px; text-align: left; }
th { background: #f5f5f5; }
img { max-width: 100%; }
</style>
"""


def md_to_html(md_text: str) -> str:
    extensions = ["tables", "fenced_code", "toc", "nl2br"]
    body = markdown.markdown(md_text, extensions=extensions)
    return f"<!DOCTYPE html><html><head><meta charset='utf-8'>{_CSS}</head><body>{body}</body></html>"


def convert(
    input_path: str | Path,
    output_path: str | Path,
    fmt: str = "html",
) -> Path:
    md_text = Path(input_path).read_text(encoding="utf-8")
    html = md_to_html(md_text)
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    if fmt == "html":
        out.write_text(html, encoding="utf-8")
        return out

    tmp_html = out.with_suffix(".tmp.html")
    tmp_html.write_text(html, encoding="utf-8")

    try:
        from app.agents.prompts.scripts.html2png import html_to_png

        if fmt == "png":
            return html_to_png(html_path=tmp_html, output_path=out, width=800, height=0, scale=2.0)
        elif fmt == "pdf":
            from playwright.sync_api import sync_playwright

            with sync_playwright() as pw:
                browser = pw.chromium.launch()
                page = browser.new_page()
                page.goto(f"file:///{tmp_html.resolve().as_posix()}")
                page.wait_for_load_state("networkidle")
                page.pdf(path=str(out), format="A4")
                browser.close()
            return out
        else:
            raise ValueError(f"Unsupported format: {fmt}")
    finally:
        tmp_html.unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Markdown format converter")
    parser.add_argument("-i", "--input", required=True, help="Markdown file path")
    parser.add_argument("-o", "--output", required=True, help="Output file path")
    parser.add_argument("--format", default=None, choices=["html", "pdf", "png"],
                        help="Output format (auto-detected from extension)")

    args = parser.parse_args()
    fmt = args.format or Path(args.output).suffix.lstrip(".")
    if fmt not in ("html", "pdf", "png"):
        fmt = "html"

    out = convert(args.input, args.output, fmt)
    print(f"Saved: {out}")


if __name__ == "__main__":
    main()