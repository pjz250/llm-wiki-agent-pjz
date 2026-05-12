#!/usr/bin/env python3
"""
图谱自我修复工具 —— 自动检测并创建缺失的实体页面。

扫描 wiki 中所有页面，找出那些被大量引用（3 次以上）但还没有
独立页面的实体名称，然后利用 AI 根据现有上下文自动生成实体定义页。

使用方法：
    python tools/heal.py

工作原理：
    1. 调用 lint.py 的 find_missing_entities() 找出缺失的实体
    2. 在现有页面中搜索这些实体被提及的上下文
    3. 让 AI 根据上下文生成实体定义页
    4. 保存到 wiki/entities/<实体名>.md
"""

import os
import sys
from pathlib import Path

# 尝试导入 litellm 库（用于调用各种 AI 模型）
try:
    from litellm import completion
except ImportError:
    # 如果没安装 litellm，给出友好的提示
    print("错误：litellm 未安装。请运行：pip install litellm")
    sys.exit(1)

# 把项目根目录加入 Python 搜索路径，以便导入 tools.lint
sys.path.insert(0, str(Path(__file__).parent.parent))

# 从 lint.py 导入工具函数
from tools.lint import find_missing_entities, all_wiki_pages

# ============================================================
# 项目路径常量
# ============================================================
REPO_ROOT = Path(__file__).parent.parent   # 项目根目录
WIKI_DIR = REPO_ROOT / "wiki"              # wiki 目录
ENTITIES_DIR = WIKI_DIR / "entities"       # 实体页目录

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


def call_llm(prompt: str, max_tokens: int = 1500) -> str:
    """
    调用 AI 语言模型。
    
    参数：
        prompt: 发送给 AI 的提示词
        max_tokens: 生成内容的最大 token 数量（默认 1500）
    
    返回：
        AI 生成的内容文本
    
    环境变量说明：
        LLM_MODEL: 指定要使用的模型（默认 claude-3-5-haiku-latest）
        同时需要设置对应模型的 API Key：
        - Anthropic: ANTHROPIC_API_KEY
        - OpenAI: OPENAI_API_KEY
        - Google: GEMINI_API_KEY
    """
    # 从环境变量读取模型名称，如果没有设置就使用默认值
    # 使用 haiku（快速模型）而不是 sonnet（强大模型），
    # 因为实体生成任务相对简单，不需要最强大的模型
    model = os.getenv("LLM_MODEL", "claude-3-5-haiku-latest")
    
    # 调用 AI 模型
    response = completion(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=max_tokens
    )
    return response.choices[0].message.content


def search_sources(entity: str, pages: list[Path]) -> list[Path]:
    """
    在所有页面中搜索某个实体被提及的上下文。
    
    参数：
        entity: 要搜索的实体名称
        pages: 所有 wiki 页面的路径列表
    
    返回：
        包含该实体提及的页面列表（最多 15 个）
    
    注意：
        只搜索 sources/（资料页）和 concepts/（概念页），
        不搜索 entities/ 目录（因为实体页自身并不提供有用的上下文）。
    """
    sources = []
    for p in pages:
        # 只搜索 sources/（资料页）和 concepts/（概念页），
        # 不搜索 entities/ 目录（因为实体页自身并不提供有用的上下文）。
        parent = str(p.parent)
        if "entities" in parent:
            continue
        content = p.read_text(encoding="utf-8")
        # 大小写不敏感地搜索实体名称
        if entity.lower() in content.lower():
            sources.append(p)
    # 最多返回 15 个页面，避免上下文溢出
    return sources[:15]


def heal_missing_entities():
    """
    主修复逻辑：找出缺失的实体 → 收集上下文 → 调用 AI 生成 → 保存页面。
    """
    # 获取所有 wiki 页面
    pages = all_wiki_pages()
    # 找出缺失的实体（被 3 个以上页面引用但没有独立页面）
    missing_entities = find_missing_entities(pages)
    
    # 如果没有缺失的实体，图谱是完整的
    if not missing_entities:
        print("图谱连接完整！没有发现缺失的实体。")
        return

    # 确保 entities/ 目录存在
    ENTITIES_DIR.mkdir(exist_ok=True, parents=True)
    print(f"发现 {len(missing_entities)} 个缺失的实体节点。开始自动修复...")
    
    # 逐个处理缺失的实体
    for entity in missing_entities:
        print(f"正在为「{entity}」生成实体页面...")
        # 搜索该实体被提及的上下文页面
        sources = search_sources(entity, pages)
        
        # 构建上下文文本（取每个页面的前 800 个字符作为上下文）
        context = ""
        for s in sources:
            context += f"\n\n### {s.name}\n{s.read_text(encoding='utf-8')[:800]}"
        
        # 构建给 AI 的提示词（中文）
        prompt = f"""你正在补充一个个人知识维基中缺失的数据。
请为「{entity}」创建一个实体定义页面。

以下是该实体在当前资料中出现的上下文：
{context}

请按照以下格式输出：

---
title: "{entity}"
type: entity
tags: []
sources: {[s.name for s in sources]}
---

# {entity}

写一个完整的段落，定义「{entity}」在这个 wiki 语境中的含义，
它的主要重要性，以及与之相关的行动或关联。
"""
        try:
            # 调用 AI 生成实体页面内容
            result = call_llm(prompt)
            # 保存到 wiki/entities/<实体名>.md
            out_path = ENTITIES_DIR / f"{entity}.md"
            out_path.write_text(result, encoding="utf-8")
            print(f" -> 已保存到 {out_path.relative_to(REPO_ROOT)}")
        except Exception as e:
            print(f" [!] 生成「{entity}」失败：{e}")


# ============================================================
# 程序入口
# ============================================================
if __name__ == "__main__":
    heal_missing_entities()
