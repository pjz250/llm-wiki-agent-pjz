#!/usr/bin/env python3
"""
全流程管道脚本 —— 对一本书依次执行 Wiki 收录 → 书籍萃取。

工作流程：
    步骤 ①：ingest  将整本书收录到 wiki
    步骤 ②：extract  对同一本书做知识萃取（生成分析报告 + 卡片，保留在 wiki/cards/ 下）

使用方法：
    # 处理单本书
    python tools/pipeline.py raw/人类思想型/纯粹理性批判.md

    # 批量处理一个分类下所有书籍
    python tools/pipeline.py raw/方法实践型/

    # 批量处理全部分类
    python tools/pipeline.py raw/

    # 只做萃取，跳过收录（如果已经收录过）
    python tools/pipeline.py raw/方法实践型/搞定GTD.md --skip-ingest-book

依赖：
    自动调用 tools/ingest.py 和 tools/extract.py，这两个脚本必须在同级目录。
"""

import os
import sys
import re
import subprocess
import argparse
from pathlib import Path

# ============================================================
# 项目路径常量
# ============================================================
REPO_ROOT = Path(__file__).parent.parent
TOOLS_DIR = REPO_ROOT / "tools"
RAW_DIR = REPO_ROOT / "raw"
CATEGORIES = ["方法实践型", "人类思想型", "行为改变型", "硬核技能型"]


def get_category(filepath: Path) -> str:
    """根据文件所在目录判断分类。"""
    for cat in CATEGORIES:
        if cat in filepath.parts:
            return cat
    return "未分类"


def build_book_slug(filepath: Path) -> str:
    """构建书籍 slug（与 extract.py 完全一致的算法）。"""
    category = get_category(filepath)
    stem = filepath.stem
    safe = re.sub(r'[^\w\u4e00-\u9fff-]', "-", stem)
    safe = re.sub(r"-+", "-", safe).strip("-")
    return f"{category}-{safe}"


def run_ingest(file_path: Path) -> bool:
    """调用 ingest.py 收录一个文件到 wiki。"""
    python = sys.executable
    ingest_script = TOOLS_DIR / "ingest.py"
    result = subprocess.run(
        [python, str(ingest_script), str(file_path)],
        capture_output=False,
        cwd=REPO_ROOT,
    )
    return result.returncode == 0


def run_extract(file_path: Path) -> bool:
    """调用 extract.py 对一本书做萃取（加 --force 确保执行）。"""
    python = sys.executable
    extract_script = TOOLS_DIR / "extract.py"
    result = subprocess.run(
        [python, str(extract_script), str(file_path), "--force"],
        capture_output=False,
        cwd=REPO_ROOT,
    )
    return result.returncode == 0


def print_header(text: str):
    """打印带分隔线的标题。"""
    print(f"\n{'='*60}")
    print(f"  {text}")
    print(f"{'='*60}")


def pipeline(file_path: Path, skip_ingest_book: bool = False) -> bool:
    """对一本书执行全流程管道处理。"""
    if not file_path.exists():
        print(f"  ✗ 文件不存在：{file_path}")
        return False

    book_title = file_path.stem
    book_slug = build_book_slug(file_path)

    print(f"\n{'#'*60}")
    print(f"  # 全流程管道：{book_title}")
    print(f"  # 分类：{get_category(file_path)}")
    print(f"{'#'*60}")

    # ── 步骤 ①：Wiki 收录整本书 ──
    if skip_ingest_book:
        print_header("步骤 ① [跳过] Wiki 收录整本书（--skip-ingest-book）")
    else:
        print_header("步骤 ① Wiki 收录整本书")
        if not run_ingest(file_path):
            print(f"  ✗ 步骤 ① 失败：书籍收录出错，终止管道")
            return False
        print(f"  ✓ 步骤 ① 完成")

    # ── 步骤 ②：书籍萃取 ──
    print_header("步骤 ② 书籍萃取（分析报告 + 卡片）")
    if not run_extract(file_path):
        print(f"  ✗ 步骤 ② 失败：书籍萃取出错，终止管道")
        return False
    print(f"  ✓ 步骤 ② 完成")

    # ── 完成 ──
    print(f"\n{'#'*60}")
    print(f"  # 全流程管道完成：{book_title}")
    print(f"  # 步骤 ① 书籍收录：{'✓' if not skip_ingest_book else '已跳过'}")
    print(f"  # 步骤 ② 书籍萃取：✓")
    print(f"{'#'*60}")
    print(f"\n  萃取结果保存在：wiki/cards/{book_slug}/")
    print(f"{'#'*60}")
    return True


def collect_md_files(path: Path) -> list[Path]:
    """收集要处理的 .md 文件列表（与 extract.py 一致的算法）。"""
    if path.is_file():
        return [path]

    files = []
    if path.name in CATEGORIES:
        files.extend(sorted(path.glob("*.md")))
    elif path == RAW_DIR:
        for cat in CATEGORIES:
            cat_dir = path / cat
            if cat_dir.exists():
                files.extend(sorted(cat_dir.glob("*.md")))
    else:
        files.extend(sorted(path.glob("*.md")))
    return sorted(set(files))


def main():
    parser = argparse.ArgumentParser(
        description="全流程管道 —— Wiki 收录 → 书籍萃取",
    )
    parser.add_argument(
        "path",
        nargs="?",
        default=None,
        help=(
            "要处理的路径。支持：\n"
            "  - 单本书：raw/方法实践型/搞定GTD.md\n"
            "  - 单分类：raw/方法实践型/\n"
            "  - 全部分类：raw/\n"
            "  - 不指定：自动扫描 raw/ 下所有分类"
        ),
    )
    parser.add_argument(
        "--skip-ingest-book",
        action="store_true",
        help="跳过第 1 步（不收录整本书到 wiki，只做萃取）",
    )
    args = parser.parse_args()

    target_path = args.path

    if target_path is None:
        files = []
        for cat in CATEGORIES:
            cat_dir = RAW_DIR / cat
            if cat_dir.exists():
                files.extend(sorted(cat_dir.glob("*.md")))
    else:
        target = Path(target_path)
        if not target.is_absolute():
            target = REPO_ROOT / target

        if not target.exists():
            print(f"错误：路径不存在：{target}")
            sys.exit(1)

        files = collect_md_files(target)

    if not files:
        print("没有找到要处理的书籍文件（.md）。")
        print(f"请确保在 raw/ 的分类目录下放置了 Markdown 格式的书籍文件。")
        print(f"当前分类目录：{', '.join(CATEGORIES)}")
        sys.exit(0)

    print(f"找到 {len(files)} 本书籍待处理")
    print(f"{'='*60}")

    success = 0
    failed = 0

    for fp in files:
        print(f"\n{'='*60}")
        print(f"  处理：{fp.relative_to(REPO_ROOT)}")
        print(f"{'='*60}")
        if pipeline(fp, skip_ingest_book=args.skip_ingest_book):
            success += 1
        else:
            failed += 1

    print(f"\n{'='*60}")
    print(f"全流程管道完成！")
    print(f"  成功：{success} 本")
    print(f"  失败：{failed} 本")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
