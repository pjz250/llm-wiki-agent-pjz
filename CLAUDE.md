# LLM Wiki Agent — 架构说明与工作流指令

这个维基百科（Wiki）完全由 Claude Code 来维护。你**不需要任何 API Key**，也不需要运行 Python 脚本 —— 只需要在 Claude Code 中打开本仓库，然后用自然语言跟它对话即可。

---

## 斜杠命令（仅限 Claude Code）

| 命令 | 对话示例 |
|---|---|
| `/wiki-ingest` | `ingest raw/my-article.md` |
| `/wiki-query` | `query: 这些资料的主题是什么？` |
| `/wiki-health` | `health`（快速检查，每次对话都能跑） |
| `/wiki-lint` | `帮我检查一下 wiki 的质量`（比较耗时，定期跑） |
| `/wiki-graph` | `构建知识图谱` |
| `/wiki-daemon` | `开启自动模式`（守护进程，自主运行） |

或者直接用大白话说你想干什么：

- *"帮我收录这份文件：raw/papers/attention-is-all-you-need.md"*
- *"这个 wiki 里关于 transformer 模型都说了些什么？"*
- *"帮我检查一下 wiki 有没有孤立的页面和矛盾的内容"*
- *"构建图谱，然后告诉我哪些页面和 RAG 概念是关联的"*

Claude Code 会自动读取本文件，并按照以下工作流规则执行。

---

## 目录结构说明

```
raw/          # 原始资料目录 —— 你的文档放在这里，助手永远不会修改
wiki/         # 知识库目录 —— 助手全权负责维护
  index.md    # 全局目录 —— 每次收录新资料时自动更新
  log.md      # 操作日志 —— 只追加不删除
  overview.md # 综合概述 —— 汇集所有资料的精华，随知识增长而演进
  sources/    # 资料摘要 —— 每份原始资料对应一个摘要页
  entities/   # 实体页 —— 人物、公司、项目、产品等（自动创建/更新）
  concepts/   # 概念页 —— 思想、框架、方法论、理论（自动创建/更新）
  syntheses/  # 综合问答 —— 把查询结果存档为 wiki 页面
logs/         # 守护进程日志（自动创建）
graph/        # 知识图谱数据（自动生成）
tools/        # Python 工具脚本
  health.py   # 健康检查脚本（纯逻辑判断，不调用 AI）
  lint.py     # 质量检查脚本（需要调用 AI 做语义分析）
  build_graph.py  # 知识图谱生成脚本
  daemon.py   # 后台守护进程（自动监控 raw/ 目录并处理新文件）
```

---

## 页面格式规范

每个 wiki 页面都必须以 YAML 格式的元数据（frontmatter）开头：

```yaml
---
title: "页面标题"
type: source | entity | concept | synthesis
tags: []
sources: []       # 影响本页面的原始资料列表
last_updated: YYYY-MM-DD   # 最后更新时间
---
```

页面之间使用 `[[页面名称]]` 这种维基链接语法来相互引用。

---

## 资料收录工作流（Ingest Workflow）

触发方式：说 *"收录 raw/papers/my-paper.md"* 或 `/wiki-ingest`

