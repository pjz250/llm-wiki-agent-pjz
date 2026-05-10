# 命令说明书 —— 本项目所有功能与命令速查

## 前置准备

### 1. 安装依赖
```bash
cd <项目目录>      # 替换成你的项目路径
pip install -r requirements.txt
```

### 2. 配置 AI 模型

> **本项目默认使用 DeepSeek 模型**。`.env` 文件已包含配置，你通常只需要确认 API Key 有效即可。

```bash
# 查看当前配置
Get-Content .env

# 如果 API Key 需要更新，编辑 .env 文件，找到这一行修改：
# DEEPSEEK_API_KEY=sk-你的新密钥
```

**如果要切换模型**，编辑 `.env` 文件中的 `LLM_MODEL` 和对应的 API Key 即可。

> **关于 `provider/` 前缀**：本项目使用 litellm 库调用 AI 模型，模型名必须带 provider 前缀。
> - DeepSeek → `deepseek/deepseek-chat` 或 `deepseek/deepseek-reasoner`
> - OpenAI → `openai/gpt-4o`
> - Anthropic → `anthropic/claude-3-5-sonnet-latest`
> - 更多 provider 参见 [litellm 文档](https://docs.litellm.ai/docs/providers)

---

## 一、Wiki 萃取体系 —— 资料收录与知识管理

适用于：论文、文章、报告、网页、日记、会议记录等任意文档。每份资料自动变成 wiki 页面，交叉引用，持续积累。

### 1.1 收录资料（ingest）

将一份原始资料收录到 wiki 中，自动创建摘要页、更新索引、创建实体/概念页。

```bash
# 单篇收录
python tools/ingest.py raw/papers/attention-is-all-you-need.md

# 自动转换非 Markdown 格式（PDF/DOCX/PPTX 等）
python tools/ingest.py raw/papers/report.pdf
python tools/ingest.py raw/meetings/notes.docx

# 批量收录（支持混合格式）
python tools/ingest.py raw/papers/paper1.md raw/papers/paper2.pdf

# 跳过自动转换（保持原格式）
python tools/ingest.py raw/html_files/ --no-convert

# 只验证不收录
python tools/ingest.py raw/papers/my-paper.md --validate-only

# 在 AI 助手中用自然语言触发
ingest raw/papers/my-paper.md
```

### 1.2 知识查询（query）

从 wiki 中综合已有知识回答问题。

```bash
# 在 AI 助手中触发（AI 助手会自动读取相关 wiki 页面）
query: Transformer 模型的核心创新是什么？

# 或用自然语言
"这个 wiki 里关于注意力机制都说了些什么？"
```

### 1.3 健康检查（health）

检查 wiki 的结构完整性 —— 纯逻辑判断，不调用 AI，速度快。

```bash
# 标准检查（结果输出到控制台）
python tools/health.py

# 保存报告到文件
python tools/health.py --save

# 输出 JSON 格式（适合程序处理）
python tools/health.py --json

# 在 AI 助手中触发
health
```

### 1.4 代码检查（lint）

检查 wiki 的内容质量 —— 需要调用 AI 做语义分析，比较耗资源。

```bash
# 标准检查
python tools/lint.py

# 保存报告到文件
python tools/lint.py --save

# 在 AI 助手中触发
lint
```

### 1.5 构建知识图谱（build graph）

分析所有 wiki 页面之间的 `[[维基链接]]` 关系，生成可视化图谱。

```bash
# 生成图谱数据 + 打开可视化页面
python tools/build_graph.py --open

# 只生成数据，不打开页面
python tools/build_graph.py

# 生成图谱健康报告
python tools/build_graph.py --report

# 保存报告到文件
python tools/build_graph.py --report --save

# 在 AI 助手中触发
build graph
```

### 1.6 守护进程（daemon）

自动监控 `raw/` 目录，发现新文件自动收录。

```bash
# 前台运行（每 30 秒扫描一次）
python tools/daemon.py

# 每 60 秒扫描一次
python tools/daemon.py --interval 60

# 只跑一轮就退出（适合配合系统定时任务）
python tools/daemon.py --once

# 收录后不重建图谱（速度更快）
python tools/daemon.py --no-graph

# 指定日志文件路径
python tools/daemon.py --log-file logs/my-daemon.log

# 后台运行（Windows）
start /B python tools/daemon.py

# 在 AI 助手中触发
daemon
```

---

## 二、书籍智慧萃取体系 —— 四卡知识萃取

适用于：整本通读书籍，自动生成概念卡 / 模型卡 / 流程卡 / 清单卡。

### 前置：分类放置书籍

在 `raw/` 下的四个分类目录中放入 Markdown 格式的书籍文件：

```
raw/
  方法实践型/          ← 自我成长、学习方法、工作技巧类
    搞定GTD.md
    高效能人士的七个习惯.md
  人类思想型/          ← 思想、历史、哲学、经济学等
    国富论.md
    纯粹理性批判.md
  行为改变型/          ← 心理学、行为改变、影响他人
    思考快与慢.md
    影响力.md
  硬核技能型/          ← AI、编程、数学、物理等
    Python编程从入门到实践.md
```

### 2.1 萃取一本书

```bash
python tools/extract.py raw/方法实践型/搞定GTD.md
```

### 2.2 批量萃取一个分类

```bash
python tools/extract.py raw/方法实践型/
```

### 2.3 批量萃取全部分类

```bash
python tools/extract.py raw/
```

### 2.4 强制重新萃取（覆盖已生成的卡片）

同名书籍默认跳过，加 `--force` 强制重新生成：

```bash
python tools/extract.py raw/方法实践型/搞定GTD.md --force
python tools/extract.py raw/ --force
```

### 2.5 萃取流程（3 轮）

| 轮次 | 做什么 | 使用提示词 | 输出 |
|---|---|---|---|
| **第 1 轮** | 按分类提示词做完整书籍分析 | 分类提示词（如 `人类思想型全书.txt`） | `书籍分析报告.md` |
| **第 2 轮** | 根据分析结果判断需要生成哪些卡 | 内置判断规则 | `元信息.json` 中的决策记录 |
| **第 3 轮** | 按各卡片提示词逐类穷尽生成 | 各卡片提示词（如 `概念卡提示词.txt`） | 各 `概念卡.md` / `模型卡.md` / ... |

每轮职责单一，互不干扰 —— 分类提示词的完整结果不会被丢失，卡片提示词的"穷尽"要求也不会被其他指令稀释。

### 2.6 输出位置

萃取结果自动生成到 `wiki/cards/` 目录：

```
wiki/cards/
  人类思想型-纯粹理性批判/
    书籍分析报告.md    ← 第 1 轮：按分类提示词生成的完整分析（Markdown）
    概念卡.md          ← 第 3 轮：按概念卡提示词穷尽生成
    模型卡.md          ← 第 3 轮：按模型卡提示词穷尽生成
    元信息.json        ← 记录分类、生成时间、跳过了哪些卡及理由
  方法实践型-搞定GTD/
    书籍分析报告.md
    概念卡.md
    流程卡.md
    清单卡.md
    元信息.json
```

### 2.6 自定义提示词

萃取使用的提示词放在 `prompt/` 目录，你可以自由修改：

```
prompt/
  方法实践型全书.txt    ← 该类书籍的萃取指导
  人类思想型全书.txt
  行为改变型全书.txt
  硬核技能型全书.txt
  概念卡提示词.txt      ← 各卡片的输出格式
  模型卡提示词.txt
  流程卡提示词.txt
  清单卡提示词.txt
```

---

## 三、全流程管道 —— 一键完成 Wiki 收录 + 萃取 + 卡片收录

自动执行 3 个步骤：Wiki 收录整本书 → 书籍萃取 → 将萃取结果（分析报告 + 卡片）也收录到 Wiki。

### 3.1 处理单本书

```bash
python tools/pipeline.py raw/人类思想型/纯粹理性批判.md
```

### 3.2 批量处理一个分类

```bash
python tools/pipeline.py raw/方法实践型/
```

### 3.3 批量处理全部分类

```bash
python tools/pipeline.py raw/
```

### 3.4 跳过书籍收录（如果已经收录过）

```bash
python tools/pipeline.py raw/方法实践型/搞定GTD.md --skip-ingest-book
```

### 3.5 管道内部执行流程

| 步骤 | 调用脚本 | 做什么 |
|---|---|---|
| **① Wiki 收录整本书** | `ingest.py` | 把整本书作为资料收录到 wiki，生成摘要页、实体页、概念页 |
| **② 书籍萃取** | `extract.py` | 对同一本书做知识萃取，生成 `书籍分析报告.md` + 四卡 |
| **③ 卡片收录** | `ingest.py`（多次） | 将生成的每个 `.md` 文件（分析报告 + 卡片）逐一收录到 wiki |

---

## 四、两种萃取方式对比

| 维度 | Wiki 萃取（ingest） | 书籍萃取（extract） |
|---|---|---|
| **适用场景** | 论文、文章、日记、会议记录等片段式资料 | 整本通读的书籍 |
| **输出** | wiki 页面（摘要/实体/概念/综合概述） | 四卡（概念卡/模型卡/流程卡/清单卡） |
| **跨文档关联** | 自动构建 `[[维基链接]]`、知识图谱 | 单本书独立萃取，不交叉引用 |
| **知识积累** | 所有资料汇总到 overview.md，持续演进 | 每本书独立输出，不互相合并 |
| **侧重点** | 文档与文档之间的关系网络 | 一本书的深度提炼 |
| **触发方式** | `python tools/ingest.py <文件>` | `python tools/extract.py <文件>` |

**推荐搭配使用：**

```
# 1. 读书时先做书籍萃取，沉淀卡片
python tools/extract.py raw/方法实践型/搞定GTD.md

# 2. 把萃取结果作为资料收录到 wiki，让它跟其他知识关联起来
python tools/ingest.py wiki/cards/方法实践型-搞定GTD/概念卡.md
python tools/ingest.py wiki/cards/方法实践型-搞定GTD/流程卡.md
```

---

## 四、快速启动 —— 开箱即用模板

### 🆕 推荐方式：一键全流程管道

```bash
# ===== 第 1 步：安装依赖 =====
pip install -r requirements.txt

# ===== 第 2 步：确认模型配置（项目默认使用 DeepSeek） =====
# 编辑 .env 文件，确认 DEEPSEEK_API_KEY 有效即可

# ===== 第 3 步：把书籍放进分类目录 =====
# 把搞定GTD.md 复制到 raw/方法实践型/
# 把思考快与慢.md 复制到 raw/行为改变型/

# ===== 第 4 步：一键全流程管道 =====
# 自动完成：Wiki收录 → 萃取 → 卡片收录
python tools/pipeline.py raw/方法实践型/搞定GTD.md

# 批量处理全部分类
python tools/pipeline.py raw/
```

### 手动分步执行（如果你想控制每一步）

以下是一套完整流程，你只需要把路径名改成自己的：

```bash
# ===== 第 1 步：安装依赖 =====
pip install -r requirements.txt

# ===== 第 2 步：确认模型配置（项目默认使用 DeepSeek） =====
# 编辑 .env 文件，确认 DEEPSEEK_API_KEY 有效即可
# 如果需要切换模型，修改 LLM_MODEL 和对应的 API Key

# ===== 第 3 步：把书籍放进分类目录 =====
# 把搞定GTD.md 复制到 raw/方法实践型/
# 把思考快与慢.md 复制到 raw/行为改变型/

# ===== 第 4 步：批量萃取所有书籍 =====
# 如果之前已经萃取过，加 --force 重新生成
python tools/extract.py raw/

# 单本重新萃取
python tools/extract.py raw/人类思想型/纯粹理性批判.md --force

# ===== 第 5 步：把萃取结果收录到 wiki =====
python tools/ingest.py wiki/cards/方法实践型-搞定GTD/概念卡.md
python tools/ingest.py wiki/cards/方法实践型-搞定GTD/流程卡.md
python tools/ingest.py wiki/cards/方法实践型-搞定GTD/清单卡.md

# ===== 第 6 步：查询 wiki 中的知识 =====
# 在 AI 助手中说：query: GTD 的核心工作流是什么？

# ===== 第 7 步：构建知识图谱 =====
python tools/build_graph.py --open
```

---

## 五、目录结构速览

```
raw/              ← 放原始文件（.md / .pdf / .docx ...）
  方法实践型/      ← 书籍萃取的分类目录
  人类思想型/
  行为改变型/
  硬核技能型/
prompt/           ← 书籍萃取的提示词（你可自由修改）
wiki/             ← Wiki 知识库（自动生成）
  cards/          ← 书籍萃取的输出目录
log/              ← 守护进程日志（自动生成）
graph/            ← 知识图谱数据（自动生成）
tools/            ← 脚本工具
  ingest.py       ← Wiki 收录
  extract.py      ← 书籍萃取
  pipeline.py     ← 全流程管道（推荐）
  health.py       ← 健康检查
  lint.py         ← 代码检查
  build_graph.py  ← 图谱构建
  daemon.py       ← 守护进程
  file_to_md.py   ← 文件格式转换
  pdf2md.py       ← PDF 转 Markdown
  query.py        ← 查询
  heal.py         ← 链接修复
  refresh.py      ← 刷新
```




# 重新生成：把之前收录过的资料再跑一遍
python tools/ingest.py raw/探索智慧：从达尔文到芒格.md
python tools/ingest.py raw/人类思想型/纯粹理性批判.md

# 或者用全流程管道，重新萃取 + 收录
python tools/pipeline.py raw/


已经使用过的命令
# 单本书
python tools/pipeline.py raw/人类思想型/纯粹理性批判.md

# 整分类
python tools/pipeline.py raw/方法实践型/

# 全部
python tools/pipeline.py raw/

# 跳过收录，只做萃取
python tools/pipeline.py raw/方法实践型/搞定GTD.md --skip-ingest-book