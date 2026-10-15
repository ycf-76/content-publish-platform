"""Mindmap HTML generator using markmap (CDN-based self-contained HTML).

Usage:
  python -m app.agents.prompts.scripts.mindmap make -i outline.md -o mm.html
  python -m app.agents.prompts.scripts.mindmap make --text "# Topic\n## Branch" -o mm.html
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Mindmap</title>
<style>
  html, body {{ margin: 0; padding: 0; height: 100%; overflow: hidden; }}
  #root {{ width: 100vw; height: 100vh; }}
  svg {{ width: 100%; height: 100%; }}
</style>
<script src="https://cdn.jsdelivr.net/npm/markmap-autoloader@0.17.0/dist/index.min.js"></script>
</head>
<body>
<div id="root">
<script>
window.markmap = {{
  options: {{
    duration: 300,
    maxWidth: 300,
    autoFit: true,
  }},
}};
</script>
<textarea style="display:none" id="markdown">
{markdown}
</textarea>
<script>
const md = document.getElementById('markdown').value;
const {{ Markmap }} = window.markmap;
const root = document.getElementById('root');
if (Markmap && Markmap.create) {{
  Markmap.create(root, window.markmap.options, md);
}} else if (window.markmap.autoLoader) {{
  window.markmap.autoLoader.render(root, md);
}}
</script>
</body>
</html>"""


def render_mindmap(
    markdown: str,
    output_path: str | Path | None = None,
) -> Path:
    html = _HTML_TEMPLATE.format(markdown=markdown)
    out = Path(output_path) if output_path else Path("mindmap.html")
    out.write_text(html, encoding="utf-8")
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="Mindmap HTML generator")
    sub = parser.add_subparsers(dest="cmd")

    make = sub.add_parser("make")
    make.add_argument("-i", "--input", help="Markdown outline file path")
    make.add_argument("--text", help="Markdown text directly")
    make.add_argument("-o", "--output", default="mindmap.html")

    args = parser.parse_args()
    if args.cmd != "make":
        parser.print_help()
        sys.exit(1)

    if args.input:
        md = Path(args.input).read_text(encoding="utf-8")
    elif args.text:
        md = args.text
    else:
        print("Error: provide --input or --text", file=sys.stderr)
        sys.exit(1)

    out = render_mindmap(md, args.output)
    print(f"Saved: {out}")


if __name__ == "__main__":
    main()