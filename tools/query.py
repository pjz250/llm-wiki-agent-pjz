#!/usr/bin/env python3
"""
查询知识维基 —— 向 wiki 提问，AI 综合所有相关资料后给出答案。

使用方法：
    python tools/query.py "所有资料的核心主题是什么？"
    python tools/query.py "概念 A 和概念 B 之间有什么关系？" --save
    python tools/query.py "帮我总结一下关于某个实体的所有信息" --save synthesis/my-analysis.md

参数说明：
    --save              把答案保存回 wiki 中（会提示输入文件名）
    --save <路径>        指定保存路径（例如 synthesis/my-analysis.md）

工作原理：
    1. 读取 wiki/index.md 找出与问题最相关的页面
    2. 如果关键字匹配不到，让 AI 从索引中挑选相关页面
    3. 读取这些页面的完整内容
    4. 让 AI 综合所有信息给出答案（附带 [[维基链接]] 引用）
    5. 可选：把答案存档为 wiki 的永久资产
"""

import sys
import re
import json
import argparse
from pathlib import Path
from datetime import date

import os

# ============================================================
# 项目路径常量
# ============================================================
REPO_ROOT = Path(__file__).parent.parent      # 项目根目录
WIKI_DIR = REPO_ROOT / "wiki"                 # wiki 目录
INDEX_FILE = WIKI_DIR / "index.md"            # 索引文件（全局目录）
LOG_FILE = WIKI_DIR / "log.md"                # 日志文件
SCHEMA_FILE = REPO_ROOT / "CLAUDE.md"         # 架构说明文件（作为 AI 的指令参考）

# ============================================================
# 加载 .env 配置文件（如果存在）
# ============================================================
_env_path = REPO_ROOT / ".env"
if _env_path.exists():
    try:
        from dotenv import load_dotenv
        load_dotenv(_env_path)
    except ImportError:
        pass


def read_file(path: Path) -> str:
    """读取文件内容（UTF-8 编码），文件不存在时返回空字符串。"""
    return path.read_text(encoding="utf-8") if path.exists() else ""


