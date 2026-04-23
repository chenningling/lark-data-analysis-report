#!/usr/bin/env python3
"""生成飞书数据分析报告的标准本地产物包。

默认只输出可复盘的规划表、数据字典、清洗记录、中间结果、图表数据、
图表注册表、章节规划、结论索引、报告块和发布清单；不复制全量原始明细到
飞书 Base。只有显式传入 --include-source-rows 时才额外输出明细表。
"""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd


@dataclass
class ColumnMap:
    order_id: str | None
    sku: str | None
    date: str | None
    amount: str | None
    refund: str | None
    coupon: str | None
    region: str | None
    quantity: str | None
    price: str | None


def read_tables(paths: list[Path]) -> list[tuple[Path, str, pd.DataFrame]]:
    tables: list[tuple[Path, str, pd.DataFrame]] = []
    for path in paths:
        if path.suffix.lower() in {".xlsx", ".xls"}:
            workbook = pd.ExcelFile(path)
            for sheet in workbook.sheet_names:
                tables.append((path, sheet, pd.read_excel(path, sheet_name=sheet)))
        elif path.suffix.lower() in {".csv", ".tsv"}:
            sep = "\t" if path.suffix.lower() == ".tsv" else ","
            tables.append((path, path.stem, pd.read_csv(path, sep=sep)))
        else:
            raise SystemExit(f"不支持的文件类型：{path}")
    return tables


def first_match(columns: list[str], keywords: list[str]) -> str | None:
    lower = {col: col.lower().replace(" ", "").replace("_", "") for col in columns}
    for col in columns:
        value = lower[col]
        if any(keyword in value for keyword in keywords):
            return col
    return None


def detect_columns(df: pd.DataFrame) -> ColumnMap:
    columns = [str(col) for col in df.columns]
    return ColumnMap(
        order_id=first_match(columns, ["订单id", "订单号", "orderid", "order"]),
        sku=first_match(columns, ["商品sku", "sku", "商品", "product"]),
        date=first_match(columns, ["订单时间", "下单时间", "日期", "date", "time"]),
        amount=first_match(columns, ["总金额", "销售额", "gmv", "amount", "revenue", "sales"]),
        refund=first_match(columns, ["是否退款", "退款", "refund"]),
        coupon=first_match(columns, ["用券", "优惠", "coupon", "voucher"]),
        region=first_match(columns, ["订单位置", "地区", "省", "城市", "region", "location"]),
        quantity=first_match(columns, ["数量", "件数", "quantity", "qty"]),
        price=first_match(columns, ["单价", "price"]),
    )


def pct(value: float) -> str:
    return f"{value:.2%}"


def write_csv(output_dir: Path, name: str, frame: pd.DataFrame) -> dict[str, str]:
    path = output_dir / f"{name}.csv"
    frame.to_csv(path, index=False, encoding="utf-8-sig")
    return {"name": name, "csv": f"./outputs/{path.name}"}