**支持的格式：** Markdown（`.md`）直接收录。非 Markdown 文件（`.pdf`、`.docx`、`.pptx`、`.xlsx`、`.html`、`.txt`、`.csv`、`.json`、`.xml`、`.rst`、`.rtf`、`.epub`、`.ipynb`、`.yaml`、`.yml`、`.tsv`、`.wav`、`.mp3`）会自动通过 [markitdown](https://github.com/microsoft/markitdown) 转换成 Markdown 后再收录。加 `--no-convert` 可以跳过自动转换。

### 收录步骤（严格按以下顺序执行）：

1. **完整阅读原始文档**（如果不是 Markdown，先转换成 Markdown）
2. **阅读 `wiki/index.md` 和 `wiki/overview.md`**，了解当前已有的知识
3. **创建资料摘要页** `wiki/sources/<slug>.md` —— 使用下面规定的资料页格式
4. **更新 `wiki/index.md`** —— 在 Sources（资料）分类下添加新条目
5. **更新 `wiki/overview.md`** —— 如果新资料补充了重要知识，修改综合概述
6. **创建或更新实体页** —— 人物、公司、项目等
7. **创建或更新概念页** —— 关键思想、框架等
8. **标记矛盾** —— 新资料与已有知识冲突时，在资料页中标记
9. **追加日志** —— `## [YYYY-MM-DD] ingest | <标题>`
10. **收录后验证** —— 检查 `[[wikilinks]]` 是否有效，确认所有新页面已注册到 `index.md`，最后打印变更摘要

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
2-4 句话概括核心内容。

## 关键主张
- 主张 1
- 主张 2

## 关键引文
> "引文内容" —— 来源上下文说明

## 关联
- [[实体名称]] — 与这个实体有什么关系
- [[概念名称]] — 与这个概念有什么关系

## 矛盾
- 与 [[其他页面]] 在某个问题上存在矛盾：...
```

### 特定领域的模板

如果资料属于某个特定领域，使用下面专门的模板：

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

触发方式：说 *"query: <你的问题>"* 或 `/wiki-query`

1. 读取 `wiki/index.md`，找出最相关的页面
2. 用 Read 工具读取这些页面的完整内容
3. 综合答案，用 `[[页面名称]]` 维基链接格式标注引用来源
4. 问用户是否要保存答案到 `wiki/syntheses/<slug>.md`

---

## 代码检查工作流（Lint Workflow）

触发方式：说 *"帮我检查 wiki 的质量"* 或 `/wiki-lint`

使用 Grep 和 Read 工具检查以下项目：

- **孤页** —— 没有入链的页面
- **断裂链接** —— `[[链接]]` 指向不存在的页面
- **矛盾** —— 跨页面说法冲突
- **过时的摘要** —— 新资料已更新但旧页面没跟上
- **缺失的实体页** —— 3+ 页面提到的名称但没有独立页面
- **稀疏页** —— 出站链接少于 2 个
- **数据缺口** —— wiki 回答不了的重要问题，建议找什么资料来补充

如果已有 `graph.json`，还要做图谱层面的检查：
- **Hub Stub** —— 高度连接的枢纽节点但内容很少
- **脆弱桥梁** —— 两个社区之间只有 1 条边连接
- **孤立社区** —— 完全没有外部连接的集群

输出检查报告，问用户是否保存到 `wiki/lint-report.md`。

---

## 健康检查工作流（Health Workflow）

触发方式：说 *"health"* 或 `/wiki-health`

执行：`python tools/health.py`（加 `--json` 可输出机器可读格式）

快速结构完整性检查，**完全不调用 AI**，每次对话都能安全运行：

- **空文件/内容过少** —— 页面没有实质内容
- **索引同步** —— `index.md` 记录 vs 实际文件
- **日志覆盖** —— 有资料页但缺少 ingest 日志

输出报告，加 `--save` 可保存到 `wiki/health-report.md`。

### 健康检查 vs 代码检查

| 维度 | 健康检查（health） | 代码检查（lint） |
|---|---|---|
| **范围** | 结构完整性 | 内容质量 |
| **AI 调用** | 不调用 | 调用（语义分析） |
| **成本** | 免费 | 消耗 tokens |
| **频率** | 每次对话 | 每 10-15 次收录 |
| **检查项目** | 空文件、索引、日志 | 孤页、断裂链接、矛盾等 |
| **工具** | `tools/health.py` | `tools/lint.py` |

> 先跑 health 再跑 lint —— 对空文件做语义分析是浪费 tokens。

---

## 图谱构建工作流（Graph Workflow）

触发方式：说 *"构建知识图谱"* 或 `/wiki-graph`

首先尝试：`python tools/build_graph.py --open`

如果 Python/依赖不可用，手动构建：
1. 用 Grep 找出所有 `[[wikilinks]]`
2. 构建节点列表和边列表
3. 推断维基链接未捕捉到的隐含关系 —— 标记 `INFERRED` 加置信度，低置信度标 `AMBIGUOUS`
4. 写入 `graph/graph.json`
5. 写入 `graph/graph.html`（自包含 vis.js 可视化）

---

## 守护进程工作流（Daemon Workflow）

触发方式：说 *"开启自动模式"* 或 `/wiki-daemon`

启动后台监控程序，定时扫描 `raw/` 发现新文件后自动处理。

执行：`python tools/daemon.py [--interval N] [--once] [--no-graph]`

参数：
- `--interval N` — 每隔 N 秒扫描一次（默认 30）
- `--once` — 只跑一轮就退出（适合配合系统定时任务）
- `--no-graph` — 收录后不重建图谱（更快）
- `--log-file PATH` — 指定日志路径（默认 `logs/daemon.log`）

### 每轮流程：
1. 扫描 `raw/` 新文件（SHA256 去重）
2. 对每个新文件运行收录
3. 运行自我修复，修复断裂链接
4. 重建知识图谱（除非加 `--no-graph`）
5. 记录日志到 `logs/daemon.log` 和控制台

### 后台运行：
```bash
# 前台
python tools/daemon.py

# 后台（Linux/Mac）
nohup python tools/daemon.py > /dev/null 2>&1 &

# 定时任务（每小时跑一轮）
0 * * * * cd /path/to/repo && python tools/daemon.py --once --no-graph

# 后台（Windows）
start /B python tools/daemon.py
```

支持 Ctrl+C 或 SIGTERM 优雅关闭。

---

## 命名规范

- 资料页：`短横线命名`（kebab-case）
- 实体页：`大驼峰命名`（TitleCase），如 `OpenAI.md`
- 概念页：`大驼峰命名`（TitleCase），如 `RAG.md`

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
- [分析标题](syntheses/slug.md) — 回答的问题
```

## 日志格式

每行以 `## [YYYY-MM-DD] <操作类型> | <标题>` 开头，方便用 grep 解析：

```
grep "^## \[" wiki/log.md | tail -10
```

操作类型：`ingest`（收录）、`query`（查询）、`health`（健康检查）、`lint`（代码检查）、`graph`（图谱构建）、`daemon`（守护进程）



# 单本书
python tools/pipeline.py raw/人类思想型/纯粹理性批判.md

# 整分类
python tools/pipeline.py raw/方法实践型/

# 全部
python tools/pipeline.py raw/

# 跳过收录，只做萃取
python tools/pipeline.py raw/方法实践型/搞定GTD.md --skip-ingest-book