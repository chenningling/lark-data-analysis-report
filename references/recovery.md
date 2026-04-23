# 发布稳定性与失败恢复

飞书发布链路包含 Base、表、记录、仪表盘、文档和图片，属于高约束流程。优先使用 `scripts/publish_to_lark.py`，不要手工拼长命令。

## 优先发布方式

先将分析结果整理成本地 CSV、Markdown、图片和发布清单：

```bash
python3 scripts/prepare_analysis_package.py \
  --input ./input.xlsx \
  --goal "给出下个季度规划建议" \
  --output ./runs/task

node scripts/check_chart_runtime.mjs
node scripts/render_echarts_png.mjs --specs ./runs/task/chart_specs.json

python3 scripts/publish_to_lark.py \
  --manifest ./runs/task/publish_manifest.json \
  --cwd ./runs/task
```

脚本会：

- 默认不把全量原始明细写入 Base；只写可复盘的过程摘要和结果表。
- 在当前工作目录下创建 `.lark_publish_tmp/`，保证所有 `@file` 都是相对路径。
- 创建 Base、表、记录、仪表盘、文档和图片。
- 自动把 CSV 每 200 行分批写入。
- 写入 `*.state.json`，失败后可继续运行同一命令恢复。
- 输出 `publish_summary.json` 或 manifest 中指定的 `summary_path`。

## 发布清单格式

```json
{
  "base": {
    "name": "数据分析过程记录仓库 - 主题 - 20260423",
    "time_zone": "Asia/Shanghai"
  },
  "tables": [
    {
      "name": "00_任务规划",
      "csv": "./outputs/00_任务规划.csv"
    },
    {
      "name": "01_数据字典",
      "csv": "./outputs/01_数据字典.csv"
    },
    {
      "name": "90_图表数据_月度趋势",
      "csv": "./outputs/90_图表数据_月度趋势.csv"
    },
    {
      "name": "97_图表注册表",
      "csv": "./outputs/97_图表注册表.csv"
    },
    {
      "name": "98_分析章节规划",
      "csv": "./outputs/98_分析章节规划.csv"
    },
    {
      "name": "99_结论索引",
      "csv": "./outputs/99_结论索引.csv"
    }
  ],
  "dashboard": {
    "name": "数据分析看板",
    "blocks": [
      {
        "name": "月度有效销售额趋势",
        "type": "line",
        "data_config": {
          "table_name": "90_图表数据_月度趋势",
          "series": [{"field_name": "有效销售额", "rollup": "SUM"}],
          "group_by": [{"field_name": "月份", "mode": "integrated"}]
        }
      }
    ]
  },
  "doc": {
    "title": "数据分析报告",
    "blocks": [
      {
        "id": "RB00",
        "type": "markdown",
        "file": "./outputs/00_摘要.md"
      },
      {
        "id": "RB01_TEXT",
        "type": "markdown",
        "file": "./outputs/SEC01_经营基线.md"
      },
      {
        "id": "RB01_CHART",
        "type": "image",
        "file": "./outputs/charts/monthly.png",
        "caption": "图：月度有效销售额趋势（来源：Base 表 90_图表数据_月度趋势；仪表盘组件：月度有效销售额趋势）"
      },
      {
        "id": "RB90",
        "type": "markdown",
        "file": "./outputs/90_行动计划.md"
      }
    ]
  },
  "summary_path": "./outputs/publish_summary.json"
}
```

推荐使用 `doc.blocks`。脚本会按块顺序创建或追加 Markdown，并把图片插入到相邻位置。旧格式 `doc.markdown` + `doc.images` 仍可使用，但图片会统一追加到文档末尾，不适合“一节分析配一张图”的报告。

## 字段映射规则

发布脚本会清理字段 schema：

- 首字段强制使用 `text`，避免主字段不合法。
- 数字字段只传 `{"type":"number"}`，不要传 `precision`。
- 布尔、日期和复杂对象默认转文本，避免接口兼容问题。
- 只保留飞书 Base 支持的字段属性，忽略不支持的键。

## 常见失败与处理

### `@file must be a relative path`

原因：`lark-cli` 的 `@file` 参数不接受 `/tmp/xxx.json` 这类绝对路径。

处理：使用发布脚本；脚本会把临时 JSON 写入当前工作目录 `.lark_publish_tmp/` 并传相对路径。

### `Unrecognized key(s): precision`

原因：字段创建接口不接受 `precision`。

处理：不要手工传 `precision`；使用发布脚本自动清理字段属性。

### 表名冲突

原因：上次发布可能已经创建了表，或接口在报错前产生了半成品表。

处理：

- 如果是同一轮发布失败，保留 `.state.json`，直接重跑发布脚本。
- 如果 state 文件丢失，不要盲目复用同名表；先检查表字段和记录是否完整。
- 半成品 Base 不要自动删除，除非用户明确确认。
- 需要干净产物时，新建带时间后缀的 Base 名称。

### 批量记录写入失败

处理：

- 检查 CSV 字段名是否与 Base 字段完全一致。
- 检查单次记录数是否超过 200；发布脚本会自动分批。
- 检查是否写入了 formula、lookup 或系统字段；这些字段不应作为写入目标。
- 修复 CSV 后保留 state 重跑，脚本会从最近记录的批次继续。

### 仪表盘组件创建失败

处理：

- 检查 `data_config.table_name` 是否为真实 Base 表名。
- 检查 `series.field_name` 和 `group_by.field_name` 是否为真实字段名。
- 先保证数据表和记录写入完成，再创建组件。
- 组件必须串行创建。

### 文档创建成功但插图失败

处理：

- 保留 state 重跑，脚本会跳过已创建文档并继续插图。
- 使用 `doc.blocks` 时，脚本会记录每个 `RBxx` 的发布状态；修复图片后重跑会从未完成块继续。
- 若图片为 SVG，脚本会在 macOS 上尝试用 `sips` 转 PNG。
- 如果仍失败，先发布文档和 Base，并在最终回复里说明本地图片路径。

### 文档分块发布中断

处理：

- 不要修改已经发布的块 ID，保持 manifest 中 `doc.blocks` 顺序稳定。
- 修复缺失的 Markdown 或图片文件后重跑同一命令。
- 如果需要补充新章节，追加新的 `RBxx` 到 `doc.blocks` 末尾；避免在已发布块中间插入，以免文档顺序和 state 难以核对。
- 若必须重排报告，先确认用户接受创建新文档，或手工清理旧文档后再重新发布。

### 权限不足

处理：

- 运行 `lark-cli auth status` 确认 token 有效。
- 根据错误中的 `permission_violations` 申请最小 scope。
- 用户身份使用 `auth login`；应用身份不要执行用户授权。

## 运行后检查

发布完成后检查 `publish_summary.json`，至少应包含：

- `base.base_token` 和 `base.url`
- 每张表的行数
- `dashboard.dashboard_id`
- `doc.doc_id` 和 `doc.doc_url`
- 使用 `doc.blocks` 时，每个 `RBxx` 的发布状态

最终回复用户时返回飞书文档链接、Base 链接、仪表盘组件名称、关键结论和任何失败/跳过项。
