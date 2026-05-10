#!/usr/bin/env python3
"""
把 PDF 或 arXiv 论文转换为 Markdown 格式，保存到 raw/ 目录中。

使用方法：
    python tools/pdf2md.py <输入> [--output raw/papers/输出.md] [--backend auto]

输入类型：
    arXiv 编号   →  2401.12345
    arXiv 地址   →  https://arxiv.org/abs/2401.12345
    本地 PDF     →  /path/to/paper.pdf

转换引擎：
    auto          →  arXiv 输入用 arxiv2md；PDF 用 marker（后备方案：pymupdf4llm）
    arxiv2md      →  最适合 arXiv 论文（使用结构化源码，不是 PDF）
    marker        →  最适合复杂的多栏学术 PDF
    pymupdf4llm   →  速度快、轻量、不需要 GPU —— 适合纯文本 PDF

示例：
    python tools/pdf2md.py 2401.12345
    python tools/pdf2md.py https://arxiv.org/abs/2401.12345
    python tools/pdf2md.py paper.pdf --backend marker
    python tools/pdf2md.py paper.pdf -o raw/papers/my-paper.md
"""

import argparse
import importlib     # 用于检查 Python 包是否已安装
import os
import re
import subprocess    # 用于运行外部命令（如 arxiv2md）
import sys
from pathlib import Path

# ============================================================
# 项目路径常量
# ============================================================
REPO_ROOT = Path(__file__).parent.parent      # 项目根目录
DEFAULT_OUTPUT_DIR = REPO_ROOT / "raw" / "papers"  # 默认输出目录

# 用于识别 arXiv 编号或地址的正则表达式模式
ARXIV_PATTERNS = [
    re.compile(r"^(\d{4}\.\d{4,5})(v\d+)?$"),                          # 纯编号：2401.12345
    re.compile(r"arxiv\.org/abs/(\d{4}\.\d{4,5})(v\d+)?"),              # 摘要页地址
    re.compile(r"arxiv\.org/pdf/(\d{4}\.\d{4,5})(v\d+)?"),              # 直接 PDF 地址
]


def extract_arxiv_id(source: str) -> str | None:
    """
    判断输入是否为 arXiv 引用，如果是则返回 arXiv ID。
    
    例如：输入 "2401.12345" 或 "https://arxiv.org/abs/2401.12345"
    都会返回 "2401.12345"。
    如果输入不是 arXiv 引用，返回 None。
    """
    for pattern in ARXIV_PATTERNS:
        m = pattern.search(source)
        if m:
            return m.group(1)
    return None


def check_dependency(package: str, pip_name: str | None = None) -> bool:
    """
    检查某个 Python 包是否已安装。
    
    参数：
        package: 包名（用于 import 检查）
        pip_name: pip 安装用的名称（如果和 import 名不同的话）
    
    返回：
        True 表示已安装，False 表示未安装
    """
    try:
        importlib.import_module(package)
        return True
    except ImportError:
        return False


def install_hint(pip_name: str) -> str:
    """生成安装提示信息。"""
    return f"  请运行：pip install {pip_name}"


# ============================================================
# 转换引擎 1：arxiv2md（用于 arXiv 论文）
# ============================================================