def write_file(path: Path, content: str):
    """
    写入文件内容。如果目录不存在，自动创建。
    
    参数：
        path: 要写入的文件路径
        content: 文件内容
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    print(f"  已保存：{path.relative_to(REPO_ROOT)}")


def call_llm(prompt: str, model_env: str, default_model: str, max_tokens: int = 4096) -> str:
    """
    调用 AI 语言模型。
    
    参数：
        prompt: 发送给 AI 的提示词
        model_env: 指定模型名称的环境变量名
        default_model: 如果环境变量没设置，使用的默认模型
        max_tokens: 生成内容的最大 token 数量
    
    返回：
        AI 生成的文本内容
    """
    try:
        from litellm import completion
    except ImportError:
        print("错误：litellm 未安装。请运行：pip install litellm")
        sys.exit(1)
    
    # 从环境变量读取模型名称，如果没有设置就使用默认值
    model = os.getenv(model_env, default_model)
    # 调用 AI 模型
    response = completion(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=max_tokens
    )
    return response.choices[0].message.content


def find_relevant_pages(question: str, index_content: str) -> list[Path]:
    """
    从 index.md 中找出与问题最相关的页面。
    
    参数：
        question: 用户的问题
        index_content: index.md 的完整内容
    
    返回：
        相关页面的路径列表（最多 15 个）
    
    匹配策略：
        - 对中文（CJK）：用标题中的连续 2 个字符在问题中匹配
        - 对英文：用标题中的单词（长度 >2）在问题中匹配
        - 如果找到了相关页面，还会通过知识图谱做"邻居扩展"：
          即找到与相关页面有高置信度连接的邻居页面
    """
    # 从 index 中提取所有 Markdown 链接：[标题](路径)
    md_links = re.findall(r'\[([^\]]+)\]\(([^)]+)\)', index_content)
    question_lower = question.lower()
    relevant = []

    # 遍历所有链接，判断哪些与问题相关
    for title, href in md_links:
        title_lower = title.lower()
        # 检查标题中是否包含中文字符
        has_cjk = any('\u4e00' <= ch <= '\u9fff' for ch in title)
        
        if has_cjk:
            # ---- 中文匹配策略 ----
            # 用"滑动窗口"法：检查标题中每 2 个连续中文字符是否出现在问题中
            matched = any(
                title_lower[j:j+2] in question_lower
                for j in range(len(title_lower) - 1)
                if any('\u4e00' <= c <= '\u9fff' for c in title_lower[j:j+2])
            )
        else:
            # ---- 英文匹配策略 ----
            # 用单词匹配：检查标题中长度 >2 的单词是否出现在问题中
            matched = any(
                word in question_lower for word in title_lower.split()
                if len(word) > 2
            )

        # 如果匹配上了，加入相关页面列表
        if matched:
            p = WIKI_DIR / href
            if p.exists() and p not in relevant:
                relevant.append(p)

    # ---- 知识图谱邻居扩展 ----
    # 如果已经找到了一些匹配页面，并且有知识图谱数据，
    # 就找出这些页面的"邻居"（与之有高置信度连接的页面）
    graph_json = REPO_ROOT / "graph" / "graph.json"
    if graph_json.exists() and relevant:
        try:
            graph_data = json.loads(graph_json.read_text())
            # 把匹配页面的相对路径转成图谱中的节点 ID
            page_ids = {
                p.relative_to(WIKI_DIR).as_posix().replace('.md', '')
                for p in relevant
            }
            # 找出匹配页面的高置信度邻居
            neighbors = set()
            for edge in graph_data.get('edges', []):
                if edge.get('confidence', 0) >= 0.7:
                    if edge['from'] in page_ids:
                        neighbors.add(edge['to'])
                    elif edge['to'] in page_ids:
                        neighbors.add(edge['from'])
            # 把邻居也加入相关页面列表
            for nid in neighbors:
                np = WIKI_DIR / f"{nid}.md"
                if np.exists() and np not in relevant:
                    relevant.append(np)
        except (json.JSONDecodeError, KeyError):
            # 图谱数据解析失败，跳过邻居扩展
            pass

    # 始终包含 overview.md（综合概述页）
    overview = WIKI_DIR / "overview.md"
    if overview.exists() and overview not in relevant:
        relevant.insert(0, overview)
    
    # 最多返回 15 个页面，避免 AI 上下文溢出
    return relevant[:15]


def append_log(entry: str):
    """
    在 log.md 的顶部追加一条日志。
    新日志在最上面（追加到开头，不是末尾）。
    """
    existing = read_file(LOG_FILE)
    LOG_FILE.write_text(entry.strip() + "\n\n" + existing, encoding="utf-8")


def query(question: str, save_path: str | None = None):
    """
    核心查询函数：读取 wiki → 找相关页面 → 综合答案 → 可选存档。
    
    参数：
        question: 用户的问题
        save_path: 如果指定了路径，答案会保存为 wiki 页面
    """
    today = date.today().isoformat()

    # ---- 第 1 步：读取索引 ----
    index_content = read_file(INDEX_FILE)
    if not index_content:
        print("wiki 还是空的。请先用 python tools/ingest.py <源文件> 收录一些资料。")
        sys.exit(1)

    # ---- 第 2 步：找出相关页面 ----
    relevant_pages = find_relevant_pages(question, index_content)

    # 如果关键字匹配没有找到相关页面（或者只找到了 overview），
    # 让 AI 来从索引中挑选最相关的页面
    if not relevant_pages or len(relevant_pages) <= 1:
        print("  正在让 AI 选择相关页面...")
        prompt = f"""以下是 wiki 的索引：

{index_content}

针对这个问题："{question}"

