# LLM Wiki Agent — 架构说明与工作流指令

这个维基百科（Wiki）完全由你的代码助手（coding agent）来维护。你**不需要任何 API Key**，也不需要运行 Python 脚本 —— 只需要在 Codex、OpenCode 或者其他能读这个文件的 AI 助手中打开本仓库，然后用自然语言跟它对话即可。

---

## 如何使用

用大白话直接说你想干什么就行：

- *"帮我收录这份文件：raw/papers/my-paper.md"*
- *"这个 wiki 里关于 transformer 模型都说了些什么？"*
- *"帮我检查一下 wiki 有没有孤立的页面和矛盾的内容"*
- *"帮我构建知识图谱"*

也可以用快捷命令来触发对应的工作流：

- `ingest <文件路径>` → 执行"资料收录工作流"（把一份文件收录到 wiki 中）
- `query: <你的问题>` → 执行"知识查询工作流"（从 wiki 中找答案）
- `health` → 执行"健康检查工作流"（检查 wiki 的结构是否完整，速度快，每次对话都可以跑）
- `lint` → 执行"代码检查工作流"（检查 wiki 的内容质量，比较耗资源，每隔一段时间跑一次就行）
- `build graph` → 执行"图谱构建工作流"（把所有 wiki 页面之间的链接关系可视化）
- `daemon` → 执行"守护进程工作流"（进入自主模式，自动监控新文件并处理）

---

## 目录结构说明

```
raw/          # 原始资料目录 —— 把你的文档放在这里，AI 助手永远不会修改这些文件
wiki/         # 知识库目录 —— AI 助手全权负责维护这个目录
  index.md    # 全局目录 —— 每次收录新资料时自动更新
  log.md      # 操作日志 —— 只追加不删除，记录每一次操作
  overview.md # 综合概述 —— 汇集所有资料精华的"活文档"，随知识增长而演进
  sources/    # 资料摘要 —— 每份原始资料对应一个摘要页
  entities/   # 实体页 —— 人物、公司、项目、产品等（AI 自动创建和更新）
  concepts/   # 概念页 —— 思想、框架、方法论、理论（AI 自动创建和更新）
  syntheses/  # 综合问答 —— 把查询结果存档为 wiki 页面
logs/         # 守护进程日志（自动创建）
graph/        # 知识图谱数据（自动生成）
tools/        # Python 工具脚本
  health.py   # 健康检查脚本（纯逻辑判断，不调用 AI，速度快）
  lint.py     # 质量检查脚本（需要调用 AI 做语义分析，比较慢）
  build_graph.py  # 知识图谱生成脚本
  daemon.py   # 后台守护进程（自动监控 raw/ 目录，发现新文件自动处理）
```

---

## 页面格式规范

每个 wiki 页面都必须以 YAML 格式的元数据（frontmatter）开头：

```yaml
---
title: "页面标题"
type: source | entity | concept | synthesis   # 页面类型：资料页/实体页/概念页/综合问答页
tags: []
sources: []       # 影响本页面的原始资料列表（用资料页的文件名 slug）
last_updated: YYYY-MM-DD   # 最后更新时间
---
```

页面之间使用 `[[页面名称]]` 这种维基链接语法来相互引用。例如 `[[Transformer]]` 会链接到概念页 Transformer。

---

## 资料收录工作流（Ingest Workflow）

触发方式：对 AI 助手说 *"收录 raw/papers/my-paper.md"* 或者 `ingest raw/papers/my-paper.md`

