# LLM Wiki Agent — 架构说明与工作流指令

这个维基百科（Wiki）完全由 Gemini CLI 来维护。你**不需要任何 API Key**，也不需要运行 Python 脚本 —— 只需要在 Gemini CLI 中打开本仓库，然后用自然语言跟它对话即可。

---

## 如何使用

用大白话直接说你想干什么就行：

- *"帮我收录这份文件：raw/papers/my-paper.md"*
- *"这个 wiki 里关于 transformer 模型都说了些什么？"*
- *"帮我检查一下 wiki 有没有孤立的页面和矛盾的内容"*
- *"帮我构建知识图谱"*

也可以用快捷命令来触发对应的工作流：

- `ingest <文件路径>` → 执行"资料收录工作流"
- `query: <你的问题>` → 执行"知识查询工作流"
- `health` → 执行"健康检查工作流"（快速检查，每次对话都可以跑）
- `lint` → 执行"代码检查工作流"（比较耗时，定期跑）
- `build graph` → 执行"图谱构建工作流"
- `daemon` → 执行"守护进程工作流"（自主模式，自动监控新文件）

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

触发方式：说 *"收录 raw/papers/my-paper.md"* 或 `ingest raw/papers/my-paper.md`

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

触发方式：说 *"query: <你的问题>"*

1. 读取 `wiki/index.md`，找出最相关的页面
2. 读取这些页面的完整内容
3. 综合答案，用 `[[页面名称]]` 维基链接格式标注引用来源
4. 问用户是否要保存答案到 `wiki/syntheses/<slug>.md`

---

## 代码检查工作流（Lint Workflow）

触发方式：说 *"lint"*

检查以下项目：孤页、断裂链接、矛盾、过时的摘要、缺失的实体页（3+ 页面提到但没有独立页面）、稀疏页（出站链接少于 2 个）、数据缺口。

如果已有 `graph.json`，还要做图谱层面的检查：Hub Stub（高度连接但内容少）、脆弱桥梁（社区间单边连接）、孤立社区（无外部连接的集群）。

输出检查报告，问用户是否保存到 `wiki/lint-report.md`。

---

## 健康检查工作流（Health Workflow）

触发方式：说 *"health"*

执行：`python tools/health.py`

快速结构完整性检查，**完全不调用 AI**，每次对话都能安全运行：

- **空文件/内容过少** —— 页面没有实质内容
- **索引同步** —— `index.md` 记录 vs 实际文件
- **日志覆盖** —— 有资料页但缺少 ingest 日志

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

触发方式：说 *"构建知识图谱"* 或 `build graph`

首先尝试：`python tools/build_graph.py --open`

如果 Python/依赖不可用，手动构建：
1. 找出所有 `[[wikilinks]]`
2. 构建节点列表和边列表
3. 推断隐含关系 —— 标记 `INFERRED` 加置信度，低置信度标 `AMBIGUOUS`
4. 写入 `graph/graph.json`
5. 写入 `graph/graph.html`（自包含 vis.js 可视化）

---

## 守护进程工作流（Daemon Workflow）

触发方式：说 *"daemon"* 或 *"启动守护进程"*

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

支持 Ctrl+C 或 SIGTERM 优雅关闭。

---

## 命名规范

- 资料页：`短横线命名`（kebab-case）
- 实体/概念页：`大驼峰命名`（TitleCase.md）

## 日志格式

`## [YYYY-MM-DD] <操作类型> | <标题>`

操作类型：`ingest`（收录）、`query`（查询）、`health`（健康检查）、`lint`（代码检查）、`graph`（图谱构建）、`daemon`（守护进程）、`report`（报告）

---

## 图谱健康报告

触发方式：说 *"graph report"* 或执行 `python tools/build_graph.py --report`

涵盖：健康概况、孤页节点、超级枢纽节点、脆弱桥梁、幽灵枢纽（被引用但不存在的页面）。用 `--save` 保存到 `graph/graph-report.md`。

---

## 第三期设计约束（自动链接功能 —— 尚未实现）

- 自动链接的边从「草稿」状态开始，需要经过晋升检查验证
- 链接密度预算：出站链接 ≥2 个才能触发晋升
- HG-WA-01: 图谱层绝对不能根据断裂链接自动创建页面 —— 只能报告不能执行
- HG-WA-02: 新命令不能与现有命令的功能重复