def profile_table(path: Path, sheet: str, df: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for column in df.columns:
        series = df[column]
        samples = series.dropna().head(3).astype(str).tolist()
        rows.append(
            {
                "文件": path.name,
                "Sheet": sheet,
                "字段": str(column),
                "推断类型": str(series.dtype),
                "缺失数": int(series.isna().sum()),
                "缺失率": round(float(series.isna().mean()), 4),
                "唯一值数": int(series.nunique(dropna=True)),
                "样例值": ", ".join(samples),
                "业务含义": "由字段名和样例值推断，发布前可人工补充",
            }
        )
    return pd.DataFrame(rows)


def prepare_business_frame(df: pd.DataFrame, mapping: ColumnMap) -> pd.DataFrame:
    work = df.copy()
    if mapping.date:
        work["__日期"] = pd.to_datetime(work[mapping.date], errors="coerce")
        work["月份"] = work["__日期"].dt.to_period("M").astype(str)
        work["季度"] = work["__日期"].dt.to_period("Q").astype(str)
    if mapping.amount:
        work["GMV"] = pd.to_numeric(work[mapping.amount], errors="coerce").fillna(0)
    else:
        work["GMV"] = 0
    if mapping.refund:
        refund_raw = work[mapping.refund]
        if refund_raw.dtype == bool:
            work["是否退款_标准"] = refund_raw
        else:
            work["是否退款_标准"] = refund_raw.astype(str).str.lower().isin(["true", "是", "1", "yes", "y", "退款"])
    else:
        work["是否退款_标准"] = False
    work["有效销售额"] = work["GMV"].where(~work["是否退款_标准"], 0)
    work["退款金额"] = work["GMV"].where(work["是否退款_标准"], 0)
    work["退款订单数"] = work["是否退款_标准"].astype(int)
    return work


def aggregate(frame: pd.DataFrame, group: str, mapping: ColumnMap) -> pd.DataFrame:
    result = (
        frame.groupby(group, dropna=False)
        .agg(
            订单数=("GMV", "size"),
            GMV=("GMV", "sum"),
            有效销售额=("有效销售额", "sum"),
            退款订单数=("退款订单数", "sum"),
            退款金额=("退款金额", "sum"),
        )
        .reset_index()
    )
    result["退款率"] = result["退款订单数"] / result["订单数"]
    result["有效销售占比"] = result["有效销售额"] / result["GMV"].replace(0, math.nan)
    result["有效销售占比"] = result["有效销售占比"].fillna(0)
    for column in ["GMV", "有效销售额", "退款金额"]:
        result[column] = result[column].round(2)
    for column in ["退款率", "有效销售占比"]:
        result[column] = result[column].round(4)
    return result


def make_chart_spec(chart_id: str, title: str, chart_type: str, x: list[Any], series: list[dict[str, Any]], output: str, subtitle: str) -> dict[str, Any]:
    return {
        "id": chart_id,
        "title": title,
        "subtitle": subtitle,
        "type": chart_type,
        "x": [str(item) for item in x],
        "series": series,
        "output": output,
        "width": 1200,
        "height": 720,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="生成飞书数据分析报告标准产物包。")
    parser.add_argument("--input", nargs="+", required=True, help="Excel/CSV 文件路径")
    parser.add_argument("--goal", required=True, help="用户分析目标")
    parser.add_argument("--output", required=True, help="输出目录")
    parser.add_argument("--title", default="数据分析报告", help="飞书文档标题")
    parser.add_argument("--base-name", help="飞书 Base 名称")
    parser.add_argument("--include-source-rows", action="store_true", help="显式要求逐行审计时才写入清洗后明细表")
    args = parser.parse_args()

    inputs = [Path(item).expanduser().resolve() for item in args.input]
    run_dir = Path(args.output).expanduser().resolve()
    output_dir = run_dir / "outputs"
    charts_dir = output_dir / "charts"
    output_dir.mkdir(parents=True, exist_ok=True)
    charts_dir.mkdir(parents=True, exist_ok=True)

    loaded = read_tables(inputs)
    source_path, source_sheet, raw = loaded[0]
    mapping = detect_columns(raw)
    frame = prepare_business_frame(raw, mapping)
    now = datetime.now().strftime("%Y%m%d")
    base_name = args.base_name or f"数据分析过程记录仓库 - {args.goal[:18]} - {now}"

    data_dict = pd.concat([profile_table(path, sheet, df) for path, sheet, df in loaded], ignore_index=True)
    clean_log = pd.DataFrame(
        [
            ["R01", mapping.date or "未识别", "标准化日期字段并派生月份/季度", 0, "支持趋势和周期分析", "03_中间结果_周期经营基线", "S01"],
            ["R02", mapping.refund or "未识别", "标准化退款字段并派生有效销售额/退款金额", 0, "明确 GMV 与有效销售额口径", "03_中间结果_周期经营基线", "S01"],
            ["R03", "全表", "检查空值、字段类型和样例值", 0, "形成数据字典", "01_数据字典", "S01"],
        ],
        columns=["规则ID", "字段", "规则", "影响行数", "原因", "产出表", "关联步骤ID"],
    )

    tables: list[dict[str, str]] = []
    chart_specs: list[dict[str, Any]] = []
    chart_registry: list[list[Any]] = []
    sections: list[list[Any]] = []
    conclusions: list[list[Any]] = []
    doc_blocks: list[dict[str, str]] = [{"id": "RB00", "type": "markdown", "file": "./outputs/00_摘要.md"}]

    tables.append(write_csv(output_dir, "01_数据字典", data_dict))
    tables.append(write_csv(output_dir, "02_清洗记录", clean_log))
    if args.include_source_rows:
        tables.append(write_csv(output_dir, "10_清洗后数据明细", frame.drop(columns=[col for col in ["__日期"] if col in frame.columns])))

    steps: list[list[Any]] = [
        ["S01", "Q00", "SEC00", "", "数据画像与口径整理", "数据是否足够支持分析目标？", ";".join(path.name for path in inputs), "字段画像、空值检查、日期/金额/退款口径标准化", "01_数据字典;02_清洗记录", "完成", "默认不写全量原始明细，除非显式要求逐行审计"],
    ]

    if mapping.date and mapping.amount:
        month = aggregate(frame, "月份", mapping).sort_values("月份")
        quarter = aggregate(frame, "季度", mapping).sort_values("季度")
        month["图表ID"] = "CH01"
        tables.append(write_csv(output_dir, "03_中间结果_周期经营基线", quarter))
        tables.append(write_csv(output_dir, "90_图表数据_月度趋势", month))
        chart_specs.append(
            make_chart_spec(
                "CH01",
                "经营基线趋势",
                "line",
                month["月份"].tolist(),
                [
                    {"name": "GMV", "type": "line", "data": month["GMV"].tolist()},
                    {"name": "有效销售额", "type": "line", "data": month["有效销售额"].tolist()},
                    {"name": "退款率", "type": "line", "data": month["退款率"].tolist(), "yAxisIndex": 1, "value_type": "percent"},
                ],
                "./outputs/charts/CH01_经营基线趋势.png",
                "来源：Base 表 90_图表数据_月度趋势；渲染方式：ECharts PNG",
            )
        )
        chart_registry.append(["CH01", "SEC01", "经营基线趋势", "line", "90_图表数据_月度趋势", "月份", "GMV,有效销售额,退款率", "无", "经营基线趋势", "./outputs/charts/CH01_经营基线趋势.png", "RB01_CHART", "ECharts PNG"])
        steps.append(["S02", "Q01", "SEC01", "CH01", "经营基线计算", "目标应建立在什么经营基线上？", "标准化业务数据", "按月份/季度聚合 GMV、有效销售额和退款率", "03_中间结果_周期经营基线;90_图表数据_月度趋势", "完成", "有效销售额=未退款订单金额"])
        sections.append(["SEC01", "Q01", "S02", "CH01", "RB01_TEXT,RB01_CHART", "经营目标应先看有效销售额", "目标应建立在什么经营基线上？", "时间趋势 + 周期基线", "03_中间结果_周期经营基线;90_图表数据_月度趋势", "以有效销售额和退款率共同约束增长目标。", "中", "缺少更长周期时不做强季节性判断", "用有效销售额目标替代单一 GMV 目标"])
        conclusions.append(["C01", "SEC01", "CH01", "增长目标应采用有效销售额与退款率双指标。", "90_图表数据_月度趋势", "有效销售额,退款率", "经营基线趋势", "中", "建立目标和护栏", "高"])
        (output_dir / "RB01_TEXT.md").write_text("## 经营目标应先看有效销售额\n\n结论：增长规划不要只看 GMV，应同时看有效销售额和退款率。\n\n证据来自 `90_图表数据_月度趋势` 和 `03_中间结果_周期经营基线`。\n\n追溯：章节 `SEC01`；图表 `CH01`；仪表盘组件：`经营基线趋势`。\n", encoding="utf-8")
        doc_blocks += [
            {"id": "RB01_TEXT", "type": "markdown", "file": "./outputs/RB01_TEXT.md"},
            {"id": "RB01_CHART", "type": "image", "file": "./outputs/charts/CH01_经营基线趋势.png", "caption": "图：经营基线趋势（来源：Base 表 90_图表数据_月度趋势；仪表盘组件：经营基线趋势）"},
        ]

    dimensions = [
        ("sku", mapping.sku, "SKU机会分层", "91_图表数据_SKU机会分层", "CH02", "SEC02", "商品/SKU"),
        ("coupon", mapping.coupon, "优惠质量对比", "92_图表数据_优惠质量", "CH03", "SEC03", "优惠/活动"),
        ("region", mapping.region, "地区机会对比", "93_图表数据_地区机会", "CH04", "SEC04", "地区"),
    ]
    step_no = 3
    for _, column, title, table_name, chart_id, section_id, label in dimensions:
        if not column:
            continue
        grouped = aggregate(frame, column, mapping).sort_values("有效销售额", ascending=False)
        grouped["图表ID"] = chart_id
        top = grouped.head(12).copy()
        tables.append(write_csv(output_dir, table_name, top))
        chart_specs.append(
            make_chart_spec(
                chart_id,
                title,
                "bar",
                top[column].astype(str).tolist(),
                [
                    {"name": "有效销售额", "type": "bar", "data": top["有效销售额"].tolist()},
                    {"name": "退款率", "type": "line", "data": top["退款率"].tolist(), "yAxisIndex": 1, "value_type": "percent"},
                ],
                f"./outputs/charts/{chart_id}_{title}.png",
                f"来源：Base 表 {table_name}；渲染方式：ECharts PNG",
            )
        )
        chart_registry.append([chart_id, section_id, title, "bar", table_name, column, "有效销售额,退款率", "有效销售额 Top12", title, f"./outputs/charts/{chart_id}_{title}.png", f"RB{step_no - 1:02d}_CHART", "ECharts PNG"])
        steps.append([f"S{step_no:02d}", f"Q{step_no - 1:02d}", section_id, chart_id, f"{label}分层分析", f"哪些{label}应优先投入或修复？", "标准化业务数据", f"按{label}聚合有效销售额、退款率和有效销售占比", table_name, "完成", "只写 Top 图表数据，不默认复制全量明细"])
        sections.append([section_id, f"Q{step_no - 1:02d}", f"S{step_no:02d}", chart_id, f"RB{step_no - 1:02d}_TEXT,RB{step_no - 1:02d}_CHART", title, f"哪些{label}应优先投入或修复？", "分组聚合 + Top/风险对比", table_name, "优先关注高有效销售额且退款率可控的对象。", "中", "缺少成本、库存、渠道等辅助字段时不判断利润贡献", "建立投入名单和修复名单"])
        conclusions.append([f"C{step_no - 1:02d}", section_id, chart_id, f"{label}策略应同时看有效销售额和退款率。", table_name, f"{column},有效销售额,退款率", title, "中", "分层投入", "中"])
        block_id = f"RB{step_no - 1:02d}"
        (output_dir / f"{block_id}_TEXT.md").write_text(f"## {title}\n\n结论：优先关注高有效销售额且退款率可控的{label}，高规模高退款对象先诊断再放大。\n\n证据来自 `{table_name}`。\n\n追溯：章节 `{section_id}`；图表 `{chart_id}`；仪表盘组件：`{title}`。\n", encoding="utf-8")
        doc_blocks += [
            {"id": f"{block_id}_TEXT", "type": "markdown", "file": f"./outputs/{block_id}_TEXT.md"},
            {"id": f"{block_id}_CHART", "type": "image", "file": f"./outputs/charts/{chart_id}_{title}.png", "caption": f"图：{title}（来源：Base 表 {table_name}；仪表盘组件：{title}）"},
        ]
        step_no += 1

    task_plan = pd.DataFrame(steps, columns=["步骤ID", "关联问题ID", "关联章节ID", "关联图表ID", "步骤名称", "分析问题", "输入来源", "处理方法", "输出表", "状态", "口径/假设"])
    tables.insert(0, write_csv(output_dir, "00_任务规划", task_plan))
    registry = pd.DataFrame(chart_registry, columns=["图表ID", "章节ID", "图表名称", "图表类型", "来源表", "维度字段", "指标字段", "筛选条件", "仪表盘组件", "图片文件", "报告块ID", "渲染方式"])
    section_plan = pd.DataFrame(sections, columns=["章节ID", "问题ID", "步骤ID", "图表ID", "报告块ID", "章节标题", "决策问题", "分析方法", "证据表", "短答案", "置信度", "限制", "建议动作"])
    conclusion_index = pd.DataFrame(conclusions, columns=["结论ID", "章节ID", "图表ID", "结论", "证据表", "证据字段", "仪表盘组件", "置信度", "建议动作", "优先级"])
    tables += [
        write_csv(output_dir, "97_图表注册表", registry),
        write_csv(output_dir, "98_分析章节规划", section_plan),
        write_csv(output_dir, "99_结论索引", conclusion_index),
    ]

    (output_dir / "00_摘要.md").write_text(
        f"## 摘要\n\n分析目标：{args.goal}\n\n本报告默认不把全量原始明细复制到飞书 Base；Base 保留数据字典、清洗记录、中间结果、图表数据和结论索引，原始文件作为本地事实源。\n\n## 数据范围与口径\n\n- 输入文件：{', '.join(path.name for path in inputs)}\n- 主数据表：{source_sheet}，{len(raw)} 行，{len(raw.columns)} 列。\n- 自动识别字段：日期 `{mapping.date}`，金额 `{mapping.amount}`，退款 `{mapping.refund}`，SKU `{mapping.sku}`，优惠 `{mapping.coupon}`，地区 `{mapping.region}`。\n",
        encoding="utf-8",
    )
    (output_dir / "90_行动计划.md").write_text("## 行动计划\n\n详见 `99_结论索引`。下一步建议围绕高有效销售额、低退款风险对象做资源倾斜，并补齐成本、渠道和原因类字段。\n", encoding="utf-8")
    doc_blocks.append({"id": "RB90", "type": "markdown", "file": "./outputs/90_行动计划.md"})

    dashboard_blocks = [
        {
            "name": item[2],
            "type": "line" if item[3] == "line" else "bar",
            "data_config": {
                "table_name": item[4],
                "series": [{"field_name": "有效销售额", "rollup": "SUM"}],
                "group_by": [{"field_name": item[5].split(",")[0], "mode": "integrated", "sort": {"type": "group", "order": "asc"}}],
            },
        }
        for item in chart_registry
    ]
    manifest = {
        "base": {"name": base_name, "time_zone": "Asia/Shanghai"},
        "tables": tables,
        "dashboard": {"name": f"{args.goal[:20]}分析看板", "blocks": dashboard_blocks},
        "doc": {"title": args.title, "blocks": doc_blocks},
        "summary_path": "./outputs/publish_summary.json",
    }
    chart_payload = {"charts": chart_specs}
    (run_dir / "chart_specs.json").write_text(json.dumps(chart_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    (run_dir / "publish_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    (run_dir / "analysis_brief.json").write_text(
        json.dumps({"output": str(run_dir), "tables": len(tables), "charts": len(chart_specs), "include_source_rows": args.include_source_rows}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(str(run_dir))


if __name__ == "__main__":
    main()