def convert_arxiv(arxiv_id: str, output: Path) -> Path:
    """
    使用 arxiv2md 工具将 arXiv 论文转换为 Markdown。
    
    arxiv2md 从 arXiv 的 LaTeX 源码转换，比从 PDF 转换质量更高。
    """
    pip_name = "arxiv2markdown"
    if not check_dependency("arxiv2md", pip_name):
        print(f"错误：arxiv2md 未安装。\n{install_hint(pip_name)}")
        sys.exit(1)

    # 确保输出目录存在
    output.parent.mkdir(parents=True, exist_ok=True)
    # 调用 arxiv2md 命令行工具
    cmd = ["arxiv2md", arxiv_id, "-o", str(output)]
    print(f"  正在运行：{' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        print(f"错误：arxiv2md 转换失败：\n{result.stderr}")
        sys.exit(1)

    print(f"  ✓ 已转换 arXiv {arxiv_id} → {output.relative_to(REPO_ROOT)}")
    return output


# ============================================================
# 转换引擎 2：marker（高精度 PDF 转换）
# ============================================================

def convert_marker(pdf_path: Path, output: Path) -> Path:
    """
    使用 marker 库将 PDF 转换为 Markdown。
    
    marker 能很好地处理复杂的多栏学术 PDF，但速度较慢。
    """
    pip_name = "marker-pdf"
    if not check_dependency("marker", pip_name):
        print(f"错误：marker 未安装。\n{install_hint(pip_name)}")
        sys.exit(1)

    output.parent.mkdir(parents=True, exist_ok=True)
    # marker 输出到目录，需要从临时目录移动结果到目标路径
    tmp_dir = output.parent / f".marker_tmp_{output.stem}"
    cmd = ["marker_single", str(pdf_path), "--output_dir", str(tmp_dir)]
    print(f"  正在运行：{' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        print(f"错误：marker 转换失败：\n{result.stderr}")
        sys.exit(1)

    # marker 会在输出目录下创建 <pdf_name>/<pdf_name>.md
    md_files = list(tmp_dir.rglob("*.md"))
    if not md_files:
        print("错误：marker 没有生成 Markdown 输出。")
        sys.exit(1)

    # 把第一个 .md 文件移动到目标路径，然后清理临时目录
    md_files[0].rename(output)
    import shutil
    shutil.rmtree(tmp_dir, ignore_errors=True)

    print(f"  ✓ 已转换 {pdf_path.name} → {output.relative_to(REPO_ROOT)}")
    return output


# ============================================================
# 转换引擎 3：pymupdf4llm（快速轻量 PDF 转换）
# ============================================================

def convert_pymupdf(pdf_path: Path, output: Path) -> Path:
    """
    使用 pymupdf4llm 库将 PDF 转换为 Markdown。
    
    速度快、轻量化、不需要 GPU，适合纯文本 PDF。
    但对于复杂排版的 PDF（多栏、图片表格等）效果可能不如 marker。
    """
    pip_name = "pymupdf4llm"
    if not check_dependency("pymupdf4llm", pip_name):
        print(f"错误：pymupdf4llm 未安装。\n{install_hint(pip_name)}")
        sys.exit(1)

    import pymupdf4llm

    output.parent.mkdir(parents=True, exist_ok=True)
    md_text = pymupdf4llm.to_markdown(str(pdf_path))
    output.write_text(md_text, encoding="utf-8")

    print(f"  ✓ 已转换 {pdf_path.name} → {output.relative_to(REPO_ROOT)}")
    return output


# ============================================================
# 自动检测与调度
# ============================================================

# 可用转换引擎的映射表
BACKENDS = {
    "arxiv2md": convert_arxiv,
    "marker": convert_marker,
    "pymupdf4llm": convert_pymupdf,
}


def slugify(name: str) -> str:
    """
    把文件名或 arXiv ID 转为安全的短横线命名法（kebab-case）slug。
    
    例如："2401.12345" → "2401-12345"
         "My Paper.pdf" → "my-paper"
    """
    name = Path(name).stem if "." in name else name
    name = re.sub(r"[^\w\s-]", "", name.lower())
    return re.sub(r"[\s_]+", "-", name).strip("-")


def resolve_output(source: str, arxiv_id: str | None, output_arg: str | None) -> Path:
    """
    确定输出文件的路径。
    
    优先级：
        1. 如果用户指定了 --output，使用用户指定的路径
        2. 如果是 arXiv 论文，用 arXiv ID 作为文件名
        3. 否则用原始文件名（去掉扩展名）作为文件名
    """
    if output_arg:
        p = Path(output_arg)
        return p if p.is_absolute() else REPO_ROOT / p

    if arxiv_id:
        slug = slugify(arxiv_id)
    else:
        slug = slugify(Path(source).stem)

    return DEFAULT_OUTPUT_DIR / f"{slug}.md"


def main():
    """主函数 —— 解析参数，执行转换。"""
    parser = argparse.ArgumentParser(
        description="把 PDF/arXiv 论文转换为 Markdown，保存到 raw/ 目录",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("input", help="arXiv 编号、arXiv 地址或 PDF 文件路径")
    parser.add_argument("-o", "--output", help="输出 .md 文件路径（默认：raw/papers/<slug>.md）")
    parser.add_argument(
        "-b", "--backend",
        choices=["auto", "arxiv2md", "marker", "pymupdf4llm"],
        default="auto",
        help="转换引擎（默认：自动检测）",
    )
    args = parser.parse_args()

    # 判断输入是否为 arXiv 引用
    arxiv_id = extract_arxiv_id(args.input)
    # 确定输出路径
    output = resolve_output(args.input, arxiv_id, args.output)
    backend = args.backend

    print(f"\npdf2md — 论文转 Markdown 工具")
    print(f"  输入：  {args.input}")
    print(f"  输出：  {output.relative_to(REPO_ROOT)}")

    # ---- 自动选择转换引擎 ----
    if backend == "auto":
        if arxiv_id:
            # arXiv 论文优先用 arxiv2md
            backend = "arxiv2md"
        elif check_dependency("marker"):
            # PDF 优先用 marker（精度高）
            backend = "marker"
        elif check_dependency("pymupdf4llm"):
            # marker 不可用则用 pymupdf4llm
            backend = "pymupdf4llm"
        else:
            print("\n错误：没有找到可用的转换引擎。")
            print("请安装其中之一：")
            print("  pip install arxiv2markdown   # 用于 arXiv 论文")
            print("  pip install marker-pdf       # 用于复杂 PDF")
            print("  pip install pymupdf4llm      # 用于简单/快速 PDF 转换")
            sys.exit(1)

    print(f"  引擎：  {backend}")
    print()

    # ---- 执行转换 ----
    if backend == "arxiv2md":
        if not arxiv_id:
            print("错误：arxiv2md 引擎需要 arXiv 编号或地址。")
            sys.exit(1)
        convert_arxiv(arxiv_id, output)
    else:
        pdf_path = Path(args.input)
        if not pdf_path.exists():
            print(f"错误：找不到文件：{args.input}")
            sys.exit(1)
        BACKENDS[backend](pdf_path, output)

    print(f"\n完成。现在可以用以下命令收录：")
    print(f"  python tools/ingest.py {output.relative_to(REPO_ROOT)}")
    print(f"  — 或者在 AI 助手中说：ingest {output.relative_to(REPO_ROOT)}")


# ============================================================
# 程序入口
# ============================================================
if __name__ == "__main__":
    main()