**支持的格式：** Markdown 文件（`.md`）可以直接收录。其他格式（`.pdf`、`.docx`、`.pptx`、`.xlsx`、`.html`、`.txt`、`.csv`、`.json`、`.xml`、`.rst`、`.rtf`、`.epub`、`.ipynb`、`.yaml`、`.yml`、`.tsv`、`.wav`、`.mp3`）会自动通过 [markitdown](https://github.com/microsoft/markitdown) 转换成 Markdown 后再收录。如果你不想自动转换，可以加 `--no-convert` 参数。

收录步骤（严格按以下顺序执行）：

1. **完整阅读原始文档**（如果不是 Markdown 格式，先转换成 Markdown）
2. **阅读 `wiki/index.md` 和 `wiki/overview.md`**，了解当前 wiki 中已经有什么知识
3. **创建资料摘要页** `wiki/sources/<slug>.md` —— 使用下面规定的"资料页格式"
4. **更新 `wiki/index.md`** —— 在 Sources（资料）分类下添加新条目
5. **更新 `wiki/overview.md`** —— 如果新资料补充了重要知识，修改综合概述
6. **创建或更新实体页** —— 如果文档中提到了重要的人物、公司、项目，创建对应的实体页
7. **创建或更新概念页** —— 如果文档中讨论了关键思想或框架，创建对应的概念页
8. **标记矛盾** —— 如果新资料与 wiki 中已有的知识有冲突，要在资料页中标记出来
9. **追加日志** —— 在 `wiki/log.md` 中追加一行：`## [YYYY-MM-DD] ingest | <标题>`
10. **收录后验证** —— 检查新创建的页面中的 `[[wikilinks]]` 是否指向存在的页面，确认所有新页面都已注册到 `index.md`，最后打印一份变更摘要

### 资料页的格式模板

```markdown
---
title: "资料标题"
type: source
tags: []
date: YYYY-MM-DD
source_file: raw/...
---

## 摘要
用 2-4 句话概括这篇资料的核心内容。

## 关键主张
- 主张 1：...
- 主张 2：...

## 关键引文
> "引文内容" —— 来源上下文说明

## 关联
- [[实体名称]] — 与这个实体有什么关系
- [[概念名称]] — 与这个概念有什么关系

## 矛盾
- 与 [[其他页面]] 在某个问题上存在矛盾：...
```

### 特定领域的模板

如果资料的来源属于某个特定领域（比如个人日记、会议记录），AI 助手应该使用下面这些专门的模板，而不是上面那个通用模板：

#### 日记模板
```markdown
---
title: "YYYY-MM-DD 日记"
type: source
tags: [日记]
date: YYYY-MM-DD
---
## 事件摘要
...
## 关键决定
...
## 精力与情绪
...
## 关联
...
## 变化与矛盾
...
```

#### 会议记录模板
```markdown
---
title: "会议标题"
type: source
tags: [会议]
date: YYYY-MM-DD
---
## 目标
...
## 关键讨论
...
## 做出的决定
...
## 待办事项
...
```

---

## 知识查询工作流（Query Workflow）

触发方式：对 AI 助手说 *"query: transformer 模型的核心创新是什么？"*

步骤：
1. 读取 `wiki/index.md`，找出与问题最相关的页面
2. 读取这些页面的完整内容
3. 综合所有相关信息，用 `[[页面名称]]` 维基链接格式标注引用来源，给出答案
4. 问用户是否要把答案存档到 `wiki/syntheses/<slug>.md`（这样以后别人问类似问题可以直接参考）

---

## 代码检查工作流（Lint Workflow）

触发方式：对 AI 助手说 *"lint"* 或 *"帮我检查 wiki 的质量问题"*

需要检查的项目：

- **孤页（Orphan Pages）** —— 没有其他页面通过 `[[链接]]` 指向它的页面
- **断裂链接（Broken Links）** —— `[[某个页面]]` 指向了一个不存在的页面
- **矛盾（Contradictions）** —— 不同页面之间对同一个问题的说法有冲突
- **过时的摘要（Stale Summaries）** —— 新资料已经更新了知识，但旧页面的摘要还没跟着更新
- **缺失的实体页（Missing Entity Pages）** —— 某个名称在 3 个以上的页面中被提到，但还没有自己的独立页面
- **链接稀疏页（Sparse Pages）** —— 出站链接少于 2 个的页面（链接密度预算不足，容易变成孤页）
- **数据缺口（Data Gaps）** —— 有哪些重要问题是这个 wiki 回答不了的，建议找到哪些资料来补充

如果已经有知识图谱数据（`graph.json`），还要做以下图谱层面的检查：
- **Hub Stub（大枢纽但内容少）** —— 度（连接数）超过平均值+2个标准差的节点，但内容不到 500 个字
- **脆弱桥梁（Fragile Bridges）** —— 两个社区之间只有 1 条边连接，一旦断了就彻底隔离
- **孤立社区（Isolated Communities）** —— 没有任何外部连接的集群，形成知识孤岛

输出一份结构化的检查报告，然后问用户是否要保存到 `wiki/lint-report.md`。

---

## 健康检查工作流（Health Workflow）

触发方式：对 AI 助手说 *"health"* 或 *"帮我检查 wiki 的结构完整性"*

执行命令：`python tools/health.py`（加 `--json` 参数可以输出机器可读的 JSON 格式）

快速的**结构完整性**检查 —— **完全不调用 AI**，每次对话都可以安全运行：

- **空文件/内容过少文件** —— 检查是否有页面只有元数据没有实际内容（可能是速率限制导致的写入不完整）
- **索引同步检查** —— `wiki/index.md` 中的记录是否与实际文件一致
- **日志覆盖检查** —— 是否有已经收录的资料页但缺少对应的 `ingest` 日志条目

输出健康检查报告。加 `--save` 参数可以保存到 `wiki/health-report.md`。

### 健康检查 vs 代码检查 的区别

| 维度 | 健康检查（health） | 代码检查（lint） |
|---|---|---|
| **检查范围** | 结构完整性 | 内容质量 |
| **是否调用 AI** | 不调用（纯代码逻辑） | 调用（语义分析） |
| **成本** | 免费 | 需要消耗 tokens |
| **运行频率** | 每次对话都建议跑一次 | 每收录 10-15 份资料跑一次 |
| **检查项目** | 空文件、索引同步、日志覆盖 | 孤页、断裂链接、矛盾、数据缺口 |
| **使用工具** | `tools/health.py` | `tools/lint.py` |
| **执行顺序** | 先跑 health（预检查） | 等 health 通过后再跑 |

> 一定要先跑 `health` 再跑 `lint` —— 对一个空文件做语义分析纯粹是浪费 tokens。

---

## 图谱构建工作流（Graph Workflow）

触发方式：对 AI 助手说 *"build graph"* 或 *"帮我构建知识图谱"*

优先尝试用 Python 脚本：`python tools/build_graph.py --open`

如果 Python 或依赖没装好，就手动构建：
1. 在所有 wiki 页面中搜索所有 `[[wikilinks]]` 维基链接
2. 构建节点列表（每个页面是一个节点）和边列表（每个链接是一条边）
3. 推断维基链接没有捕捉到的隐含关系——标记为 `INFERRED`（推断）并给出置信度分数；低置信度的标记为 `AMBIGUOUS`（模糊）
4. 写入 `graph/graph.json`，包含节点列表、边列表、构建日期
5. 写入 `graph/graph.html`，生成一个自包含的 vis.js 交互式可视化页面

---

## 守护进程工作流（Daemon Workflow）

触发方式：对 AI 助手说 *"daemon"* 或 *"启动守护进程"* 或 *"开启自动模式"*

启动一个后台监控程序，定时扫描 `raw/` 目录，一旦发现新的或修改过的文件，就**自动完成收录、修复断裂链接、重建知识图谱** —— 完全不需要人工干预。

执行命令：`python tools/daemon.py [--interval N] [--once] [--no-graph]`

参数说明：
- `--interval N` — 每隔 N 秒扫描一次 raw/ 目录（默认 30 秒）
- `--once` — 只运行一轮扫描就退出（适合配合系统的定时任务使用）
- `--no-graph` — 收录后不重建知识图谱（速度更快）
- `--log-file PATH` — 指定日志文件路径（默认是 `logs/daemon.log`）

### 每轮扫描都做了什么：
1. 递归扫描 `raw/` 目录，用 SHA256 哈希缓存来跳过已经处理过的文件
2. 对每个新文件调用 `ingest`（资料收录）
3. 调用 `heal` 自动修复断裂的 `[[wikilinks]]`
4. 重建知识图谱（除非加了 `--no-graph` 参数）
5. 把所有操作记录到 `logs/daemon.log` 和控制台

### 后台运行方式：
```bash
# 前台运行（默认方式）
python tools/daemon.py

# 后台运行（Linux/Mac）
nohup python tools/daemon.py > /dev/null 2>&1 &

# 配合 cron 定时任务，每小时跑一轮（跑完就退出）
0 * * * * cd /path/to/repo && python tools/daemon.py --once --no-graph

# 后台运行（Windows）
start /B python tools/daemon.py
```

守护进程支持通过 SIGINT（Ctrl+C）和 SIGTERM 信号优雅关闭。

---

## 命名规范

- **资料页**的文件名：使用`短横线命名法`（kebab-case），与原始文件名保持一致
- **实体页**的文件名：使用`大驼峰命名法`（TitleCase），例如 `OpenAI.md`、`SamAltman.md`
- **概念页**的文件名：使用`大驼峰命名法`（TitleCase），例如 `ReinforcementLearning.md`、`RAG.md`

### 链接与文件名的对应规则（重要）

`[[维基链接]]` 中的文字必须**严格等于**目标页面的文件名（不含 `.md` 扩展名），不能有偏差：

| 页面文件名 | 正确链接写法 | 错误链接写法 |
|---|---|---|
| `CharlieMunger.md` | `[[CharlieMunger]]` | ~~`[[查理·芒格]]`~~ |
| `MentalModels.md` | `[[MentalModels]]` | ~~`[[思维模型]]`~~ |
| `ReinforcementLearning.md` | `[[ReinforcementLearning]]` | ~~`[[强化学习]]`~~ |

**理由**：链接验证是机械的字符串匹配，它不知道 `CharlieMunger` 和 `查理·芒格` 是同一个东西。只有链接名 == 文件名，链接才能正常跳转。

## 索引文件格式

```markdown
# 维基索引

## 综合概述
- [综合概述](overview.md) — 汇集所有资料的精华

## 资料
- [资料标题](sources/slug.md) — 一句话摘要

## 实体
- [实体名称](entities/EntityName.md) — 一句话描述

## 概念
- [概念名称](concepts/ConceptName.md) — 一句话描述

## 综合问答
- [分析标题](syntheses/slug.md) — 回答的是什么问题
```

## 日志格式

每行日志的格式：`## [YYYY-MM-DD] <操作类型> | <标题>`

操作类型包括：`ingest`（收录）、`query`（查询）、`health`（健康检查）、`lint`（代码检查）、`graph`（图谱构建）、`daemon`（守护进程）、`report`（报告）

---

## 图谱健康报告

触发方式：对 AI 助手说 *"graph report"* 或执行 `python tools/build_graph.py --report`

`--report` 参数会生成一份结构化的图谱健康报告，包含以下内容：
- **健康概况** — 边/节点比率、孤页百分比、社区数量、链接密度
- **孤页节点** — 在图谱中没有连接的页面
- **超级枢纽节点** — 连接数超过平均值+2个标准差的页面（连接过于集中）
- **脆弱桥梁** — 两个社区之间只有 1 条边连接的情况
- **幽灵枢纽** — 被 2 个及以上现有页面通过 `[[wikilinks]]` 引用，但自身还不存在的页面（这是需要创建新页面的信号）

使用 `--save` 参数可以将报告保存到 `graph/graph-report.md`。

---

## 第三期设计约束（自动链接功能 —— 尚未实现）

第三期计划实现基于图谱分析的自动 `[[wikilink]]` 插入功能。以下是硬性规则：

### 晋升门槛：从草稿（draft）到正式（stable）
- 自动链接的边一开始都是「草稿」状态（图谱中可见，但不会写入页面正文）
- 专门的「晋升检查」会验证这些边是否有可靠的资料依据、是否与现有知识一致
- 只有通过检查的边才会真正作为 `[[wikilinks]]` 写入页面
- **链接密度预算**：一个页面的出站维基链接必须 ≥2 个，才能触发晋升检查

### 硬性规则
| 编号 | 规则 | 理由 |
|---|---|---|
| HG-WA-01 | 图谱层绝对不能根据断裂链接自动创建页面 —— 只能报告不能执行 | AI 收录时可能产生幻觉式的维基链接，自动创建页面会放大错误 |
| HG-WA-02 | 新增的斜杠命令不能与现有命令的功能重复 | 避免用户困惑，重复功能应该合并到现有命令中 |
