---
name: lark-data-analysis-report
description: 当用户提供一个或多个 Excel/CSV 表格，要求进行业务数据分析，并将分析过程、计算结果、可视化看板和图文分析报告发送沉淀到飞书中时使用。用户即使只提到“沉淀分析过程”“要可复盘/可追溯”“把结果放到飞书协作”，也应优先触发本技能。该技能会创建飞书多维表格作为分析过程记录仓库，按原子步骤写入数据表和结果表，建立飞书 Base 仪表盘，并创建飞书云文档报告引用对应的多维表格产物。
---

# 飞书数据分析报告

## 目标

使用本技能将本地表格分析转化为可追溯的飞书交付物：

1. 分析一个或多个 Excel/CSV 文件。
2. 创建新的飞书 Base，作为数据分析过程记录仓库。
3. 将数据源概览、中间计算、结果表和结论分别写入 Base 子表。
4. 基于结果表创建飞书 Base 仪表盘和图表组件。
5. 创建飞书云文档报告，写入分析洞察、引用 Base 表/仪表盘名称，并插入图表图片。
6. 返回飞书文档链接、飞书 Base 链接和简洁的实现摘要。

## 必读资料

只读取本次任务需要的参考文件：

- `references/workflow.md`：端到端执行清单和表结构设计模式。
- `references/analysis-methods.md`：根据用户问题选择分析方法、指标契约和分析严谨性规则。
- `references/report-planning.md`：动态规划报告章节，确保每个分析部分绑定问题、证据表、图表和行动建议。
- `references/lark-cli-commands.md`：使用飞书 CLI 创建 Base、仪表盘、文档、插入媒体或处理认证前阅读。
- `references/chart-images.md`：需要渲染可插入飞书文档的图表图片时阅读。
- `references/report-writing.md`：撰写最终分析报告前阅读。
- `references/recovery.md`：发布到飞书前阅读，尤其是需要稳定重试、续跑或处理半成品产物时。

## 作业流程

### 1. 理解分析任务

明确用户的业务目标、读者对象、输入文件、指标、分组维度、时间范围和期望写入位置。如果信息足够，直接推进，不额外追问。

先识别用户需求类型：增长规划、归因诊断、分群对比、优惠/活动评估、漏斗转化、cohort、质量风控或实验评估。根据需求类型读取 `references/analysis-methods.md` 和 `references/report-planning.md`，动态生成分析章节，不套固定报告模板。

创建原子化分析计划，包含：

- `analysis_goal`：报告要回答的业务问题。
- `inputs`：每个文件、工作表、行数、重要字段和数据质量备注。
- `steps`：按顺序排列的计算步骤，例如清洗、关联、分组、排序、趋势、贡献度、异常或 cohort 分析。
- `base_tables`：每个有意义阶段对应一张 Base 表。优先使用小而可审计的表，不把所有过程混成一个黑盒。
- `analysis_sections`：每个正文分析章节的业务问题、方法、证据表、图表、短答案、置信度、限制和行动建议。
- `dashboard_blocks`：由 `analysis_sections` 推导出的图表名称、来源表名、图表类型、维度、指标和筛选条件。

### 2. 剖析并准备数据

按文件类型选择合适的表格处理工具。辅助脚本 `scripts/profile_spreadsheets.py` 可快速检查 Excel/CSV 文件，并输出 JSON 格式的数据结构和质量画像：

```bash
python3 scripts/profile_spreadsheets.py --output /tmp/profile.json input.xlsx another.csv
```

为保证可重复写回，先在本地生成干净的表格产物：每张 Base 表对应一个 CSV 或 JSON 写入载荷。字段名尽量使用用户可读的中文或业务术语。

### 3. 创建飞书 Base 过程仓库

优先使用 `scripts/publish_to_lark.py` 统一发布 Base、表、记录、仪表盘、文档和图片。只有在用户明确要求手工控制，或脚本无法覆盖当前场景时，才直接调用 `lark-cli`。

使用脚本发布前，先生成：

- 每张 Base 表对应的 CSV 文件。
- 报告 Markdown 文件。
- 图表图片文件。
- `publish_manifest.json` 发布清单，格式见 `references/recovery.md`。

发布命令示例：

```bash
python3 scripts/publish_to_lark.py --manifest ./publish_manifest.json --cwd "$(pwd)"
```

