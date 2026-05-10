#!/usr/bin/env python3
"""
刷新过时的资料页 —— 当原始文档被修改后，重新收录以更新 wiki 内容。

使用方法：
    python tools/refresh.py                     # 只刷新内容有变化的资料
    python tools/refresh.py --force             # 强制重新收录所有资料
    python tools/refresh.py --page sources/X    # 刷新指定的某个资料页

工作原理：
    通过比较原始文档（raw/ 下）的 SHA256 哈希值来判断文档是否已修改。
    如果哈希值变了，说明文档被更新了，需要重新收录以更新 wiki 页面。
"""

import os
import sys
import json
import hashlib
import re
from typing import Optional    # 可选类型标注（用于可能为 None 的返回值）
from pathlib import Path
from datetime import date

# ============================================================
# 项目路径常量
# ============================================================
REPO_ROOT = Path(__file__).parent.parent      # 项目根目录
WIKI_DIR = REPO_ROOT / "wiki"                 # wiki 目录
RAW_DIR = REPO_ROOT / "raw"                   # 原始文档目录
SOURCES_DIR = WIKI_DIR / "sources"            # 资料摘要页目录
REFRESH_CACHE = REPO_ROOT / "graph" / ".refresh_cache.json"  # 哈希值缓存文件


def sha256(text: str) -> str:
    """
    计算文本的 SHA256 哈希值（取前 16 位）。
    
    用途：作为文件内容的"指纹"，用来判断文件是否被修改过。
    前 16 位已经足够区分不同的文件内容了。
    """
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def read_file(path: Path) -> str:
    """
    读取文件的全部内容（UTF-8 编码）。
    如果文件不存在，返回空字符串而不是报错。
    """
    return path.read_text(encoding="utf-8") if path.exists() else ""


def load_refresh_cache() -> dict:
    """
    加载刷新缓存。
    
    缓存格式：{"原始文档路径": "文件内容的 SHA256 哈希值"}
    
    如果缓存文件不存在或格式损坏，返回空字典。
    """
    if REFRESH_CACHE.exists():
        try:
            return json.loads(REFRESH_CACHE.read_text())
        except (json.JSONDecodeError, IOError):
            # JSON 解析失败或文件读取出错，返回空缓存重新开始
            return {}
    return {}


def save_refresh_cache(cache: dict):
    """
    保存刷新缓存到磁盘。
    
    参数：
        cache: 要保存的缓存字典
    """
    REFRESH_CACHE.parent.mkdir(parents=True, exist_ok=True)
    REFRESH_CACHE.write_text(json.dumps(cache, indent=2, ensure_ascii=False))


def extract_source_file(content: str) -> Optional[str]:
    """
    从 wiki 页面的 YAML frontmatter 中提取 source_file 字段。
    
    source_file 字段记录了这份资料摘要对应的原始文档路径。
    格式：source_file: raw/papers/my-paper.md
    
    参数：
        content: wiki 页面的完整内容
    
    返回：
        原始文档的路径字符串，如果没有找到返回 None
    """
    # 用正则匹配 ^source_file: 开头的行
    match = re.search(r'^source_file:\s*(.+)$', content, re.MULTILINE)
    if match:
        # 去掉可能存在的引号
        return match.group(1).strip().strip('"').strip("'")
    return None


def find_stale_sources(force: bool = False) -> list[tuple[Path, Path]]:
    """
    找出需要刷新的资料：（wiki 摘要页, 原始文档路径）的列表。
    
    参数：
        force: 如果为 True，忽略哈希值比较，强制刷新所有资料
    
    返回：
        (wiki_page, raw_path) 元组的列表，表示需要刷新的配对
    
    判断逻辑：
        1. 遍历所有 wiki/sources/*.md 资料摘要页
        2. 从 frontmatter 中读取 source_file 找到对应的原始文档
        3. 计算原始文档的当前哈希值
        4. 与缓存中的哈希值比较，不同则说明文档已修改
    """
    cache = load_refresh_cache()
    stale = []

    # 如果 sources/ 目录还不存在，说明还没有过任何收录
    if not SOURCES_DIR.exists():
        return stale

    # 遍历所有资料摘要页
    for wiki_page in sorted(SOURCES_DIR.glob("*.md")):
        content = read_file(wiki_page)
        # 从 frontmatter 提取原始文档路径
        source_file = extract_source_file(content)
        if not source_file:
            # 如果页面没有 source_file 字段，跳过（可能是手动创建的）
            continue

        # 尝试在项目根目录下找原始文档
        raw_path = REPO_ROOT / source_file
        if not raw_path.exists():
            # 如果根目录下找不到，尝试在 raw/ 目录下找
            raw_path = RAW_DIR / source_file
            if not raw_path.exists():
                # 原始文档也不存在，跳过
                continue

        # 计算原始文档的当前哈希值
        raw_content = read_file(raw_path)
        current_hash = sha256(raw_content)
        # 读取缓存中记录的哈希值
        cached_hash = cache.get(str(raw_path))

        # 如果强制刷新，或者哈希值变了，说明需要刷新
        if force or cached_hash != current_hash:
            stale.append((wiki_page, raw_path))

    return stale


