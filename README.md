# Agent 数据分析沉淀到飞书的 Skill

一个面向 Agent 的飞书数据分析 Skill：把 Excel/CSV 分析从“一次性回答”升级为可动态规划、可追溯、可复核、可协作的 Base、仪表盘和云文档交付物。

## 项目背景

很多 Agent 已经能较快完成表格统计、聚合和结论生成，但在真实业务分析里，难点并不只是“算出来”，而是“把一次分析组织成后续还能继续工作的产物”。如果 Agent 只是读完 Excel 后直接输出一段结论，后面一旦要补充问题、重算口径、追踪某张图的来源、把结果交给业务团队维护，之前那次分析就很容易退化成一段不可复用的聊天记录。

`lark-data-analysis-report` 关注的正是这层“分析组织能力”。它不是把固定模板套到所有问题上，而是先识别分析意图，再动态规划问题、步骤、章节、图表和交付结构。项目会把业务问题、分析步骤、结果表、图表、仪表盘组件和文档内容建立起可追溯映射关系：一条结论能回到对应的问题，一张图能回到对应的计算结果，一段正文也能找到它引用的数据来源。最后这些内容会统一发布到飞书 Base 和云文档中。报告中的图表使用 ECharts 渲染为 PNG 后插入飞书 Doc，保证展示层和底层证据链保持一致。这也是它和“只会读表给答案”的普通分析 Agent 的差别所在。

## 解决痛点

- **指标口径难统一，结论难复核**：很多分析结果能看懂，但很难快速回答“这个指标怎么算的”“过滤了哪些数据”“为什么这次和上次口径不同”。这个项目会把字段体检、清洗步骤、计算口径和结果表一起沉淀下来。
- **报告和底层数据脱节，图表来源难追踪**：不少报告里有数字、有图，但回头很难知道图来自哪张表、结论对应哪一步计算。这个项目会让结论、图表、结果表和文档内容互相对应。
- **分析产物分散，协作成本高**：当分析过程散落在本地脚本、聊天记录、临时表格和截图中，业务团队很难接手。这个项目把过程仓库、仪表盘和报告统一沉淀到飞书里，形成更稳定的协作入口。
- **追加问题或重算分析时容易从头再来**：业务方经常会在第一次结果出来后继续追问，例如调整一个指标口径、补一张图、增加一个分组维度。这个项目通过标准化步骤和结果结构，让 Agent 更容易在已有分析上继续工作，而不是全部重做。

## 功能框架

```text
用户问题 + Excel/CSV
        |
        v
1. 数据画像
   - 识别文件、工作表、字段、类型、缺失率、样例值
   - 生成数据字典和质量备注
        |
        v
2. 分析规划
   - 根据业务目标动态选择分析方法
   - 规划问题、计算步骤、Base 表、图表、报告章节
        |
        v
3. 本地产物包
   - 输出 Base 表 CSV
   - 输出 chart_specs.json
   - 输出报告 Markdown 块
   - 输出 publish_manifest.json
        |
        v
4. 图表渲染
   - 使用 ECharts + Puppeteer 渲染 PNG 图表
   - 图表用于插入飞书云文档
        |
        v
5. 飞书发布
   - 创建飞书 Base
   - 创建过程表、结果表、结论索引
   - 创建 Base 仪表盘和图表组件
   - 创建飞书云文档报告并插入图表
        |
        v
6. 交付链接
   - 飞书文档链接
   - 飞书 Base 链接
   - 仪表盘和关键组件摘要
```

## 项目结构

```text
.
├── SKILL.md                         # Skill 主说明，供 Agent 识别和执行
├── agents/openai.yaml               # Agent 展示名、默认提示词等元信息
├── references/                      # 工作流、分析方法、发布命令和恢复指南
├── scripts/profile_spreadsheets.py  # Excel/CSV 数据画像脚本
├── scripts/prepare_analysis_package.py
│                                      # 生成标准本地产物包
├── scripts/render_echarts_png.mjs   # 批量渲染 ECharts PNG 图表
├── scripts/publish_to_lark.py       # 发布 Base、仪表盘、文档和图片
└── package.json                     # 图表渲染运行时依赖
```

## 安装前置条件

安装本 Skill 前，请先安装并配置飞书 CLI：