如需手工创建 Base，使用 `lark-cli base +base-create` 创建新的 Base，名称建议跟随分析任务，例如 `数据分析过程记录仓库 - <主题> - YYYYMMDD`。

随后创建以下类型的子表：

- `00_任务规划`：分析目标、步骤顺序、输入来源、输出产物、状态。
- `01_数据字典`：文件/工作表/字段/类型/空值率/样例值/业务含义。
- `02_清洗记录`：清洗规则、影响行数、处理原因。
- 一张或多张中间结果表，名称包含步骤编号和计算内容。
- 一张或多张最终洞察表，直接作为仪表盘图表的数据源。
- `98_分析章节规划`：章节标题、决策问题、方法、证据表、图表、短答案、置信度、限制、建议动作。
- `99_结论索引`：结论、证据表、图表/仪表盘组件、置信度、建议动作。

写入规则：

- 记录批量写入时每批最多 200 行。
- 数字字段不要传 `precision`。
- `@file` 必须是当前工作目录内的相对路径。
- 失败后优先保留 state 文件重跑发布脚本，不要立刻新建重复 Base。

### 4. 创建 Base 仪表盘

使用发布脚本创建仪表盘；如需手工操作，再使用 `lark-cli base +dashboard-create` 创建仪表盘，并使用 `lark-cli base +dashboard-block-create` 基于最终洞察表添加组件。

按图表意图选择类型：

- 核心指标总览：`statistics`
- 时间趋势：`line` 或 `area`
- 类别比较/排序：`column` 或 `bar`
- 构成占比：`pie` 或 `ring`
- 漏斗转化：`funnel`
- 关系或双指标分布：`scatter`

图表组件必须串行创建。记录每个组件的名称、图表类型、来源表、维度和指标，供最终报告引用。

### 5. 为文档渲染图表图片

Base 仪表盘图表是可交互的数据源事实，但最终飞书文档应包含静态图表图片，方便阅读。图表必须服务于具体分析章节：一个正文分析部分原则上绑定一张图、一张证据表和一个行动建议。优先从同一批结果表生成本地图表图片，再用 `lark-cli docs +media-insert` 插入文档。

需要时使用 `scripts/render_chart_image.py`：

```bash
python3 scripts/render_chart_image.py --spec chart-spec.json --output chart.png
```

图表规格见 `references/chart-images.md`。尽量使用支持中文的字体，并让图片文件名与图表/组件名称保持一致。

### 6. 撰写飞书云文档报告

使用 `lark-cli docs +create` 创建报告。报告较长时，先创建简洁初稿，再用 `docs +update --mode append` 分段追加。通过发布脚本发布时，将完整 Markdown 写入 manifest 的 `doc.markdown`。

报告必须做到：

- 说明用户最初的分析目标。
- 解释数据范围、文件、工作表和主要数据质量限制。
- 根据用户分析目标动态组织章节，不使用固定模板硬套。
- 每个正文分析章节回答一个业务问题，并紧邻插入一张对应图表。
- 用证据支撑结论，而不是只贴图。
- 每个核心指标首次出现时说明口径、分子/分母、过滤条件和时间范围。
- 精确引用 Base 产物名称，例如 `Base 表：03_月度销售趋势` 和 `仪表盘组件：月度销售额趋势`。
- 插入与 Base 仪表盘同源数据生成的图表图片。
- 给出可执行的后续动作和限制说明。

### 7. 完成并返回

返回以下内容：

- 飞书文档标题和链接。
- 飞书 Base 标题、链接和 token。
- 仪表盘名称和关键组件名称。
- 已完成的实现内容。
- 数据质量限制或后续建议。

## 防护规则

- 访问用户个人云空间/文档资源时按需使用用户身份；仅在合适场景使用应用身份，并说明所有权和权限影响。
- 不输出 appSecret、accessToken 等密钥或访问令牌。
- 对已有飞书文档/Base 做破坏性修改或覆盖前，必须取得明确确认。
- 保持分析过程表可追溯。不要只发布精美报告而缺少中间证据。
- 不把截图作为唯一数据来源。Base 表是事实源，图片只是展示副本。
- 如果飞书命令返回缺失权限，按 `references/lark-cli-commands.md` 处理，并只请求最小必要 scope。
