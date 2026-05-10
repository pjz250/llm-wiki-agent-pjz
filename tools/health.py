#!/usr/bin/env python3
from __future__ import annotations

"""
Wiki 健康检查脚本 —— 检查 wiki 的结构是否完整。

与 lint.py（需要调用 AI 做语义分析，比较昂贵）不同，
health.py 完全基于纯逻辑判断（不调用任何 AI 接口），
速度快到每次对话都可以跑。

使用方法：
    python tools/health.py              # 把报告打印到控制台
    python tools/health.py --save       # 同时保存到 wiki/health-report.md
    python tools/health.py --json       # 输出机器可读的 JSON 格式

检查项目：
  - 空文件 / 内容过少的文件（只有元数据没有实质内容）
  - 索引同步（wiki/index.md 中的记录 vs 磁盘上的实际文件）
  - 日志覆盖（有资料页但缺少对应的 ingest 日志条目）

设计边界（详见 AGENTS.md）：
  health.py = 结构完整性检查，纯逻辑，每次对话都可运行
  lint.py   = 内容质量检查，语义分析（调用 AI），每 10-15 次收录运行一次
"""

# ============================================================
# 导入标准库模块
# ============================================================
import re            # 正则表达式，用于解析 index.md 中的链接和日志条目
import sys           # 系统相关功能
import json          # 用于输出 JSON 格式的报告
import argparse      # 用于解析命令行参数
from pathlib import Path       # 跨平台路径操作
from datetime import date      # 获取当前日期，用于报告时间戳

# ============================================================
# 项目路径常量
# ============================================================
REPO_ROOT = Path(__file__).parent.parent   # 项目根目录
WIKI_DIR = REPO_ROOT / "wiki"              # wiki 目录
INDEX_FILE = WIKI_DIR / "index.md"         # 索引文件
LOG_FILE = WIKI_DIR / "log.md"             # 日志文件

# 内容过少判定阈值：正文内容（去掉 frontmatter 后）少于 100 个字符就算是"stub 文件"
STUB_THRESHOLD_CHARS = 100


def read_file(path: Path) -> str:
    """
    读取文件的全部内容（UTF-8 编码）。
    如果文件不存在，返回空字符串而不是报错。
    """
    return path.read_text(encoding="utf-8") if path.exists() else ""


def all_wiki_pages() -> list[Path]:
    """
    获取 wiki/ 目录下所有 Markdown 文件的列表。
    
    排除元数据文件（index.md、log.md、lint-report.md、health-report.md），
    这些文件不属于"知识页面"。
    """
    # 不需要检查的文件名集合
    exclude = {"index.md", "log.md", "lint-report.md", "health-report.md"}
    # 递归搜索 wiki/ 下所有 .md 文件
    return [p for p in WIKI_DIR.rglob("*.md") if p.name not in exclude]


def strip_frontmatter(content: str) -> str:
    """
    去掉 YAML 格式的元数据（frontmatter），只保留正文内容。
    
    YAML frontmatter 的格式是：
    ---
    title: "xxx"
    type: source
    ---
    正文从这里开始...
    
    参数：
        content: 完整的页面内容
    
    返回：
        去掉 frontmatter 后的纯正文文本
    """
    # 检查是否以 --- 开头（有 frontmatter）
    if content.startswith("---"):
        # 找到第二个 --- 的位置
        end = content.find("---", 3)
        if end != -1:
            # 返回第二个 --- 之后的内容
            return content[end + 3:].strip()
    # 没有 frontmatter，直接返回原文
    return content.strip()


# ============================================================
# 检查 1：空文件 / 内容过少的文件（Stub 文件）
# ============================================================

def check_empty_files(pages: list[Path], threshold: int = STUB_THRESHOLD_CHARS) -> list[dict]:
    """
    找出 wiki 中内容为空或只有 frontmatter（没有实质内容）的页面。
    
    参数：
        pages: wiki 中所有页面的路径列表
        threshold: 内容过少的判定阈值（字符数）
    
    返回：
        字典列表，每个字典包含：
        - path: 文件路径（相对于项目根目录）
        - total_bytes: 文件总大小
        - body_bytes: 正文部分的大小（去掉 frontmatter 后）
        - status: "empty"（完全空）或 "stub"（内容太少）
    
    为什么要检查这个：
        当 API 调用因速率限制被中断时，可能会写出只有 frontmatter
        但没有内容的"残片"页面。这些页面需要被识别出来。
    """
    results = []
    for p in pages:
        raw = read_file(p)                 # 读取文件原始内容
        body = strip_frontmatter(raw)       # 去掉 frontmatter 得到正文
        # 如果正文长度小于阈值，标记为 stub 或 empty
        if len(body) < threshold:
            results.append({
                "path": str(p.relative_to(REPO_ROOT)),  # 相对于项目根目录的路径
                "total_bytes": len(raw),                 # 文件总大小
                "body_bytes": len(body),                 # 正文大小
                "status": "empty" if len(body) == 0 else "stub",  # 状态
            })
    # 按正文大小升序排列（最小的排在最前面）
    results.sort(key=lambda x: x["body_bytes"])
    return results