def refresh_page(wiki_page: Path, raw_path: Path) -> bool:
    """
    重新收录一份原始文档以刷新对应的 wiki 资料页。
    
    参数：
        wiki_page: wiki 中的资料摘要页路径
        raw_path: 原始文档的路径
    
    返回：
        True 表示刷新成功，False 表示刷新失败
    """
    # 导入 ingest 模块中的 ingest 函数
    sys.path.insert(0, str(Path(__file__).parent))
    try:
        from ingest import ingest
        print(f"\n{'='*60}")
        print(f"  正在刷新：{wiki_page.name}")
        print(f"  原始文档：{raw_path}")
        print(f"{'='*60}")
        # 调用 ingest 函数重新收录
        ingest(str(raw_path))
        return True
    except Exception as e:
        print(f"  [错误] 刷新 {wiki_page.name} 失败：{e}")
        return False


def main():
    """
    主函数 —— 解析命令行参数，执行刷新操作。
    """
    import argparse
    parser = argparse.ArgumentParser(
        description="刷新过时的 wiki 资料页 —— 当原始文档修改时重新收录"
    )
    parser.add_argument(
        "--force", action="store_true",
        help="强制刷新所有资料（忽略哈希值比较）"
    )
    parser.add_argument(
        "--page", type=str,
        help="刷新指定的某个资料页（例如 sources/my-page）"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="仅列出需要刷新的页面，不实际执行刷新"
    )
    args = parser.parse_args()

    # ---- 如果指定了 --page，只刷新单个页面 ----
    if args.page:
        wiki_page = WIKI_DIR / args.page
        # 如果路径没有 .md 后缀，自动补上
        if not wiki_page.suffix:
            wiki_page = wiki_page.with_suffix(".md")
        
        # 检查页面是否存在
        if not wiki_page.exists():
            print(f"页面不存在：{wiki_page}")
            sys.exit(1)
        
        # 从 frontmatter 读取原始文档路径
        content = read_file(wiki_page)
        source_file = extract_source_file(content)
        if not source_file:
            print(f"{wiki_page.name} 的 frontmatter 中没有找到 source_file 字段")
            sys.exit(1)
        
        # 定位原始文档
        raw_path = REPO_ROOT / source_file
        if not raw_path.exists():
            raw_path = RAW_DIR / source_file
        if not raw_path.exists():
            print(f"原始文档不存在：{source_file}")
            sys.exit(1)
        
        stale = [(wiki_page, raw_path)]
    else:
        # ---- 自动检测需要刷新的页面 ----
        stale = find_stale_sources(force=args.force)

    # 如果没有需要刷新的页面
    if not stale:
        print("所有资料页都是最新的。没有需要刷新的内容。")
        return

    # 打印需要刷新的页面列表
    print(f"发现 {len(stale)} 个过时的资料页：")
    for wiki_page, raw_path in stale:
        print(f"  • {wiki_page.name} ← {raw_path.relative_to(REPO_ROOT)}")

    # 如果是 --dry-run（试运行），只列出不执行
    if args.dry_run:
        print("\n[试运行] 未做任何修改。")
        return

    # ---- 逐个刷新 ----
    cache = load_refresh_cache()
    refreshed = 0
    failed = 0

    for wiki_page, raw_path in stale:
        if refresh_page(wiki_page, raw_path):
            # 刷新成功，更新缓存
            raw_content = read_file(raw_path)
            cache[str(raw_path)] = sha256(raw_content)
            refreshed += 1
        else:
            failed += 1

    # 保存更新后的缓存
    save_refresh_cache(cache)

    # 打印刷新结果摘要
    print(f"\n{'='*60}")
    print(f"  刷新完成：{refreshed} 个更新成功，{failed} 个失败")
    print(f"{'='*60}")


# ============================================================
# 程序入口
# ============================================================
if __name__ == "__main__":
    main()