哪些页面最相关？请只返回一个 JSON 数组，里面是索引中列出的相对路径，
例如 ["sources/foo.md", "concepts/Bar.md"]。最多 10 个页面。
"""
        raw = call_llm(prompt, "LLM_MODEL_FAST", "claude-3-5-haiku-latest", max_tokens=512)
        # 去掉可能的 Markdown 代码块标记
        raw = raw.strip()
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
        try:
            paths = json.loads(raw)
            relevant_pages = [WIKI_DIR / p for p in paths if (WIKI_DIR / p).exists()]
        except (json.JSONDecodeError, TypeError):
            # AI 返回的格式不对，就用原本的匹配结果
            pass

    # ---- 第 3 步：读取相关页面的内容 ----
    pages_context = ""
    for p in relevant_pages:
        rel = p.relative_to(REPO_ROOT)
        pages_context += f"\n\n### {rel}\n{p.read_text(encoding='utf-8')}"

    # 如果还是没有找到相关页面，至少给 AI 提供索引
    if not pages_context:
        pages_context = f"\n\n### wiki/index.md\n{index_content}"

    # 读取架构说明文件，作为 AI 行为的参考
    schema = read_file(SCHEMA_FILE)

    # ---- 第 4 步：让 AI 综合答案 ----
    print(f"  正在综合 {len(relevant_pages)} 个页面的内容生成答案...")
    prompt = f"""你正在查询一个知识维基来回答问题。请使用下面的 wiki 页面内容，
综合出一个完整的答案。引用来源时使用 [[页面名称]] 维基链接格式。

架构说明：
{schema}

相关的 wiki 页面内容：
{pages_context}

问题：{question}

请写一份结构清晰、内容充实的 Markdown 格式答案，
包含标题、项目符号和 [[维基链接]] 引用。
在末尾添加一个 ## 参考来源 小节，列出你参考了哪些页面。
"""
    answer = call_llm(prompt, "LLM_MODEL", "claude-3-5-sonnet-latest", max_tokens=4096)
    
    # 打印答案到控制台
    print("\n" + "=" * 60)
    print(answer)
    print("=" * 60)

    # ---- 第 5 步：可选地保存答案到 wiki ----
    if save_path is not None:
        # 如果 --save 后面没跟路径，提示用户输入文件名
        if save_path == "":
            slug = input("\n保存为（输入文件名 slug，例如 'my-analysis'）：").strip()
            if not slug:
                print("跳过保存。")
                return
            save_path = f"syntheses/{slug}.md"

        full_save_path = WIKI_DIR / save_path
        # 添加 YAML frontmatter 元数据
        frontmatter = f"""---
title: "{question[:80]}"
type: synthesis
tags: []
sources: []
last_updated: {today}
---

"""
        write_file(full_save_path, frontmatter + answer)

        # 更新 index.md，在 Syntheses（综合问答）分类下添加条目
        index_content = read_file(INDEX_FILE)
        entry = f"- [{question[:60]}]({save_path}) — 综合问答"
        if "## Syntheses" in index_content:
            index_content = index_content.replace("## Syntheses\n", f"## Syntheses\n{entry}\n")
            INDEX_FILE.write_text(index_content, encoding="utf-8")
        print(f"  已注册到索引：{save_path}")

    # 追加日志
    append_log(f"## [{today}] query | {question[:80]}\n\n综合了 {len(relevant_pages)} 个页面的内容。" +
               (f" 保存到 {save_path}。" if save_path else ""))


# ============================================================
# 程序入口
# ============================================================
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="查询知识维基 —— 向 wiki 提问，AI 综合回答")
    parser.add_argument("question", help="要问 wiki 的问题")
    parser.add_argument(
        "--save", nargs="?", const="", default=None,
        help="把答案保存到 wiki 中（可选参数：指定保存路径）"
    )
    args = parser.parse_args()
    query(args.question, args.save)
