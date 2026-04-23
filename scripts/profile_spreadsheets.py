#!/usr/bin/env python3
"""为飞书数据分析报告剖析 Excel/CSV 文件。"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any


def _infer_scalar(value: str) -> str:
    if value == "":
        return "empty"
    try:
        int(value)
        return "整数"
    except ValueError:
        pass
    try:
        float(value)
        return "数字"
    except ValueError:
        return "文本"


def _profile_delimited(path: Path, delimiter: str, sheet: str) -> dict[str, Any]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle, delimiter=delimiter)
        rows = list(reader)
    fields = []
    row_count = len(rows)
    for column in reader.fieldnames or []:
        values = [row.get(column, "") for row in rows]
        non_empty = [value for value in values if value != ""]
        type_counts: dict[str, int] = {}
        for value in non_empty:
            inferred = _infer_scalar(value)
            type_counts[inferred] = type_counts.get(inferred, 0) + 1
        inferred_type = max(type_counts, key=type_counts.get) if type_counts else "空"
        missing = row_count - len(non_empty)
        fields.append(
            {
                "file": str(path),
                "sheet": sheet,
                "field": str(column),
                "inferred_type": inferred_type,
                "missing_count": missing,
                "missing_rate": round(missing / row_count, 4) if row_count else 0,
                "unique_count": len(set(non_empty)),
                "sample_values": non_empty[:5],
            }
        )
    return {"file": str(path), "sheet": sheet, "rows": row_count, "columns": len(reader.fieldnames or []), "fields": fields}


def _sample_values(series: Any, limit: int = 5) -> list[str]:
    values = []
    for value in series.dropna().head(limit).tolist():
        values.append(str(value))
    return values


def _profile_frame(pd: Any, df: Any, file_path: Path, sheet: str) -> dict[str, Any]:
    row_count = int(len(df))
    fields = []
    for column in df.columns:
        series = df[column]
        missing = int(series.isna().sum())
        fields.append(
            {
                "file": str(file_path),
                "sheet": sheet,
                "field": str(column),
                "inferred_type": str(series.dtype),
                "missing_count": missing,
                "missing_rate": round(missing / row_count, 4) if row_count else 0,
                "unique_count": int(series.nunique(dropna=True)),
                "sample_values": _sample_values(series),
            }
        )
    return {"file": str(file_path), "sheet": sheet, "rows": row_count, "columns": len(df.columns), "fields": fields}


def profile_file(path: Path) -> list[dict[str, Any]]:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return [_profile_delimited(path, ",", "csv")]
    if suffix == ".tsv":
        return [_profile_delimited(path, "\t", "tsv")]

    try:
        import pandas as pd
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "剖析 Excel 文件需要 pandas/openpyxl。请使用工作区自带的 Python 运行时，"
            "或先安装表格处理依赖，再剖析 .xlsx/.xls 文件。"
        ) from exc

    if suffix in {".xlsx", ".xls", ".xlsm"}:
        sheets = pd.read_excel(path, sheet_name=None)
        return [_profile_frame(pd, df, path, str(name)) for name, df in sheets.items()]
    raise ValueError(f"不支持的文件类型：{path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="剖析表格结构和基础数据质量。")
    parser.add_argument("files", nargs="+", help="需要剖析的 Excel/CSV/TSV 文件")
    parser.add_argument("--output", "-o", required=True, help="输出 JSON 路径")
    args = parser.parse_args()

    profiles: list[dict[str, Any]] = []
    for raw_path in args.files:
        path = Path(raw_path).expanduser().resolve()
        if not path.exists():
            raise FileNotFoundError(path)
        profiles.extend(profile_file(path))

    out_path = Path(args.output).expanduser().resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps({"profiles": profiles}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(str(out_path))


if __name__ == "__main__":
    main()
