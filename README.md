# LLM Wiki Agent（智能维基助手）

[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

**一个给代码助手用的技能包。** 把原始文档丢进 `raw/` 目录，告诉 AI 助手"收录它"——它就会自动阅读文档、提取知识、构建一个持续关联的维基百科。每收录一份新资料，wiki 就变得更丰富。你**不需要自己动手写**任何 wiki 页面。

> 大多数知识工具让你去搜索自己的笔记。而这个工具会读取你收集的所有资料，自动写出一份结构化的维基百科，而且随时间不断积累——交叉引用已经建好了、矛盾已经标记了、综合归纳已经做好了。

```
ingest raw/papers/attention-is-all-you-need.md
```

```
wiki/
├── index.md          全局目录 —— 每次收录自动更新
├── log.md            操作日志 —— 只追加不删除
├── overview.md       综合概述 —— 汇集所有资料的精华
├── sources/          资料摘要 —— 每份原始资料对应一个摘要页
├── entities/         实体页 —— 人物、公司、项目等（自动创建）
├── concepts/         概念页 —— 思想、框架、方法等（自动创建）
└── syntheses/        综合问答 —— 把查询结果存档为 wiki 页面
graph/
├── graph.json        节点/边数据（SHA256 缓存）
└── graph.html        交互式 vis.js 可视化 —— 在浏览器中直接打开
```

## 安装

**需要：** [Claude Code](https://claude.ai/code)、[Codex](https://openai.com/codex)、[Gemini CLI](https://github.com/google-gemini/gemini-cli) 或其他能读配置文件的 AI 助手。

```bash
git clone https://github.com/SamurAIGPT/llm-wiki-agent.git
cd llm-wiki-agent
```

在 AI 助手中打开这个目录 —— **不需要 API Key 或 Python 环境配置**：

```bash
claude      # 会自动读取 CLAUDE.md + .claude/commands/（支持斜杠命令）
codex       # 会自动读取 AGENTS.md
opencode    # 会自动读取 AGENTS.md
gemini      # 会自动读取 GEMINI.md
```

## 使用方法

所有 AI 助手都理解自然语言和快捷触发命令：

```
ingest raw/papers/my-paper.md              # 收录一份 Markdown 资料
ingest report.pdf                          # 自动转换为 .md，然后收录
ingest slides.pptx notes.docx              # 批量收录，支持混合格式
query: 所有资料的核心主题是什么？           # 从 wiki 页面综合答案
lint                                       # 找出孤页、矛盾、数据缺口
build graph                                # 从所有维基链接构建知识图谱
```

直接说大白话也可以：

```
"帮我收录这篇论文：raw/papers/llama2.md"
"这个 wiki 里关于注意力机制都说了些什么？"
"帮我检查不同资料之间有没有矛盾"
"构建知识图谱，告诉我哪些节点连接最多"
```

**Claude Code** 还提供了 `/wiki-ingest`、`/wiki-query`、`/wiki-lint`、`/wiki-graph`、`/wiki-daemon` 这些斜杠命令（通过 `.claude/commands/` 目录）。这些是 Claude Code 专属的 —— 其他 AI 助手使用上面的自然语言触发方式，功能完全一样。

支持 Markdown、PDF、DOCX、PPTX、XLSX、HTML、TXT、CSV、JSON、XML、RST、EPUB 等多种格式。非 Markdown 文件在收录时会通过 [markitdown](https://github.com/microsoft/markitdown) 自动转换 —— 不需要额外的转换步骤。

---

## 自主模式

项目提供了**后台守护进程**，可以自动监控 `raw/` 目录并处理新文件：

```bash
# 前台运行（每 30 秒扫描一次）
python tools/daemon.py

# 后台运行（Windows）
start /B python tools/daemon.py

# 配合系统定时任务，每小时跑一轮
python tools/daemon.py --once --no-graph
```

守护进程每轮自动执行：检测新文件 → 收录 → 修复断裂链接 → 重建知识图谱。

---

## 你能得到什么

**持久化的维基** —— 结构化的 Markdown 页面，跨会话持续积累。和聊天不同，知识不会丢失。

**实体页** —— 每提到一个人物、公司、项目，都会自动创建实体页。每次新资料提及它们时自动更新。

**概念页** —— 每个关键思想或框架都自动创建概念页，交叉引用到所有讨论它的资料。

**活的综合概述** —— `wiki/overview.md` 在每次收录时都会更新，反映当前所有资料的综合理解。

**矛盾标记** —— 新资料与已有知识冲突时，在收录时当场标记，不会等到你去查的时候才发现。

**知识图谱** —— `graph.html` 把每个 wiki 页面显示为一个节点，每个 `[[维基链接]]` 显示为一条边，AI 推断的隐含关系显示为虚线边。社区检测自动聚类相关主题。

**质量检查报告** —— 找出孤页、断裂链接、缺失的实体页、数据缺口，并建议补充什么资料。

## 使用场景

### 学术研究

花几周深入某个课题 —— 读论文、文章、报告。

```
/wiki-ingest raw/papers/attention-is-all-you-need.md
/wiki-ingest raw/papers/llama2.md
/wiki-ingest raw/papers/rag-survey.md

# Wiki 自动构建实体页（Meta AI、Google Brain）和
# 概念页（注意力机制、RLHF、上下文窗口）。

/wiki-query "减少幻觉的主要方法有哪些？"
/wiki-query "不同模型的上下文窗口大小是如何演变的？"

/wiki-lint
# → "没有关于混合专家模型（MoE）的资料 —— 建议找找 Mixtral 论文"
```

最后你得到的是一份结构化的、交叉引用的参考资料 —— 而不是一个永远不会再打开的 PDF 文件夹。

---

### 读书笔记

边读边整理每一章。自动构建角色、主题、论点的页面。

```
/wiki-ingest raw/book/chapter-01.md
/wiki-ingest raw/book/chapter-02.md

# Wiki 自动创建角色和主题页面。

/wiki-query "主角的动机是如何演变的？"
/wiki-query "作者的论证中存在哪些矛盾？"

/wiki-graph   # → graph.html 显示每个角色/主题以及它们之间的关联
```

就像托尔金维基（Tolkien Gateway）那样 —— 边读边建，AI 帮你做所有的交叉引用。

---

### 个人知识库

追踪目标、健康、习惯、自我提升 —— 归档日记、文章、播客笔记。

```
/wiki-ingest raw/journal/2026-01-week1.md
/wiki-ingest raw/articles/huberman-sleep-protocol.md
/wiki-ingest raw/articles/atomic-habits-summary.md

/wiki-query "我的日记里关于精力有什么模式？"
/wiki-query "我尝试过哪些习惯，结果怎么样？"
```

Wiki 随着时间的推移构建出一幅结构化的画面。"睡眠"、"运动"、"深度工作"等概念从每份归档的资料中积累证据。

---

### 商业/团队情报

输入会议记录、项目文档、客户通话。

```
/wiki-ingest raw/meetings/q1-planning-transcript.md
/wiki-ingest raw/docs/product-roadmap-2026.md
/wiki-ingest raw/calls/customer-interview-acme.md

/wiki-query "客户通话中最常提到的功能需求是什么？"
/wiki-query "第一季度做了什么决定，理由是什么？"

/wiki-lint
# → "项目 X 在 5 个页面中被提到但没有独立页面"
# → "路线图和客户访谈在功能 Y 的优先级上存在矛盾"
```

Wiki 始终是最新的，因为 AI 替你做完了没人愿意做的维护工作。

---

### 竞品分析

追踪公司、市场、技术。

```
/wiki-ingest raw/competitors/openai-announcements.md
/wiki-ingest raw/market/ai-funding-report-q1.md

/wiki-query "OpenAI 和 Anthropic 在安全方法上有什么不同？"
/wiki-query "过去 6 个月有哪些公司发布了多模态模型？"
/wiki-query "当前竞争格局总结"
# → AI 展示答案，然后问你要不要把它保存为综合问答页
```

---

## 知识图谱

两遍构建：

1. **确定性构建** —— 解析所有 wiki 页面中的 `[[维基链接]]` → 边标记为 `EXTRACTED`
2. **语义推断** —— AI 推断维基链接没有捕捉到的隐含关系 → 边标记为 `INFERRED`（带置信度）或 `AMBIGUOUS`（模糊）

Louvain 社区检测按主题聚类节点。SHA256 缓存意味着只有变更的页面才会被重新处理。输出是自包含的 `graph.html` —— 不需要服务器，在浏览器中直接打开。

## CLAUDE.md / AGENTS.md 配置文件

这些架构说明文件告诉 AI 助手如何维护 wiki —— 页面格式、收录/查询/检查/图谱工作流、命名规范。这是关键的配置文件。编辑它们可以自定义在你特定领域中的行为。

| AI 助手 | 对应的配置文件 |
|---|---|
| Claude Code | `CLAUDE.md` |
| Codex / OpenCode | `AGENTS.md` |
| Gemini CLI | `GEMINI.md` |

## 和 RAG（检索增强生成）有什么不同

| RAG | LLM Wiki Agent（智能维基） |
|---|---|
| 每次查询都重新推导知识 | 一次性编译，持续保持最新 |
| 原始文本块作为检索单元 | 结构化的 Wiki 页面 |
| 没有交叉引用 | 交叉引用预先建好 |
| 矛盾在查询时才暴露（可能根本发现不了） | 在收录时当场标记 |
| 没有累积效应 | 每份资料都让 wiki 更丰富 |

## Obsidian 集成

这个 wiki 设计为可以在 [Obsidian](https://obsidian.md) 中无缝浏览。由于 AI 助手维护着一致的 `[[维基链接]]`，你的知识库中会自然生长出一个知识图谱。

### 仓库链接模式
如果你想保持 LLM Wiki Agent 仓库和主 Obsidian 仓库分离，可以使用符号链接：

1. 把工作仓库放在例如 `~/llm-wiki-agent`
2. 从 Obsidian 仓库创建符号链接：
   ```bash
   ln -sfn ~/llm-wiki-agent/wiki ~/你的Obsidian仓库/wiki
   ```
3. 使用 [Obsidian Web Clipper](https://obsidian.md/clipper) 或直接向 agent 仓库的 `raw/` 写入来排队处理资料。

> **注意：** 如果你移动了本地仓库目录，记得更新符号链接，否则 `wiki/` 目录在 Obsidian 中会显示为丢失。

### 推荐的 Obsidian 配置
- **关系图谱视图：** 过滤掉 `index.md` 和 `log.md`（例如 `-file:index.md -file:log.md`），避免它们成为 Obsidian 图谱中的"引力井"。
- **Dataview 插件：** 使用社区插件 [Dataview](https://blacksmithgu.github.io/obsidian-dataview/) 来查询 AI 助手自动注入的 YAML frontmatter（例如 `type: source`、`tags: [日记]`）。

## 多种格式的收录

把任何支持的文件直接丢给 `ingest` —— 不需要单独的转换步骤：

```bash
# 以下都能工作 —— 收录时自动转换
ingest report.pdf
ingest meeting-notes.docx
ingest slides.pptx
ingest data.xlsx
ingest page.html
ingest raw/mixed-folder/          # 递归查找所有支持的文件
```

**支持的格式：**
`.md` `.pdf` `.docx` `.pptx` `.xlsx` `.xls` `.html` `.htm` `.txt` `.csv` `.json` `.xml` `.rst` `.rtf` `.epub` `.ipynb` `.yaml` `.yml` `.tsv` `.wav` `.mp3`

非 Markdown 文件通过 [markitdown](https://github.com/microsoft/markitdown) 自动转换。加 `--no-convert` 可以跳过自动转换，只处理 `.md` 文件。

### arXiv 论文（进阶）

对于 arXiv 论文，使用 `tools/pdf2md.py` 可以获得更高质量的转换结果：

```bash
python tools/pdf2md.py 2401.12345                      # 用 arXiv ID
python tools/pdf2md.py https://arxiv.org/abs/2401.12345 # 用 URL
python tools/pdf2md.py paper.pdf --backend marker       # 复杂的多栏 PDF
```

然后收录生成的 `.md` 文件：

```
ingest raw/papers/my-paper.md
```

### 批量目录转换（进阶）

要预先转换整个目录（适合批量导入）：

```bash
python tools/file_to_md.py --input_dir raw/imports/
python tools/file_to_md.py --input_dir raw/imports/ --delete_source  # 同时删除原始文件
```

### 可选依赖

| 包名 | 安装命令 | 用途 |
|---|---|---|
| [markitdown](https://github.com/microsoft/markitdown) | `pip install markitdown` | 非 .md 文件的自动转换（多格式收录必需） |
| [arxiv2md](https://github.com/ryansingman/arxiv2md) | `pip install arxiv2markdown` | arXiv 论文的结构化源码转换 |
| [Marker](https://github.com/VikParuchuri/marker) | `pip install marker-pdf` | 复杂多栏学术 PDF 的转换 |
| [PyMuPDF4LLM](https://github.com/pymupdf/RAG) | `pip install pymupdf4llm` | 快速的 PDF 提取（不需要 GPU） |
| [tqdm](https://github.com/tqdm/tqdm) | `pip install tqdm` | 批量目录转换的进度条 |
| [litellm](https://github.com/BerriAI/litellm) | `pip install litellm` | 调用 AI 模型（Python 脚本模式需要） |
| [networkx](https://networkx.org/) | `pip install networkx` | 图谱构建中的社区检测 |

## 小贴士

- 直接把文件（PDF、DOCX 等）丢进 `raw/` 然后 `ingest` —— 转换是自动的
- 对于 arXiv 论文，`tools/pdf2md.py` 比通用的 markitdown 转换质量更高
- 查询答案会先展示给你看 —— 然后 AI 会问你是否想把它保存为综合问答页。你的探索成果会像已收录的资料一样不断积累
- wiki 本身是一个 git 仓库 —— 免费获得版本历史
- `tools/` 目录下的独立 Python 脚本不需要代码助手也能运行（但需要设置 `ANTHROPIC_API_KEY` 等环境变量）

## 技术栈

NetworkX + Louvain + Claude + vis.js。没有服务器、没有数据库、完全本地运行。全部都是纯文本 Markdown 文件。

## 相关项目

- [graphify](https://github.com/safishamsi/graphify) — 基于图谱的知识提取技能（图谱层的灵感来源）
- [Vannevar Bush 的 Memex（1945）](https://en.wikipedia.org/wiki/Memex) — 这个项目所效仿的最初愿景

## Star 历史

[![Star History Chart](https://api.star-history.com/svg?repos=SamurAIGPT/llm-wiki-agent&type=Date)](https://star-history.com/#SamurAIGPT/llm-wiki-agent&Date)

## 许可证

MIT 许可证 —— 详见 [LICENSE](LICENSE) 文件。
