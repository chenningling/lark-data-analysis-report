#!/usr/bin/env python3
"""将分析产物稳定发布到飞书 Base、仪表盘和云文档。"""

from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


MAX_BATCH_ROWS = 200


class PublishError(RuntimeError):
    """发布流程中的可解释错误。"""


@dataclass
class Context:
    manifest_path: Path
    manifest: dict[str, Any]
    cwd: Path
    state_path: Path
    temp_dir: Path
    identity: str
    dry_run: bool
    keep_temp: bool
    state: dict[str, Any]


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def dump_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def run_cli(args: list[str], cwd: Path, dry_run: bool = False) -> dict[str, Any]:
    if dry_run:
        print("[dry-run]", " ".join(args))
        return {}
    proc = subprocess.run(args, cwd=cwd, text=True, capture_output=True)
    if proc.returncode != 0:
        message = proc.stderr.strip() or proc.stdout.strip() or f"命令失败：{' '.join(args)}"
        raise PublishError(message)
    output = proc.stdout.strip()
    if not output:
        return {}
    try:
        return json.loads(output)
    except json.JSONDecodeError as exc:
        raise PublishError(f"命令输出不是 JSON：{output[:800]}") from exc


def rel_for_cli(ctx: Context, path: Path) -> str:
    try:
        return "./" + str(path.resolve().relative_to(ctx.cwd.resolve()))
    except ValueError as exc:
        raise PublishError(f"CLI @file 必须位于当前工作目录内：{path}") from exc


def write_temp_json(ctx: Context, name: str, value: Any) -> str:
    safe_name = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in name)
    path = ctx.temp_dir / safe_name
    dump_json(path, value)
    return rel_for_cli(ctx, path)


def save_state(ctx: Context) -> None:
    if ctx.dry_run:
        return
    dump_json(ctx.state_path, ctx.state)


def require_lark_cli() -> None:
    if shutil.which("lark-cli") is None:
        raise PublishError("未找到 lark-cli，请先安装并配置飞书 CLI。")


def preflight(ctx: Context) -> None:
    require_lark_cli()
    result = run_cli(["lark-cli", "auth", "status"], ctx.cwd, dry_run=False)
    token_status = result.get("tokenStatus")
    scopes = result.get("scope", "")
    if token_status != "valid":
        raise PublishError("飞书授权状态无效，请先执行 lark-cli auth login。")
    required = [
        "base:app:create",
        "base:table:create",
        "base:record:create",
        "base:dashboard:create",
        "docx:document:create",
        "docs:document.media:upload",
    ]
    missing = [scope for scope in required if scope not in scopes]
    if missing:
        raise PublishError("缺少飞书权限 scope：" + ", ".join(missing))