# ============================================================
# 检查 2：索引同步（index.md 中的记录 vs 实际文件）
# ============================================================

def _parse_index_links(index_content: str) -> set[str]:
    """
    从 index.md 中解析出所有的 Markdown 链接目标路径。
    
    匹配模式：[标题](路径/文件名.md)
    返回相对路径的集合，例如 {'sources/slug.md', 'entities/Foo.md'}
    
    参数：
        index_content: index.md 的完整内容
    
    返回：
        链接中引用的文件路径集合
    """
    return set(re.findall(r'\[.*?\]\(([^)]+\.md)\)', index_content))


def check_index_sync(pages: list[Path]) -> dict:
    """
    比较 wiki/index.md 中的记录和磁盘上的实际文件是否一致。
    
    返回：
        {
            "in_index_not_on_disk": [...],   # index.md 中有记录但文件不存在（过期的索引条目）
            "on_disk_not_in_index": [...],   # 文件存在但 index.md 中没有记录（遗漏注册）
        }
    
    为什么这两种情况都有问题：
        - "过期条目"：页面被删了但 index.md 没更新
        - "遗漏注册"：页面创建了但忘记添加到 index.md（会导致没人能找到它）
    """
    index_content = read_file(INDEX_FILE)
    index_links = _parse_index_links(index_content)

    # overview.md 不在分类列表中（它在 ## Overview 下面），
    # 从两侧都排除它，避免误报
    meta_pages = {"overview.md"}

    # 把 index.md 中的链接解析为绝对路径
    index_paths = set()
    for link in index_links:
        resolved = (WIKI_DIR / link).resolve()
        if Path(link).name not in meta_pages:
            index_paths.add(resolved)

    # 把磁盘上的文件也解析为绝对路径
    disk_paths = set()
    for p in pages:
        if p.name not in meta_pages:
            disk_paths.add(p.resolve())

    # 计算差集
    # A - B：在 index.md 中但磁盘上不存在的（过期条目）
    in_index_not_on_disk = [
        str(p.relative_to(REPO_ROOT)) for p in sorted(index_paths - disk_paths)
        if REPO_ROOT in p.parents or p == REPO_ROOT
    ]
    # B - A：磁盘上存在但 index.md 中没有的（遗漏注册）
    on_disk_not_in_index = [
        str(p.relative_to(REPO_ROOT)) for p in sorted(disk_paths - index_paths)
    ]

    return {
        "in_index_not_on_disk": in_index_not_on_disk,
        "on_disk_not_in_index": on_disk_not_in_index,
    }


# ============================================================
# 检查 3：日志覆盖（资料页是否有对应的 ingest 日志）
# ============================================================

def _parse_log_entries(log_content: str) -> set[str]:
    """
    从 log.md 中解析出所有 ingest（资料收录）操作的条目标题。
    
    日志格式：## [YYYY-MM-DD] ingest | 标题文字
    返回小写化后的标题集合，方便后续匹配。
    
    参数：
        log_content: log.md 的完整内容
    
    返回：
        所有 ingest 条目标题的（小写）集合
    """
    return set(
        m.group(1).strip().lower()
        for m in re.finditer(
            r'^## \[\d{4}-\d{2}-\d{2}\] ingest \| (.+)$',
            log_content,
            re.MULTILINE
        )
    )


def check_log_coverage(pages: list[Path]) -> list[dict]:
    """
    找出没有对应 ingest 日志条目的资料页。
    
    只检查 wiki/sources/*.md（资料摘要页）。
    实体页（entities/）和概念页（concepts/）是收录的"副产品"，
    不需要在日志中有自己的条目。
    
    参数：
        pages: wiki 中所有页面路径列表（但实际只用 sources/ 下的）
    
    返回：
        缺失日志的页面信息列表
    """
    log_content = read_file(LOG_FILE)
    logged_titles = _parse_log_entries(log_content)

    source_dir = WIKI_DIR / "sources"
    # 如果 sources/ 目录还不存在，说明还没有收录过任何资料
    if not source_dir.exists():
        return []

    missing = []
    for p in sorted(source_dir.glob("*.md")):
        # 方法 1：用文件名（slug）匹配。例如 "my-article" → "my article"
        slug = p.stem.lower().replace("-", " ").replace("_", " ")

        # 方法 2：从 frontmatter 中提取 title 来匹配
        content = read_file(p)
        title_match = re.search(r'^title:\s*["\']?(.+?)["\']?\s*$', content, re.MULTILINE)
        fm_title = title_match.group(1).strip().lower() if title_match else ""

        # 如果两种方式都匹配不上，说明缺少日志条目
        if slug not in logged_titles and fm_title not in logged_titles:
            missing.append({
                "path": str(p.relative_to(REPO_ROOT)),  # 文件路径
                "slug": p.stem,                          # 文件名的 slug
                "title": fm_title or p.stem,              # 标题（如果没有 frontmatter 就用文件名）
            })

    return missing


