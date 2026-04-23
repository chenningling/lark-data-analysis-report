#!/usr/bin/env python3
"""根据 JSON 规格渲染简单图表图片。"""

from __future__ import annotations

import argparse
import html
import json
import math
from pathlib import Path
from typing import Any


def _load_spec(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _try_pyecharts(spec: dict[str, Any], output: Path) -> bool:
    try:
        from pyecharts import options as opts
        from pyecharts.charts import Bar, Line, Pie, Scatter
        from snapshot_selenium import snapshot
        from pyecharts.render import make_snapshot
    except Exception:
        return False

    chart_type = spec.get("type", "line")
    title_opts = opts.TitleOpts(title=spec.get("title", ""), subtitle=spec.get("subtitle", ""))
    x_values = spec.get("x", [])
    series = spec.get("series", [])

    if chart_type in {"bar", "column"}:
        chart = Bar().add_xaxis(x_values)
        for item in series:
            chart.add_yaxis(item.get("name", "series"), item.get("data", []))
        chart.set_global_opts(title_opts=title_opts)
    elif chart_type == "line":
        chart = Line().add_xaxis(x_values)
        for item in series:
            chart.add_yaxis(item.get("name", "series"), item.get("data", []), is_smooth=True)
        chart.set_global_opts(title_opts=title_opts)
    elif chart_type in {"pie", "ring"}:
        data = list(zip(x_values, series[0].get("data", []) if series else []))
        radius = ["40%", "70%"] if chart_type == "ring" else None
        chart = Pie().add(series[0].get("name", "series") if series else "series", data, radius=radius)
        chart.set_global_opts(title_opts=title_opts, legend_opts=opts.LegendOpts(orient="vertical", pos_left="left"))
    elif chart_type == "scatter":
        chart = Scatter().add_xaxis(x_values)
        for item in series:
            chart.add_yaxis(item.get("name", "series"), item.get("data", []))
        chart.set_global_opts(title_opts=title_opts)
    else:
        return False

    output.parent.mkdir(parents=True, exist_ok=True)
    make_snapshot(snapshot, chart.render(), str(output))
    return True


def _set_cjk_font(plt: Any) -> None:
    candidates = [
        "PingFang SC",
        "Microsoft YaHei",
        "SimHei",
        "Noto Sans CJK SC",
        "Arial Unicode MS",
        "Heiti SC",
    ]
    plt.rcParams["font.sans-serif"] = candidates + plt.rcParams.get("font.sans-serif", [])
    plt.rcParams["axes.unicode_minus"] = False


def _matplotlib_render(spec: dict[str, Any], output: Path) -> None:
    import matplotlib.pyplot as plt

    _set_cjk_font(plt)
    chart_type = spec.get("type", "line")
    x_values = spec.get("x", [])
    series = spec.get("series", [])

    fig, ax = plt.subplots(figsize=(10, 5.8), dpi=180)
    if chart_type in {"bar", "column"}:
        if len(series) == 1:
            ax.bar(x_values, series[0].get("data", []), label=series[0].get("name", "series"))
        else:
            width = 0.8 / max(len(series), 1)
            positions = list(range(len(x_values)))
            for idx, item in enumerate(series):
                offset = (idx - (len(series) - 1) / 2) * width
                ax.bar([pos + offset for pos in positions], item.get("data", []), width=width, label=item.get("name", "series"))
            ax.set_xticks(positions, x_values)
    elif chart_type == "line":
        for item in series:
            ax.plot(x_values, item.get("data", []), marker="o", linewidth=2, label=item.get("name", "series"))
    elif chart_type in {"pie", "ring"}:
        data = series[0].get("data", []) if series else []
        wedgeprops = {"width": 0.42} if chart_type == "ring" else None
        ax.pie(data, labels=x_values, autopct="%1.1f%%", startangle=90, wedgeprops=wedgeprops)
        ax.axis("equal")
    elif chart_type == "scatter":
        for item in series:
            data = item.get("data", [])
            if data and isinstance(data[0], list):
                xs = [point[0] for point in data]
                ys = [point[1] for point in data]
            else:
                xs = x_values
                ys = data
            ax.scatter(xs, ys, label=item.get("name", "series"))
    else:
        raise ValueError(f"不支持的图表类型：{chart_type}")

    ax.set_title(spec.get("title", ""), fontsize=16, pad=14)
    if spec.get("subtitle"):
        fig.text(0.5, 0.91, spec["subtitle"], ha="center", fontsize=10, color="#555555")
    if spec.get("y_label") and chart_type not in {"pie", "ring"}:
        ax.set_ylabel(spec["y_label"])
    if chart_type not in {"pie", "ring"}:
        ax.grid(axis="y", alpha=0.25)
        ax.legend(loc="best")
        plt.xticks(rotation=30, ha="right")
    fig.tight_layout()
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, bbox_inches="tight")