def resolve_path(ctx: Context, value: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = ctx.manifest_path.parent / path
    return path.resolve()


def sanitize_field(field: dict[str, Any], primary: bool = False) -> dict[str, Any]:
    name = field.get("name")
    if not name:
        raise PublishError(f"字段缺少 name：{field}")
    field_type = field.get("type", "text")
    if primary:
        field_type = "text"
    allowed: dict[str, set[str]] = {
        "text": {"name", "type", "description"},
        "number": {"name", "type", "description"},
        "date": {"name", "type", "description"},
        "select": {"name", "type", "multiple", "options", "description"},
        "checkbox": {"name", "type", "description"},
    }
    if field_type not in allowed:
        field_type = "text"
    cleaned = {key: value for key, value in field.items() if key in allowed[field_type]}
    cleaned["name"] = name
    cleaned["type"] = field_type
    return cleaned


def infer_fields_from_csv(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
        columns = reader.fieldnames or []
    fields: list[dict[str, Any]] = []
    for idx, column in enumerate(columns):
        if idx == 0:
            fields.append({"name": str(column), "type": "text"})
        else:
            values = [row.get(column, "") for row in rows if row.get(column, "") not in {"", None}]
            is_number = bool(values) and all(is_number_like(value) for value in values)
            fields.append({"name": str(column), "type": "number" if is_number else "text"})
    return fields


def load_rows_from_csv(path: Path) -> tuple[list[str], list[list[Any]]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fields = [str(col) for col in (reader.fieldnames or [])]
        records = list(reader)
    rows: list[list[Any]] = []
    for record in records:
        rows.append([parse_cell(record.get(field, "")) for field in fields])
    return fields, rows


def is_number_like(value: str) -> bool:
    try:
        float(value)
        return True
    except (TypeError, ValueError):
        return False


def parse_cell(value: str | None) -> Any:
    if value is None or value == "":
        return None
    if is_number_like(value):
        number = float(value)
        if number.is_integer():
            return int(number)
        return number
    if value.lower() == "true":
        return "true"
    if value.lower() == "false":
        return "false"
    return value


def create_base(ctx: Context) -> str:
    if ctx.state.get("base", {}).get("base_token"):
        return ctx.state["base"]["base_token"]
    base_cfg = ctx.manifest["base"]
    args = [
        "lark-cli",
        "base",
        "+base-create",
        "--as",
        ctx.identity,
        "--name",
        base_cfg["name"],
        "--time-zone",
        base_cfg.get("time_zone", "Asia/Shanghai"),
    ]
    if base_cfg.get("folder_token"):
        args += ["--folder-token", base_cfg["folder_token"]]
    result = run_cli(args, ctx.cwd, ctx.dry_run)
    if ctx.dry_run:
        token = "dry_run_base_token"
        url = ""
    else:
        base = result.get("data", {}).get("base", {})
        token = base.get("base_token") or base.get("app_token")
        url = base.get("url", "")
        if not token:
            raise PublishError(f"创建 Base 后未取得 token：{result}")
    ctx.state["base"] = {"base_token": token, "url": url, "name": base_cfg["name"]}
    save_state(ctx)
    return token


def table_exists(ctx: Context, base_token: str, name: str) -> bool:
    if ctx.dry_run:
        return False
    result = run_cli(["lark-cli", "base", "+table-list", "--as", ctx.identity, "--base-token", base_token], ctx.cwd)
    tables = result.get("data", {}).get("tables", [])
    return any(table.get("name") == name for table in tables)


def create_table(ctx: Context, base_token: str, table: dict[str, Any]) -> None:
    name = table["name"]
    state = ctx.state.setdefault("tables", {}).setdefault(name, {})
    if state.get("records_written"):
        return
    csv_path = resolve_path(ctx, table["csv"])
    if not csv_path.exists():
        raise PublishError(f"表数据文件不存在：{csv_path}")
    if table_exists(ctx, base_token, name) and not state.get("table_created"):
        raise PublishError(
            f"Base 中已存在同名表但状态文件没有记录：{name}。"
            "请查看 references/recovery.md，确认复用或改名后再继续。"
        )
    raw_fields = table.get("fields") or infer_fields_from_csv(csv_path)
    fields = [sanitize_field(field, primary=(idx == 0)) for idx, field in enumerate(raw_fields)]
    fields_file = write_temp_json(ctx, f"fields_{name}.json", fields)
    if not state.get("table_created"):
        args = [
            "lark-cli",
            "base",
            "+table-create",
            "--as",
            ctx.identity,
            "--base-token",
            base_token,
            "--name",
            name,
            "--fields",
            f"@{fields_file}",
            "--view",
            '[{"name":"表格视图","type":"grid"}]',
        ]
        run_cli(args, ctx.cwd, ctx.dry_run)
        state["table_created"] = True
        save_state(ctx)
    record_fields, rows = load_rows_from_csv(csv_path)
    for start in range(state.get("rows_written", 0), len(rows), MAX_BATCH_ROWS):
        batch = rows[start : start + MAX_BATCH_ROWS]
        payload_file = write_temp_json(
            ctx,
            f"records_{name}_{start}.json",
            {"fields": record_fields, "rows": batch},
        )
        args = [
            "lark-cli",
            "base",
            "+record-batch-create",
            "--as",
            ctx.identity,
            "--base-token",
            base_token,
            "--table-id",
            name,
            "--json",
            f"@{payload_file}",
        ]
        run_cli(args, ctx.cwd, ctx.dry_run)
        state["rows_written"] = start + len(batch)
        save_state(ctx)
    state["records_written"] = True
    state["rows"] = len(rows)
    save_state(ctx)


def create_dashboard(ctx: Context, base_token: str) -> str | None:
    dashboard_cfg = ctx.manifest.get("dashboard")
    if not dashboard_cfg:
        return None
    if ctx.state.get("dashboard", {}).get("dashboard_id"):
        return ctx.state["dashboard"]["dashboard_id"]
    result = run_cli(
        [
            "lark-cli",
            "base",
            "+dashboard-create",
            "--as",
            ctx.identity,
            "--base-token",
            base_token,
            "--name",
            dashboard_cfg["name"],
        ],
        ctx.cwd,
        ctx.dry_run,
    )
    dashboard_id = "dry_run_dashboard_id"
    if not ctx.dry_run:
        dashboard_id = (
            result.get("data", {}).get("dashboard_id")
            or result.get("data", {}).get("dashboard", {}).get("dashboard_id")
            or result.get("dashboard_id")
        )
        if not dashboard_id:
            raise PublishError(f"创建仪表盘后未取得 dashboard_id：{result}")
    ctx.state["dashboard"] = {"dashboard_id": dashboard_id, "blocks": {}}
    save_state(ctx)
    return dashboard_id


def create_dashboard_blocks(ctx: Context, base_token: str, dashboard_id: str | None) -> None:
    dashboard_cfg = ctx.manifest.get("dashboard")
    if not dashboard_cfg or not dashboard_id:
        return
    block_state = ctx.state.setdefault("dashboard", {}).setdefault("blocks", {})
    for block in dashboard_cfg.get("blocks", []):
        name = block["name"]
        if block_state.get(name, {}).get("created"):
            continue
        args = [
            "lark-cli",
            "base",
            "+dashboard-block-create",
            "--as",
            ctx.identity,
            "--base-token",
            base_token,
            "--dashboard-id",
            dashboard_id,
            "--name",
            name,
            "--type",
            block["type"],
            "--data-config",
            json.dumps(block.get("data_config", {}), ensure_ascii=False),
        ]
        run_cli(args, ctx.cwd, ctx.dry_run)
        block_state[name] = {"created": True, "type": block["type"]}
        save_state(ctx)


def convert_image_if_needed(ctx: Context, image_path: Path) -> Path:
    if image_path.suffix.lower() != ".svg":
        return image_path
    sips = shutil.which("sips")
    if not sips:
        return image_path
    output = ctx.temp_dir / (image_path.stem + ".png")
    proc = subprocess.run([sips, "-s", "format", "png", str(image_path), "--out", str(output)], text=True, capture_output=True)
    if proc.returncode == 0 and output.exists():
        return output
    return image_path


def create_doc(ctx: Context) -> str | None:
    doc_cfg = ctx.manifest.get("doc")
    if not doc_cfg:
        return None
    if ctx.state.get("doc", {}).get("doc_id"):
        return ctx.state["doc"]["doc_id"]
    markdown_path = resolve_path(ctx, doc_cfg["markdown"])
    if not markdown_path.exists():
        raise PublishError(f"报告 Markdown 不存在：{markdown_path}")
    markdown_tmp = ctx.temp_dir / "report.md"
    markdown_tmp.write_text(markdown_path.read_text(encoding="utf-8"), encoding="utf-8")
    args = [
        "lark-cli",
        "docs",
        "+create",
        "--as",
        ctx.identity,
        "--title",
        doc_cfg["title"],
        "--markdown",
        f"@{rel_for_cli(ctx, markdown_tmp)}",
    ]
    for key, flag in [("folder_token", "--folder-token"), ("wiki_node", "--wiki-node"), ("wiki_space", "--wiki-space")]:
        if doc_cfg.get(key):
            args += [flag, doc_cfg[key]]
    result = run_cli(args, ctx.cwd, ctx.dry_run)
    doc_id = "dry_run_doc_id"
    doc_url = ""
    if not ctx.dry_run:
        data = result.get("data", result)
        doc_id = data.get("doc_id") or data.get("document_id") or data.get("token")
        doc_url = data.get("doc_url") or data.get("url") or ""
        if not doc_id:
            raise PublishError(f"创建文档后未取得 doc_id：{result}")
    ctx.state["doc"] = {"doc_id": doc_id, "doc_url": doc_url, "images": {}}
    save_state(ctx)
    return doc_id


def insert_images(ctx: Context, doc_id: str | None) -> None:
    doc_cfg = ctx.manifest.get("doc")
    if not doc_cfg or not doc_id:
        return
    image_state = ctx.state.setdefault("doc", {}).setdefault("images", {})
    for image in doc_cfg.get("images", []):
        source = resolve_path(ctx, image["file"])
        if not source.exists():
            raise PublishError(f"图表图片不存在：{source}")
        key = image.get("caption") or source.name
        if image_state.get(key, {}).get("inserted"):
            continue
        usable = convert_image_if_needed(ctx, source)
        if usable.resolve().is_relative_to(ctx.cwd.resolve()):
            file_arg = rel_for_cli(ctx, usable)
        else:
            copied = ctx.temp_dir / usable.name
            shutil.copyfile(usable, copied)
            file_arg = rel_for_cli(ctx, copied)
        args = [
            "lark-cli",
            "docs",
            "+media-insert",
            "--as",
            ctx.identity,
            "--doc",
            doc_id,
            "--file",
            file_arg,
            "--align",
            image.get("align", "center"),
            "--caption",
            image.get("caption", source.stem),
        ]
        run_cli(args, ctx.cwd, ctx.dry_run)
        image_state[key] = {"inserted": True, "file": str(source)}
        save_state(ctx)


def write_summary(ctx: Context) -> None:
    summary_path = Path(ctx.manifest.get("summary_path", ctx.cwd / "publish_summary.json"))
    if not summary_path.is_absolute():
        summary_path = ctx.manifest_path.parent / summary_path
    if ctx.dry_run:
        print(str(summary_path))
        return
    dump_json(summary_path, ctx.state)
    print(str(summary_path))


def validate_manifest(manifest: dict[str, Any]) -> None:
    if "base" not in manifest or not manifest["base"].get("name"):
        raise PublishError("manifest 缺少 base.name。")
    for table in manifest.get("tables", []):
        if not table.get("name") or not table.get("csv"):
            raise PublishError(f"表配置必须包含 name 和 csv：{table}")
    if manifest.get("doc") and (not manifest["doc"].get("title") or not manifest["doc"].get("markdown")):
        raise PublishError("doc 配置必须包含 title 和 markdown。")


def main() -> None:
    parser = argparse.ArgumentParser(description="稳定发布分析结果到飞书 Base、仪表盘和云文档。")
    parser.add_argument("--manifest", required=True, help="发布清单 JSON 路径")
    parser.add_argument("--state", help="状态文件路径；默认与 manifest 同目录")
    parser.add_argument("--identity", default="user", choices=["user", "bot"], help="飞书身份")
    parser.add_argument("--cwd", default=".", help="执行 lark-cli 的当前目录")
    parser.add_argument("--dry-run", action="store_true", help="只做校验并打印计划，不调用写入接口")
    parser.add_argument("--keep-temp", action="store_true", help="发布完成后保留临时文件")
    args = parser.parse_args()

    manifest_path = Path(args.manifest).expanduser().resolve()
    manifest = load_json(manifest_path)
    validate_manifest(manifest)
    cwd = Path(args.cwd).expanduser().resolve()
    cwd.mkdir(parents=True, exist_ok=True)
    state_path = Path(args.state).expanduser().resolve() if args.state else manifest_path.with_suffix(".state.json")
    temp_dir = cwd / ".lark_publish_tmp"
    temp_dir.mkdir(parents=True, exist_ok=True)
    state = load_json(state_path) if state_path.exists() else {"version": 1, "steps": []}
    ctx = Context(
        manifest_path=manifest_path,
        manifest=manifest,
        cwd=cwd,
        state_path=state_path,
        temp_dir=temp_dir,
        identity=args.identity,
        dry_run=args.dry_run,
        keep_temp=args.keep_temp,
        state=state,
    )
    try:
        if not args.dry_run:
            preflight(ctx)
        base_token = create_base(ctx)
        for table in manifest.get("tables", []):
            create_table(ctx, base_token, table)
        dashboard_id = create_dashboard(ctx, base_token)
        create_dashboard_blocks(ctx, base_token, dashboard_id)
        doc_id = create_doc(ctx)
        insert_images(ctx, doc_id)
        write_summary(ctx)
    finally:
        if not args.keep_temp and not args.dry_run:
            shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    try:
        main()
    except PublishError as exc:
        print(f"发布失败：{exc}", file=sys.stderr)
        sys.exit(1)
