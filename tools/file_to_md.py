#!/usr/bin/env python3
"""
批量文件转换工具 —— 把目录下的所有非 Markdown 文件自动转换为 Markdown 格式。

使用方法：
    python tools/file_to_md.py --input_dir raw/papers
    python tools/file_to_md.py --input_dir raw/papers --delete_source

参数说明：
    --input_dir      要处理的目录路径（必填）
    --delete_source  转换后是否删除原始文件（可选，默认保留）

支持的格式：
    所有 markitdown 能处理的格式：pdf、docx、pptx、xlsx、html 等
"""

import argparse
from tqdm import tqdm           # 进度条显示库
from pathlib import Path
from markitdown import MarkItDown  # 微软出品的文件转 Markdown 库


def convert_directory_to_md(input_dir: Path, delete_source: bool = False):
    """
    把目录下的所有非 Markdown 文件转换为 Markdown 格式。
    
    参数：
        input_dir: 要处理的目录路径
        delete_source: 转换后是否删除原始文件（默认 False）
    
    注意事项：
        - 跳过隐藏文件（以 . 开头的文件）
        - 跳过已经是 .md 的文件
        - 转换后的 .md 文件与原始文件放在同一目录
    """

    # 创建 MarkItDown 实例
    md = MarkItDown(enable_plugins=False)

    # 获取目录下所有文件（递归搜索）
    files_to_process = [f for f in input_dir.rglob('*') if f.is_file()]

    if not files_to_process:
        print(f"目录中没有找到文件：{input_dir}！")
        return

    # 用 tqdm 显示进度条
    for file_path in tqdm(files_to_process, desc="正在转换文件"):
        # 跳过隐藏文件和已存在的 Markdown 文件
        if file_path.name.startswith('.') or file_path.suffix.lower() == '.md':
            print(f"跳过转换：{file_path.name}")
            continue

        # 构造输出文件路径（将原始扩展名替换为 .md）
        output_path = file_path.with_suffix(".md")
        try:
            # 执行转换
            result = md.convert(str(file_path))
            # 保存为 .md 文件
            output_path.write_text(result.text_content, encoding="utf-8")
            # 如果指定了 --delete_source，删除原始文件
            if delete_source:
                file_path.unlink()
            tqdm.write(f"已转换：{file_path.name}")
        except Exception as e:
            tqdm.write(f"失败：无法转换 '{file_path.name}'。原因：{e}")


def main(args):
    """
    主函数 —— 设置路径并执行批量转换。
    """
    # 将输入路径解析为绝对路径
    input_path = Path(args.input_dir).resolve()
    print("-" * 40)
    print(f"输入目录：{input_path}")
    print("-" * 40)

    # 执行转换
    try:
        convert_directory_to_md(input_path, args.delete_source)
        print("\n转换完成。")
    except FileNotFoundError:
        print(f"\n错误：找不到输入目录 {input_path}")
    except Exception as e:
        print(f"\n执行过程中出现意外错误：{e}")


# ============================================================
# 程序入口
# ============================================================
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="把目录下的所有文件转换为 Markdown 格式"
    )
    parser.add_argument(
        "--input_dir",
        type=str,
        help="要处理的目录路径"
    )
    parser.add_argument(
        "--delete_source",
        action="store_true",
        help="转换后是否删除原始文件"
    )
    args = parser.parse_args()

    main(args)
