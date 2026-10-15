"""Chart HTML generator using ECharts CDN (self-contained, no external API).

The LLM generates an ECharts option JSON, this script wraps it into
a standalone HTML file that renders in any browser / iframe.

Usage:
  python -m app.agents.prompts.scripts.chart_render -o chart.html --option '{"xAxis":{"type":"category","data":["A","B","C"]},"yAxis":{"type":"value"},"series":[{"type":"bar","data":[10,20,30]}]}'
  python -m app.agents.prompts.scripts.chart_render -i option.json -o chart.html
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Chart</title>
<script src="https://cdn.jsdelivr.net/npm/echarts@5.5.1/dist/echarts.min.js"></script>
<style>
  html, body {{ margin: 0; padding: 0; height: 100%; background: #fff; }}
  #chart {{ width: 100vw; height: 100vh; }}
</style>
</head>
<body>
<div id="chart"></div>
<script>
const option = {option_json};
const chart = echarts.init(document.getElementById('chart'), null, {{renderer: 'canvas'}});
chart.setOption(option);
window.addEventListener('resize', () => chart.resize());
</script>
</body>
</html>"""


def render_chart(
    option: dict,
    output_path: str | Path = "chart.html",
) -> Path:
    option_json = json.dumps(option, ensure_ascii=False, indent=2)
    html = _HTML_TEMPLATE.format(option_json=option_json)
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="Chart HTML generator (ECharts)")
    parser.add_argument("-i", "--input", help="ECharts option JSON file")
    parser.add_argument("--option", help="ECharts option JSON string")
    parser.add_argument("-o", "--output", default="chart.html")

    args = parser.parse_args()

    if args.input:
        option = json.loads(Path(args.input).read_text(encoding="utf-8"))
    elif args.option:
        option = json.loads(args.option)
    else:
        print("Error: provide --input or --option", file=sys.stderr)
        sys.exit(1)

    out = render_chart(option, args.output)
    print(f"Saved: {out}")


if __name__ == "__main__":
    main()