# ============================================================
# 报告生成
# ============================================================

def run_health() -> dict:
    """
    运行所有健康检查，返回结构化的检查结果。
    
    返回：
        包含所有检查结果的字典：
        - date: 检查日期
        - total_pages: 总页面数
        - empty_files: 空文件/stub 文件列表
        - index_sync: 索引同步检查结果
        - log_coverage: 日志覆盖检查结果
    """
    pages = all_wiki_pages()

    return {
        "date": date.today().isoformat(),       # 当前日期
        "total_pages": len(pages),              # 总页面数
        "empty_files": check_empty_files(pages),     # 检查 1 结果
        "index_sync": check_index_sync(pages),       # 检查 2 结果
        "log_coverage": check_log_coverage(pages),   # 检查 3 结果
    }


def format_report(results: dict) -> str:
    """
    把健康检查结果格式化为易读的 Markdown 格式。
    
    参数：
        results: run_health() 返回的字典
    
    返回：
        格式化的 Markdown 字符串
    """
    lines = [
        f"# Wiki 健康报告 — {results['date']}",
        "",
        f"扫描了 {results['total_pages']} 个 wiki 页面。"
        "这些检查都是纯结构性的（没有调用 AI）。",
        "",
    ]

    # ---- 空文件 / Stub 文件 ----
    empty = results["empty_files"]
    lines.append(f"## 空文件 / 内容过少文件（发现 {len(empty)} 个）")
    lines.append("")
    if empty:
        lines.append("| 页面 | 总大小 | 正文大小 | 状态 |")
        lines.append("|---|---|---|---|")
        for ef in empty:
            emoji = "🔴" if ef["status"] == "empty" else "🟡"
            lines.append(f"| `{ef['path']}` | {ef['total_bytes']} | {ef['body_bytes']} | {emoji} {ef['status']} |")
    else:
        lines.append("所有页面都有 frontmatter 之外的实质内容。✅")
    lines.append("")

    # ---- 索引同步 ----
    isync = results["index_sync"]
    stale = isync["in_index_not_on_disk"]       # 过期条目
    missing = isync["on_disk_not_in_index"]      # 遗漏注册
    total_issues = len(stale) + len(missing)
    lines.append(f"## 索引同步（发现 {total_issues} 个问题）")
    lines.append("")

    if stale:
        lines.append("### 过期的索引条目（index.md 中记录了，但磁盘上找不到文件）")
        for s in stale:
            lines.append(f"- `{s}`")
        lines.append("")

    if missing:
        lines.append("### 未注册到索引的文件（磁盘上存在，但 index.md 中没有记录）")
        for m in missing:
            lines.append(f"- `{m}`")
        lines.append("")

    if not stale and not missing:
        lines.append("index.md 与磁盘文件完全同步。✅")
        lines.append("")

    # ---- 日志覆盖 ----
    log_missing = results["log_coverage"]
    lines.append(f"## 日志覆盖（{len(log_missing)} 个资料页缺少日志条目）")
    lines.append("")
    if log_missing:
        lines.append("以下资料页没有对应的 `ingest` 日志条目：")
        lines.append("")
        for lm in log_missing:
            lines.append(f"- `{lm['path']}` — {lm['title']}")
    else:
        lines.append("所有资料页都有对应的日志条目。✅")
    lines.append("")

    return "\n".join(lines)


# ============================================================
# 程序入口
# ============================================================
if __name__ == "__main__":
    # 解析命令行参数
    parser = argparse.ArgumentParser(
        description="Wiki 健康检查 —— 纯结构检测，不调用 AI，速度快"
    )
    parser.add_argument(
        "--save", action="store_true",
        help="保存报告到 wiki/health-report.md"
    )
    parser.add_argument(
        "--json", action="store_true",
        help="输出 JSON 格式（机器可读）而不是 Markdown"
    )
    args = parser.parse_args()

    # 运行所有检查
    results = run_health()

    # 根据命令行参数选择输出格式
    if args.json:
        # JSON 格式输出：适合被其他程序解析
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        # Markdown 格式输出：适合人阅读
        report = format_report(results)
        print(report)
        # 如果指定了 --save，同时保存到文件
        if args.save:
            report_path = WIKI_DIR / "health-report.md"
            report_path.write_text(report, encoding="utf-8")
            print(f"\n报告已保存到：{report_path.relative_to(REPO_ROOT)}")
