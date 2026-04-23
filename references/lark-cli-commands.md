# 飞书 CLI 命令参考

本技能内置数据分析报告流程所需的命令说明。飞书操作统一使用 `lark-cli`。

## 认证与身份

- 如需初始化应用配置：

```bash
lark-cli config init --new
```

- 访问用户个人云空间/文档资源时使用用户身份：

```bash
lark-cli auth login --scope "<missing_scope>"
```

- 当身份会影响资源归属或可见性时，明确使用 `--as user` 或 `--as bot`。
- 如果权限错误中列出 `permission_violations`，只申请缺失的最小 scope。若当前是应用身份，请让用户在开发者后台开通权限，不要执行 `auth login`。
- 不打印 appSecret、accessToken 或其他密钥。

## 创建 Base

```bash
lark-cli base +base-create \
  --name "数据分析过程记录仓库 - 主题 - 20260423" \
  --time-zone Asia/Shanghai
```

可选参数：`--folder-token fld_xxx`。

返回时说明 Base 链接和 token。如果输出中包含 `permission_grant`，总结当前用户权限授予结果：已授予、已跳过或失败。

## 创建数据表

```bash
lark-cli base +table-create \
  --base-token app_xxx \
  --name "00_任务规划"
```

需要同时创建字段时：

```bash
lark-cli base +table-create \
  --base-token app_xxx \
  --name "00_任务规划" \
  --fields '[{"name":"步骤ID","type":"text"},{"name":"步骤名称","type":"text"},{"name":"状态","type":"select","multiple":false,"options":[{"name":"待处理","hue":"Yellow","lightness":"Light"},{"name":"完成","hue":"Green","lightness":"Light"}]}]' \
  --view '[{"name":"表格视图","type":"grid"}]'
```

第一个字段会更新默认主字段。不要并发修改同一张表。

## 创建字段

```bash
lark-cli base +field-create \
  --base-token app_xxx \
  --table-id tbl_xxx \
  --json '{"name":"销售额","type":"number"}'
```

常用字段定义：

```json
{"name":"名称","type":"text"}
{"name":"数量","type":"number"}
{"name":"金额","type":"number"}
{"name":"日期","type":"date"}
{"name":"状态","type":"select","multiple":false,"options":[{"name":"完成","hue":"Green","lightness":"Light"}]}
{"name":"标签","type":"select","multiple":true,"options":[{"name":"重点","hue":"Red","lightness":"Light"}]}
```

公式字段和查找引用字段需要更详细的指南；除非报告需要在 Base 内长期保留派生字段，否则通常更清晰的做法是在本地计算后写入结果表。

> 稳定性提醒：当前 Base 字段创建接口不接受 `precision`。不要在字段 JSON 中传 `precision`，需要格式展示时后续在飞书界面或专门字段更新流程中处理。

## 批量创建记录

```bash
lark-cli base +record-batch-create \
  --base-token app_xxx \
  --table-id tbl_xxx \
  --json '{"fields":["步骤ID","步骤名称","状态"],"rows":[["S01","数据概览","完成"]]}'
```

规则：

- JSON 必须是包含 `fields` 和 `rows` 的对象。
- 字段顺序必须与每一行的值顺序一致。
- 空单元格使用 `null`。
- 单次最多写入 200 行。
- 只写入存储字段，不写入公式、查找引用或系统字段。

## 创建仪表盘

```bash
lark-cli base +dashboard-create \
  --base-token app_xxx \
  --name "销售分析看板"
```

记录返回的 `dashboard_id`。

## 创建仪表盘组件

组件必须串行创建：

```bash
lark-cli base +dashboard-block-create \
  --base-token app_xxx \
  --dashboard-id blk_xxx \
  --name "月度销售额趋势" \
  --type line \
  --data-config '{"table_name":"90_图表数据_月度销售额","series":[{"field_name":"销售额","rollup":"SUM"}],"group_by":[{"field_name":"月份","mode":"integrated","sort":{"type":"group","order":"asc"}}]}'
```

常用组件类型：

| 类型 | 用途 |
| --- | --- |
| `statistics` | 核心指标卡或总量统计 |
| `line` | 时间趋势 |
| `area` | 累积趋势 |
| `column` | 纵向类别比较 |
| `bar` | 横向排序 |
| `pie` / `ring` | 构成或占比 |
| `funnel` | 步骤转化 |
| `scatter` | 分布或关系 |
| `text` | 仪表盘说明文本 |

通用 `data_config` 示例：

```json
{
  "table_name": "90_图表数据_品类销售额",
  "series": [{"field_name": "销售额", "rollup": "SUM"}],
  "group_by": [{"field_name": "品类", "mode": "integrated", "sort": {"type": "value", "order": "desc"}}],
  "filter": {"conjunction": "and", "conditions": [{"field_name": "销售额", "operator": "isGreater", "value": 0}]}
}
```

统计记录数时使用 `count_all: true`，不要同时传 `series`。`series` 和 `count_all` 互斥。

`text` 组件示例：

```json
{"text":"# 数据说明\n本看板展示核心分析结果。"}
```

## 创建飞书云文档

```bash
lark-cli docs +create \
  --title "销售数据分析报告" \
  --markdown "## 摘要\n\n..."
```

可选写入位置：`--folder-token`、`--wiki-node` 或 `--wiki-space`。当返回的文档链接是 wiki 链接时，后续插入媒体请使用返回的 `doc_id`。

报告较长时，使用追加模式：

```bash
lark-cli docs +update \
  --doc doxcn_xxx \
  --mode append \
  --markdown "## 关键发现\n\n..."
```

除非用户明确要求替换整个文档，否则避免使用 `overwrite`。

## 插入图表图片

```bash
lark-cli docs +media-insert \
  --doc doxcn_xxx \
  --file ./charts/monthly-sales.png \
  --align center \
  --caption "图：月度销售额趋势（来源：Base 表 90_图表数据_月度销售额；仪表盘组件：月度销售额趋势）"
```

`--doc` 使用 `doc_id` 或 `/docx/` 链接。不要把 `/wiki/` 链接直接传给 `docs +media-insert`。

## 稳定发布脚本

完整发布流程优先使用：

```bash
python3 scripts/prepare_analysis_package.py --input ./input.xlsx --goal "分析目标" --output ./runs/task
node scripts/check_chart_runtime.mjs
node scripts/render_echarts_png.mjs --specs ./runs/task/chart_specs.json
python3 scripts/publish_to_lark.py --manifest ./runs/task/publish_manifest.json --cwd ./runs/task
```

脚本会自动处理：

- `@file` 相对路径约束。
- 字段 schema 清理。
- 每批 200 行记录写入。
- state 续跑。
- SVG 到 PNG 的尽力转换。

发布清单和失败恢复见 `references/recovery.md`。
