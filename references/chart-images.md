# 图表图片

在飞书文档中使用静态图表图片，以提升阅读体验；同时保持 Base 表和仪表盘作为数据事实源。

## 推荐流程

1. 在本地构造仪表盘就绪的结果表。
2. 将结果表写入飞书 Base。
3. 使用同一批结果表创建 Base 仪表盘组件。
4. 使用同一批表数据渲染本地图表图片。
5. 将图片插入飞书文档，并在图片说明中引用 Base 表和仪表盘组件。

## 辅助脚本

`scripts/render_chart_image.py` 可根据 JSON 规格渲染简单图表：

```bash
python3 scripts/render_chart_image.py --spec chart-spec.json --output chart.png
```

脚本会优先尝试使用 `pyecharts` + `snapshot-selenium`。如果不可用，则回退到 `matplotlib`。如果两种 PNG 渲染能力都不可用，可输出 `.svg`，使用脚本内置的标准库渲染器：

```bash
python3 scripts/render_chart_image.py --spec chart-spec.json --output chart.svg
```

`matplotlib` 和 SVG 兜底渲染都会设置中文字体候选项，以便在运行环境具备 CJK 字体时正常显示中文标签。

## 图表规格

```json
{
  "title": "月度销售额趋势",
  "subtitle": "来源：Base 表 90_图表数据_月度销售额",
  "type": "line",
  "x": ["2026-01", "2026-02", "2026-03"],
  "series": [
    {"name": "销售额", "data": [1200, 1800, 1600]}
  ],
  "y_label": "销售额",
  "source_table": "90_图表数据_月度销售额",
  "dashboard_block": "月度销售额趋势"
}
```

支持的 `type`：`line`、`bar`、`column`、`pie`、`ring`、`scatter`。

`pie` 和 `ring` 使用一个数据系列：

```json
{
  "title": "品类销售额占比",
  "type": "ring",
  "x": ["A品类", "B品类", "C品类"],
  "series": [{"name": "销售额", "data": [50, 30, 20]}]
}
```

## 图片说明格式

使用类似以下图片说明：

`图：月度销售额趋势（来源：Base 表 90_图表数据_月度销售额；仪表盘组件：月度销售额趋势）`

## 质量规则

- 使用与 Base 仪表盘组件相同的维度和指标。
- 图表标题保持简洁，并贴近业务语境。
- 使用可读的标签和单位。
- 中文文本需检查生成图片中是否出现缺字方框。
- 不把图表图片作为计算数据的唯一副本；底层数据必须写入 Base。