def _svg_render(spec: dict[str, Any], output: Path) -> None:
    if output.suffix.lower() != ".svg":
        raise RuntimeError(
            "当前没有可用的 PNG 渲染器。请安装 pyecharts+snapshot-selenium 或 matplotlib，"
            "也可以将 --output 设置为 .svg 路径，使用内置渲染器输出 SVG。"
        )

    chart_type = spec.get("type", "line")
    x_values = [str(value) for value in spec.get("x", [])]
    series = spec.get("series", [])
    width, height = 1000, 580
    left, right, top, bottom = 90, 40, 92, 92
    plot_w = width - left - right
    plot_h = height - top - bottom
    colors = ["#2563eb", "#16a34a", "#dc2626", "#9333ea", "#ea580c", "#0891b2"]

    def esc(value: Any) -> str:
        return html.escape(str(value), quote=True)

    def y_scale(value: float, max_value: float) -> float:
        if max_value == 0:
            return top + plot_h
        return top + plot_h - (value / max_value) * plot_h

    values = []
    for item in series:
        values.extend([float(v) for v in item.get("data", []) if isinstance(v, (int, float))])
    max_value = max(values) if values else 1
    max_value = max_value * 1.15 if max_value > 0 else 1

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="white"/>',
        f'<text x="{width/2}" y="36" text-anchor="middle" font-family="Arial, PingFang SC, Microsoft YaHei, sans-serif" font-size="24" font-weight="700">{esc(spec.get("title", ""))}</text>',
    ]
    if spec.get("subtitle"):
        parts.append(f'<text x="{width/2}" y="62" text-anchor="middle" font-family="Arial, PingFang SC, Microsoft YaHei, sans-serif" font-size="14" fill="#555">{esc(spec["subtitle"])}</text>')

    if chart_type in {"pie", "ring"}:
        data = [float(v) for v in (series[0].get("data", []) if series else [])]
        total = sum(data) or 1
        cx, cy, radius = width / 2, height / 2 + 20, 165
        start = -math.pi / 2
        for idx, value in enumerate(data):
            angle = (value / total) * math.tau
            end = start + angle
            large = 1 if angle > math.pi else 0
            x1, y1 = cx + radius * math.cos(start), cy + radius * math.sin(start)
            x2, y2 = cx + radius * math.cos(end), cy + radius * math.sin(end)
            color = colors[idx % len(colors)]
            parts.append(f'<path d="M {cx:.2f} {cy:.2f} L {x1:.2f} {y1:.2f} A {radius} {radius} 0 {large} 1 {x2:.2f} {y2:.2f} Z" fill="{color}" opacity="0.9"/>')
            mid = start + angle / 2
            lx, ly = cx + (radius + 35) * math.cos(mid), cy + (radius + 35) * math.sin(mid)
            label = x_values[idx] if idx < len(x_values) else idx + 1
            pct = value / total * 100
            parts.append(f'<text x="{lx:.2f}" y="{ly:.2f}" text-anchor="middle" font-family="Arial, PingFang SC, Microsoft YaHei, sans-serif" font-size="13">{esc(label)} {pct:.1f}%</text>')
            start = end
        if chart_type == "ring":
            parts.append(f'<circle cx="{cx}" cy="{cy}" r="78" fill="white"/>')
    else:
        parts.append(f'<line x1="{left}" y1="{top + plot_h}" x2="{left + plot_w}" y2="{top + plot_h}" stroke="#999"/>')
        parts.append(f'<line x1="{left}" y1="{top}" x2="{left}" y2="{top + plot_h}" stroke="#999"/>')
        for tick in range(5):
            value = max_value * tick / 4
            y = y_scale(value, max_value)
            parts.append(f'<line x1="{left}" y1="{y:.2f}" x2="{left + plot_w}" y2="{y:.2f}" stroke="#e5e7eb"/>')
            parts.append(f'<text x="{left - 10}" y="{y + 4:.2f}" text-anchor="end" font-family="Arial, PingFang SC, Microsoft YaHei, sans-serif" font-size="12" fill="#555">{value:.0f}</text>')
        n = max(len(x_values), 1)
        step = plot_w / max(n - 1, 1) if chart_type == "line" else plot_w / n
        if chart_type == "line":
            for sidx, item in enumerate(series):
                points = []
                for idx, value in enumerate(item.get("data", [])):
                    x = left + step * idx
                    y = y_scale(float(value), max_value)
                    points.append(f"{x:.2f},{y:.2f}")
                    parts.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="4" fill="{colors[sidx % len(colors)]}"/>')
                parts.append(f'<polyline fill="none" stroke="{colors[sidx % len(colors)]}" stroke-width="3" points="{" ".join(points)}"/>')
        elif chart_type in {"bar", "column"}:
            bar_w = step * 0.62 / max(len(series), 1)
            for sidx, item in enumerate(series):
                for idx, value in enumerate(item.get("data", [])):
                    x = left + step * idx + step * 0.19 + sidx * bar_w
                    y = y_scale(float(value), max_value)
                    parts.append(f'<rect x="{x:.2f}" y="{y:.2f}" width="{bar_w:.2f}" height="{top + plot_h - y:.2f}" fill="{colors[sidx % len(colors)]}" opacity="0.9"/>')
        for idx, label in enumerate(x_values):
            x = left + (step * idx if chart_type == "line" else step * idx + step / 2)
            parts.append(f'<text x="{x:.2f}" y="{top + plot_h + 28}" text-anchor="middle" font-family="Arial, PingFang SC, Microsoft YaHei, sans-serif" font-size="12" fill="#333">{esc(label)}</text>')
        for sidx, item in enumerate(series):
            lx = left + sidx * 150
            parts.append(f'<rect x="{lx}" y="{height - 30}" width="14" height="14" fill="{colors[sidx % len(colors)]}"/>')
            parts.append(f'<text x="{lx + 20}" y="{height - 18}" font-family="Arial, PingFang SC, Microsoft YaHei, sans-serif" font-size="13">{esc(item.get("name", "series"))}</text>')

    parts.append("</svg>")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(parts), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="根据 JSON 规格渲染图表图片。")
    parser.add_argument("--spec", required=True, help="图表规格 JSON 路径")
    parser.add_argument("--output", required=True, help="输出图片路径，支持 PNG 或 SVG")
    args = parser.parse_args()

    spec_path = Path(args.spec).expanduser().resolve()
    output = Path(args.output).expanduser().resolve()
    spec = _load_spec(spec_path)

    if not _try_pyecharts(spec, output):
        try:
            _matplotlib_render(spec, output)
        except ModuleNotFoundError:
            _svg_render(spec, output)
    print(str(output))


if __name__ == "__main__":
    main()