[https://github.com/larksuite/cli.git](https://github.com/larksuite/cli.git)

安装完成后，确认本机可以执行：

```bash
lark-cli --help
```

首次使用飞书能力时，需要初始化和登录授权：

```bash
lark-cli config init --new
lark-cli auth login
```

如果后续发布时提示缺少权限 scope，请按错误提示补充最小必要权限。常见能力包括创建 Base、创建表、写入记录、创建仪表盘、创建文档和上传图片。

## 安装方式一：让 Agent 自主安装

用户可以打开本项目地址，然后向支持 Skill 安装的 Agent 发送一句话：

```text
请先确认我已经安装并配置飞书 CLI，然后从 https://github.com/chenningling/lark-data-analysis-report.git 安装 lark-data-analysis-report 这个 Skill。安装后帮我检查 Skill 是否可用。
```

## 安装方式二：手动 clone 到 Agent 技能目录

先克隆项目：

```bash
git clone https://github.com/chenningling/lark-data-analysis-report.git
```

然后把整个 `lark-data-analysis-report` 目录放到你的 Agent 指定技能目录中。不同 Agent 的目录可能不同，请以你的 Agent 文档为准。

常见示例：

```bash
# OpenClaw Skills 安装示例
mkdir -p ~/.openclaw/skills
cp -R lark-data-analysis-report ~/.openclaw/skills/
```

如果你的 Agent 使用其他目录，例如工作区级 skills、插件级 skills 或企业统一技能包目录，请将整个项目目录复制过去，确保目录中保留 `SKILL.md`、`references/`、`scripts/` 和 `package.json`。

## 安装图表运行时依赖

本 Skill 使用 ECharts + Puppeteer 渲染可插入飞书云文档的 PNG 图表。首次使用或换环境后，在 Skill 目录执行：

```bash
npm install
npm run check:charts
```

Python 分析脚本会使用 `pandas`、`openpyxl` 等表格处理依赖。多数 Agent 工作区会提供可用的 Python 数据分析运行时；如果本地缺少依赖，请在你的 Python 环境中安装：

```bash
python3 -m pip install pandas openpyxl
```

## 使用方式

安装完成后，把 Excel/CSV 文件提供给 Agent，然后使用类似提示：

```text
使用 $lark-data-analysis-report 分析这些 Excel 文件，并发布一份可追溯的飞书可视化报告。
```

也可以描述更具体的业务问题：

```text
使用 $lark-data-analysis-report 分析这份销售数据，找出下季度增长机会，把分析过程沉淀到飞书 Base，并生成一份带图表的飞书云文档报告。
```

执行完成后，Agent 应返回：

- 飞书云文档标题和链接
- 飞书 Base 标题、链接和 token
- 仪表盘名称和关键组件名称
- 已完成的分析步骤摘要
- 数据质量限制和后续建议

## 本地脚本流程

如果需要手动调试，可以按以下顺序运行：

```bash
python3 scripts/profile_spreadsheets.py --output /tmp/profile.json input.xlsx

python3 scripts/prepare_analysis_package.py \
  --input input.xlsx \
  --goal "分析销售趋势并给出增长建议" \
  --output ./runs/sales-analysis \
  --title "销售数据分析报告"

npm run check:charts
node scripts/render_echarts_png.mjs --specs ./runs/sales-analysis/chart_specs.json

python3 scripts/publish_to_lark.py \
  --manifest ./runs/sales-analysis/publish_manifest.json \
  --cwd ./runs/sales-analysis
```

默认情况下，Skill 不会把全量原始明细写入飞书 Base，只沉淀数据字典、清洗记录、中间结果、图表数据和结论索引。只有用户明确要求逐行审计、全量源数据沉淀或把明细也放进飞书时，才会发布明细表。

## 安全与权限提醒

- 请不要把 `appSecret`、`accessToken` 等密钥写入仓库或报告。
- 访问个人云空间、个人文档或用户文件时，优先使用用户身份授权。
- 对已有飞书文档或 Base 做覆盖、删除等破坏性操作前，应先获得明确确认。
- 如果飞书 CLI 提示权限不足，只申请当前任务需要的最小 scope。
- 图表图片只是展示副本，Base 表和本地计算产物才是事实来源。

## 适用场景

- 业务经营分析、销售分析、增长诊断
- 活动复盘、优惠券效果分析、漏斗转化分析
- 用户分群、SKU/品类贡献分析、区域表现对比
- 数据质量检查和可追溯分析过程沉淀
- 需要把分析结论交付到飞书协作空间的场景

## 许可

本项目采用 [MIT License](./LICENSE)。
