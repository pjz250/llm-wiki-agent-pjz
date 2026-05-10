#!/usr/bin/env python3
"""
收录一份原始资料到知识维基中。

使用方法：
    python tools/ingest.py <原始文档路径>
    python tools/ingest.py raw/articles/my-article.md
    python tools/ingest.py report.pdf                  # 自动转换为 .md 再收录
    python tools/ingest.py slides.pptx notes.docx       # 批量收录，支持混合格式
    python tools/ingest.py raw/mixed/ --no-convert      # 跳过自动转换
    python tools/ingest.py --validate-only              # 只做验证，不收录

支持的格式（通过 markitdown 自动转换）：
    .pdf .docx .pptx .xlsx .html .htm .txt .csv .json .xml
    .rst .rtf .epub .ipynb .yaml .yml .tsv .wav .mp3

工作流程：
    1. AI 读取原始文档内容
    2. AI 结合 wiki 已有知识上下文
    3. AI 生成结构化的 JSON 输出，包含：
       - 资料摘要页（wiki/sources/<slug>.md）
       - 索引条目更新
       - 综合概述更新
       - 实体页和概念页
       - 矛盾标记
       - 日志条目
    4. 脚本解析 JSON 并写入所有文件
    5. 验证新增页面的链接完整性和索引覆盖
"""

import os
import sys
import json
import hashlib
import re
import shutil
import tempfile
from pathlib import Path
from collections import defaultdict
from datetime import date

# ============================================================
# 项目路径常量
# ============================================================
REPO_ROOT = Path(__file__).parent.parent      # 项目根目录
WIKI_DIR = REPO_ROOT / "wiki"                 # wiki 目录
LOG_FILE = WIKI_DIR / "log.md"                # 日志文件
INDEX_FILE = WIKI_DIR / "index.md"            # 索引文件
OVERVIEW_FILE = WIKI_DIR / "overview.md"      # 综合概述文件

# 可以通过 markitdown 自动转换为 Markdown 的文件扩展名
# .md 文件直接收录，不需要转换
CONVERTIBLE_EXTENSIONS = {
    ".pdf", ".docx", ".pptx", ".xlsx", ".xls",
    ".html", ".htm", ".txt", ".csv", ".json", ".xml",
    ".rst", ".rtf", ".epub", ".ipynb",
    ".yaml", ".yml", ".tsv",
    ".wav", ".mp3",  # 音频文件通过 markitdown 转录
}
# 所有支持的扩展名（包括 .md）
ALL_SUPPORTED_EXTENSIONS = {".md"} | CONVERTIBLE_EXTENSIONS
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


def sha256(text: str) -> str:
    """计算文本的 SHA256 哈希值（取前 16 位）。"""
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def read_file(path: Path) -> str:
    """读取文件内容（UTF-8 编码），文件不存在时返回空字符串。"""
    return path.read_text(encoding="utf-8") if path.exists() else ""


def read_file_with_fallback(path: Path) -> str:
    """
    读取文件内容，自动检测编码（UTF-8 → GBK → UTF-16），
    适配中文 Windows 常见的文件编码场景。
    """
    for enc in ("utf-8", "gbk", "utf-16"):
        try:
            return path.read_text(encoding=enc)
        except (UnicodeDecodeError, UnicodeError):
            continue
    # 所有编码都失败，用带替换的 UTF-8 兜底
    return path.read_text(encoding="utf-8", errors="replace")


def call_llm(prompt: str, max_tokens: int = 8192) -> str:
    """
    调用 AI 语言模型。
    
    参数：
        prompt: 发送给 AI 的提示词
        max_tokens: 生成内容的最大 token 数量（默认 8192，因为收录需要生成大量内容）
    
    返回：
        AI 生成的文本内容
    """
    try:
        from litellm import completion
    except ImportError:
        print("错误：litellm 未安装。请运行：pip install litellm")
        sys.exit(1)
    
    # 从环境变量读取模型名称，默认使用 Claude 3.5 Sonnet（需要较强的理解能力）
    model = os.getenv("LLM_MODEL", "claude-3-5-sonnet-latest")
    
    kwargs = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}]
    }
    
    if max_tokens:
        kwargs["max_tokens"] = max_tokens

    response = completion(**kwargs)
    return response.choices[0].message.content


def write_file(path: Path, content: str):
    """
    写入文件内容。如果目录不存在，自动创建。
    
    参数：
        path: 要写入的文件路径
        content: 文件内容
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    print(f"  已写入：{path.relative_to(REPO_ROOT)}")


def build_wiki_context() -> str:
    """
    构建当前 wiki 的上下文信息，供 AI 参考。
    
    包含：
        - index.md（全局目录）
        - overview.md（综合概述）
        - 最近 5 个收录的资料摘要页（用于矛盾检测）
    
    返回：
        所有上下文拼接成的字符串
    """
    parts = []
    if INDEX_FILE.exists():
        parts.append(f"## wiki/index.md\n{read_file(INDEX_FILE)}")
    if OVERVIEW_FILE.exists():
        parts.append(f"## wiki/overview.md\n{read_file(OVERVIEW_FILE)}")
    # 包含最近几个资料页，用于矛盾检测
    sources_dir = WIKI_DIR / "sources"
    if sources_dir.exists():
        # 按修改时间排序，取最新的 5 个
        recent = sorted(
            sources_dir.glob("*.md"),
            key=lambda p: p.stat().st_mtime,
            reverse=True
        )[:5]
        for p in recent:
            parts.append(f"## {p.relative_to(REPO_ROOT)}\n{read_file_with_fallback(p)}")
    return "\n\n---\n\n".join(parts)


def parse_json_from_response(text: str) -> dict:
    """
    从 AI 的回复中解析出 JSON 对象。
    
    AI 有时会在 JSON 外面包 Markdown 代码块标记（```json ... ```），
    有时会在字符串中包含未转义字符导致 JSON 非法。
    这个函数会做多层容错处理。
    
    参数：
        text: AI 的原始回复文本
    
    返回：
        解析后的 Python 字典
    
    抛出：
        ValueError: 如果找不到 JSON 对象
        json.JSONDecodeError: 如果所有修复尝试都失败
    """
    # 去掉 Markdown 代码块标记
    text = re.sub(r"^```(?:json)?\s*", "", text.strip())
    text = re.sub(r"\s*```$", "", text.strip())
    # 找到最外层的 JSON 对象
    match = re.search(r"\{[\s\S]*\}", text)
    if not match:
        raise ValueError("回复中没有找到 JSON 对象")
    
    raw = match.group()
    
    # 尝试直接解析
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    
    # 尝试修复常见 JSON 错误后重新解析
    # 修复 1：去掉尾随逗号（如 "a": 1,} 或 "a": [1,]）
    fixed = re.sub(r",\s*}", "}", raw)
    fixed = re.sub(r",\s*]", "]", fixed)
    
    try:
        return json.loads(fixed)
    except json.JSONDecodeError:
        pass
    
    # 修复 2：尝试在字符串中未转义的换行符前面加反斜杠
    # 规律：在 ":" 之后到下一个 "," 或 "}" 之间的未转义换行
    # 这个比较复杂，改用更简单的方法：逐行拼接
    lines = fixed.split('\n')
    result_lines = []
    in_string = False
    for line in lines:
        if in_string:
            # 如果正在字符串中，当前行是字符串内容的一部分
            stripped = line.strip()
            if stripped.endswith('"') and not stripped.endswith('\\"'):
                in_string = False
            result_lines.append(line)
        else:
            result_lines.append(line)
            # 检查这一行是否打开了一个未关闭的字符串
            # 简单启发式：这一行包含 : " 但没有结束的 ",
            if re.search(r':\s*"[^"]*$', line) and not re.search(r':\s*"[^"]*",\s*$', line) and not re.search(r':\s*"[^"]*"\s*$', line):
                in_string = True
    
    try:
        return json.loads('\n'.join(result_lines))
    except json.JSONDecodeError:
        pass
    
    # 修复 3：如果还是不行，尝试用更激进的方式 ——
    # 找到 content 字段并对其中的内容做转义处理
    content_match = re.search(r'"content":\s*"(.+)"', fixed, re.DOTALL)
    if content_match:
        raw_content = content_match.group(1)
        # 对 content 中的特殊字符做转义
        escaped = raw_content.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n').replace('\r', '\\r').replace('\t', '\\t')
        fixed2 = fixed[:content_match.start(1)] + escaped + fixed[content_match.end(1):]
        try:
            return json.loads(fixed2)
        except json.JSONDecodeError:
            pass
    
    # 所有修复都失败，抛出原始异常
    return json.loads(raw)


def update_index(new_entry: str, section: str = "Sources"):
    """
    在 index.md 的指定分类下添加一个新条目。
    
    参数：
        new_entry: 要添加的 Markdown 列表项（例如 "- [标题](路径)"）
        section: 分类名称（Sources/Entities/Concepts/Syntheses）
    """
    content = read_file(INDEX_FILE)
    # 如果 index.md 不存在或为空，创建默认结构
    if not content:
        content = (
            "# 维基索引\n\n"
            "## 综合概述\n"
            "- [综合概述](overview.md) — 汇集所有资料的精华\n\n"
            "## 资料\n\n"
            "## 实体\n\n"
            "## 概念\n\n"
            "## 综合问答\n"
        )
    section_header = f"## {section}"
    if section_header in content:
        # 在分类标题下添加新条目
        content = content.replace(
            section_header + "\n",
            section_header + "\n" + new_entry + "\n"
        )
    else:
        # 如果分类还不存在，追加到末尾
        content += f"\n{section_header}\n{new_entry}\n"
    write_file(INDEX_FILE, content)


def append_log(entry: str):
    """
    在 log.md 的顶部追加一条日志（新日志在最上面）。
    """
    existing = read_file(LOG_FILE)
    write_file(LOG_FILE, entry.strip() + "\n\n" + existing)


def update_overview(title: str, slug: str, date_str: str):
    """
    在 overview.md 底部追加一条资料清单条目。
    
    overview.md 现在是一个按时间排列的资料列表，
    不再由 AI 写入综合概述内容，由代码自动维护。
    """
    content = read_file(OVERVIEW_FILE)
    if not content:
        content = "# 资料清单\n\n"
    new_line = f"- {date_str}：[{title}](sources/{slug}.md)"
    write_file(OVERVIEW_FILE, content.rstrip() + "\n" + new_line + "\n")


def extract_wikilinks(content: str) -> list[str]:
    """从页面内容中提取所有 [[维基链接]] 的目标名称（去除管道语法）。"""
    links = re.findall(r'\[\[([^\]]+)\]\]', content)
    result = []
    for link in links:
        if '|' in link:
            link = link.split('|')[0]
        result.append(link)
    return result


def extract_title_from_markdown(content: str) -> str | None:
    """从 Markdown 的 YAML frontmatter 中提取 title 字段。"""
    match = re.search(r'^---\s*\ntitle:\s*"([^"]+)"', content)
    if match:
        return match.group(1)
    match = re.search(r"^---\s*\ntitle:\s*'([^']+)'", content)
    if match:
        return match.group(1)
    return None


def all_wiki_pages() -> set[str]:
    """返回所有 wiki 页面的文件名（小写，不含扩展名）的集合。"""
    pages = set()
    for p in WIKI_DIR.rglob("*.md"):
        if p.name not in ("index.md", "log.md", "lint-report.md"):
            pages.add(p.stem.lower())
    return pages


def validate_ingest(changed_pages: list[str] | None = None) -> dict:
    """
    验证收录后的 wiki 完整性。
    
    检查：
        1. 新增/修改页面中的 [[维基链接]] 是否都能找到目标页面
        2. 新增页面是否都已注册到 index.md
    
    参数：
        changed_pages: 此次收录变更的页面列表（相对于 wiki/ 的路径）
                      如果为 None，则检查所有页面
    
    返回：
        {"broken_links": [(页面路径, 断裂链接名), ...], "unindexed": ["路径", ...]}
    """
    existing_pages = all_wiki_pages()
    index_content = read_file(INDEX_FILE).lower()

    # 确定要扫描的页面范围
    if changed_pages:
        scan_paths = [WIKI_DIR / p for p in changed_pages if (WIKI_DIR / p).exists()]
    else:
        scan_paths = [
            p for p in WIKI_DIR.rglob("*.md")
            if p.name not in ("index.md", "log.md", "lint-report.md")
        ]

    # 检查 1：断裂的维基链接
    broken_links = []
    for page_path in scan_paths:
        content = read_file(page_path)
        rel = str(page_path.relative_to(WIKI_DIR))
        for link in extract_wikilinks(content):
            # 标准化：如果链接包含路径（如 entities/Foo.md），只取文件名部分
            link_stem = Path(link).stem.lower() if '/' in link else link.lower()
            if link_stem not in existing_pages:
                broken_links.append((rel, link))

    # 检查 2：未注册到索引的页面
    unindexed = []
    for p in (changed_pages or []):
        page_path = WIKI_DIR / p
        if page_path.exists():
            stem = page_path.stem.lower()
            if stem not in index_content and p not in ("log.md", "overview.md"):
                unindexed.append(p)

    return {"broken_links": broken_links, "unindexed": unindexed}


def convert_to_md(source: Path) -> Path:
    """
    把非 Markdown 文件转换为 Markdown 格式（使用 markitdown 库）。
    
    参数：
        source: 原始文件的路径
    
    返回：
        转换后的 .md 文件路径（与原始文件放在同一目录）
    """
    try:
        from markitdown import MarkItDown
    except ImportError:
        print("错误：markitdown 未安装（转换非 .md 文件需要）。")
        print("  请运行：pip install markitdown")
        sys.exit(1)

    md = MarkItDown(enable_plugins=False)
    try:
        result = md.convert(str(source))
    except Exception as e:
        print(f"错误：转换 '{source.name}' 失败：{e}")
        sys.exit(1)

    # 输出文件放在原始文件旁边，扩展名改为 .md
    output = source.with_suffix(".md")
    try:
        output.write_text(result.text_content, encoding="utf-8")
    except OSError:
        # 如果原始目录是只读的，使用临时目录
        tmp = Path(tempfile.mkdtemp()) / f"{source.stem}.md"
        tmp.write_text(result.text_content, encoding="utf-8")
        output = tmp

    print(f"  ✓ 已转换 {source.name} → {output.name}")
    return output


def ingest(source_path: str, auto_convert: bool = True):
    """
    收录一份原始资料到 wiki 中。
    
    这是核心函数：
        1. 读取原始文档
        2. 构建 wiki 上下文
        3. 调用 AI 生成知识结构化数据
        4. 写入所有页面
        5. 验证完整性
    
    参数：
        source_path: 原始文档的路径
        auto_convert: 是否自动转换非 .md 文件（默认 True）
    """
    source = Path(source_path)
    if not source.exists():
        print(f"错误：找不到文件：{source_path}")
        sys.exit(1)

    # ---- 自动转换非 Markdown 文件 ----
    converted_path = None
    if source.suffix.lower() != ".md":
        if not auto_convert:
            print(f"  跳过非 .md 文件（--no-convert）：{source.name}")
            return
        if source.suffix.lower() not in CONVERTIBLE_EXTENSIONS:
            print(f"  ⚠️  不支持的格式：{source.suffix} — 跳过 {source.name}")
            print(f"       支持的格式：{', '.join(sorted(ALL_SUPPORTED_EXTENSIONS))}")
            return
        print(f"  正在将 {source.name} 转换为 Markdown...")
        converted_path = convert_to_md(source)
        source = converted_path

    source_content = read_file_with_fallback(source)
    source_hash = sha256(source_content)
    today = date.today().isoformat()

    print(f"\n正在收录：{source.name}  (哈希值：{source_hash})")

    # ---- 构建 AI 提示词 ----
    wiki_context = build_wiki_context()
    schema = read_file(SCHEMA_FILE)

    # 注意：下面的提示词中的 {{ 和 }} 是故意写的（在 f-string 中需要双写大括号才能输出字面量）
    prompt = f"""你正在维护一个中文个人知识维基。请处理以下原始文档，把它的知识整合到 wiki 中。

重要规则（必须遵守）：
1. 所有正文内容（title、source_page、entity_pages 正文、concept_pages 正文、index_entry 描述、log_entry 等）全部使用中文撰写。
2. 每份资料的摘要（source_page）必须**独立可读**，正文中**不要引用其他资料的内容**，不要做跨资料比较。你只需要处理本份资料本身。
3. entity_pages 和 concept_pages 中**只能包含当前 wiki 中还不存在的**新页面。如果一个人物/概念在当前 wiki 中已经存在（你可以在 index 中查到），**不要返回它**，只需在 source_page 中用 [[维基链接]] 指向它即可。
4. overview_update 永远填 null（概述由系统自动维护，你不需要写入）。
5. contradictions 永远填空列表 []（不需要跨资料矛盾检测）。

架构说明和规范：
{schema}

当前 wiki 状态（索引 + 近期页面）：
{wiki_context if wiki_context else "（wiki 为空 —— 这是第一份资料）"}

待收录的新资料（文件：{source.relative_to(REPO_ROOT) if source.is_relative_to(REPO_ROOT) else source.name}）：
=== 资料开始 ===
{source_content}
=== 资料结束 ===

今天的日期：{today}

请只返回一个有效的 JSON 对象（不要 Markdown 代码块，不要在 JSON 外面加说明文字），
包含以下字段：
{{
  "title": "资料的中文标题",
  "slug": "中文短横线-命名-slug（例如 纯粹理性批判-分析报告，不要用英文）",
  "source_page": "wiki/sources/<slug>.md 的完整 Markdown 内容。正文全部用中文，关键人物/概念用 [[维基链接]] 嵌入。",
  "index_entry": "- [中文标题](sources/slug.md) — 一句话中文摘要",
  "overview_update": null,
  "entity_pages": [
    {{"path": "entities/中文名称.md", "content": "完整的 Markdown 内容，正文用中文。path 必须用中文，例如 entities/康德.md"}}
  ],
  "concept_pages": [
    {{"path": "concepts/中文名称.md", "content": "完整的 Markdown 内容，正文用中文。path 必须用中文，例如 concepts/先天综合判断.md"}}
  ],
  "contradictions": [],
  "log_entry": "## [{today}] ingest | 中文标题\\n\\n已收录资料。关键主张：..."
}}
"""

    print(f"  正在调用 AI 模型...")
    raw = call_llm(prompt, max_tokens=8192)
    
    # ---- 解析 AI 的 JSON 响应 ----
    try:
        data = parse_json_from_response(raw)
    except (ValueError, json.JSONDecodeError) as e:
        print(f"错误：解析 AI 回复失败：{e}")
        debug_file = REPO_ROOT / "logs" / "ingest_debug.txt"
        debug_file.parent.mkdir(parents=True, exist_ok=True)
        debug_file.write_text(raw, encoding="utf-8")
        print(f"原始回复已保存到 {debug_file}")
        sys.exit(1)

    # ---- 写入资料摘要页 ----
    slug = data["slug"]
    write_file(WIKI_DIR / "sources" / f"{slug}.md", data["source_page"])

    # ---- 写入实体页（仅新建，不覆盖已有文件）并注册到索引 ----
    for page in data.get("entity_pages", []):
        target = WIKI_DIR / page["path"]
        if target.exists():
            print(f"  跳过已有实体页：{page['path']}")
            continue
        write_file(target, page["content"])
        title = extract_title_from_markdown(page["content"]) or Path(page["path"]).stem
        update_index(f"- [{title}]({page['path']})", section="实体")

    # ---- 写入概念页（仅新建，不覆盖已有文件）并注册到索引 ----
    for page in data.get("concept_pages", []):
        target = WIKI_DIR / page["path"]
        if target.exists():
            print(f"  跳过已有概念页：{page['path']}")
            continue
        write_file(target, page["content"])
        title = extract_title_from_markdown(page["content"]) or Path(page["path"]).stem
        update_index(f"- [{title}]({page['path']})", section="概念")

    # ---- 更新综合概述（由系统自动维护，不再由 AI 写入） ----
    # overview_update 字段固定为 null，这里保留读取只是为了兼容响应结构
    if data.get("overview_update"):
        pass
    update_overview(data["title"], data["slug"], today)

    # ---- 更新索引 ----
    update_index(data["index_entry"], section="资料")

    # ---- 追加日志 ----
    append_log(data["log_entry"])

    # ---- 报告矛盾 ----
    contradictions = data.get("contradictions", [])
    if contradictions:
        print("\n  ⚠️  检测到矛盾：")
        for c in contradictions:
            print(f"     - {c}")

    # ---- 收录后验证 ----
    created_pages = [f"sources/{slug}.md"]
    for page in data.get("entity_pages", []):
        created_pages.append(page["path"])
    for page in data.get("concept_pages", []):
        created_pages.append(page["path"])
    updated_pages = ["index.md", "log.md", "overview.md"]

    validation = validate_ingest(created_pages)

    # ---- 打印变更摘要 ----
    print(f"\n{'='*50}")
    print(f"  ✅ 已收录：{data['title']}")
    print(f"{'='*50}")
    print(f"  创建了 {len(created_pages)} 个页面：")
    for p in created_pages:
        print(f"           + wiki/{p}")
    print(f"  更新了 {len(updated_pages)} 个页面：")
    for p in updated_pages:
        print(f"           ~ wiki/{p}")
    if contradictions:
        print(f"  警告：{len(contradictions)} 处矛盾")
    if validation["broken_links"]:
        print(f"  ⚠️  断裂链接：{len(validation['broken_links'])} 处")
        for page, link in validation["broken_links"][:10]:
            print(f"           wiki/{page} → [[{link}]]")
        if len(validation["broken_links"]) > 10:
            print(f"           ... 还有 {len(validation['broken_links']) - 10} 处")
    if validation["unindexed"]:
        print(f"  ⚠️  未注册到索引：{len(validation['unindexed'])} 个")
        for p in validation["unindexed"][:10]:
            print(f"           wiki/{p}")
        if len(validation["unindexed"]) > 10:
            print(f"           ... 还有 {len(validation['unindexed']) - 10} 个")
    if not validation["broken_links"] and not validation["unindexed"]:
        print("  ✓ 验证通过 —— 没有断裂链接，所有页面已注册到索引")
    print()


# ============================================================
# 程序入口
# ============================================================
if __name__ == "__main__":
    # ---- --validate-only 模式：只做验证，不收录 ----
    if len(sys.argv) == 2 and sys.argv[1] == "--validate-only":
        print("正在运行 wiki 验证（不收录）...\n")
        result = validate_ingest()
        if result["broken_links"]:
            print(f"断裂的维基链接：{len(result['broken_links'])} 处")
            for page, link in result["broken_links"][:20]:
                print(f"  wiki/{page} → [[{link}]]")
            if len(result["broken_links"]) > 20:
                print(f"  ... 还有 {len(result['broken_links']) - 20} 处")
        else:
            print("没有发现断裂的维基链接。")
        print()
        pages = all_wiki_pages()
        index_content = read_file(INDEX_FILE).lower()
        unindexed_all = []
        for p in WIKI_DIR.rglob("*.md"):
            if p.name in ("index.md", "log.md", "lint-report.md", "overview.md"):
                continue
            if p.stem.lower() not in index_content:
                unindexed_all.append(str(p.relative_to(WIKI_DIR)))
        if unindexed_all:
            print(f"未注册到索引的页面：{len(unindexed_all)} 个")
            for up in unindexed_all[:20]:
                print(f"  wiki/{up}")
            if len(unindexed_all) > 20:
                print(f"  ... 还有 {len(unindexed_all) - 20} 个")
        else:
            print("所有页面都已注册到索引。")
        sys.exit(0)

    # ---- 解析参数 ----
    no_convert = "--no-convert" in sys.argv
    args = [a for a in sys.argv[1:] if not a.startswith("--")]

    if not args:
        print("使用方法：python tools/ingest.py <源文件路径> [源文件2 ...] [目录1 ...]")
        print("       python tools/ingest.py --validate-only")
        print("       python tools/ingest.py --no-convert  # 跳过非 .md 文件的自动转换")
        print(f"\n支持的格式：{', '.join(sorted(ALL_SUPPORTED_EXTENSIONS))}")
        sys.exit(1)

    # ---- 收集所有需要处理的文件 ----
    paths_to_process = []
    for arg in args:
        p = Path(arg)
        if p.is_file():
            ext = p.suffix.lower()
            if ext in ALL_SUPPORTED_EXTENSIONS:
                paths_to_process.append(p)
            else:
                print(f"  ⚠️  跳过不支持格式：{p.name} ({ext})")
        elif p.is_dir():
            # 如果是目录，递归搜索其中所有支持的文件
            for f in p.rglob("*"):
                if f.is_file() and f.suffix.lower() in ALL_SUPPORTED_EXTENSIONS:
                    paths_to_process.append(f)
        else:
            # 尝试作为 glob 模式处理
            import glob
            for f in glob.glob(arg, recursive=True):
                g_p = Path(f)
                if g_p.is_file() and g_p.suffix.lower() in ALL_SUPPORTED_EXTENSIONS:
                    paths_to_process.append(g_p)

    # ---- 去重（保留顺序） ----
    unique_paths = []
    seen = set()
    for p in paths_to_process:
        abs_p = p.resolve()
        if abs_p not in seen:
            seen.add(abs_p)
            unique_paths.append(p)

    if not unique_paths:
        print("错误：没有找到任何支持的文件可以收录。")
        print(f"支持的格式：{', '.join(sorted(ALL_SUPPORTED_EXTENSIONS))}")
        sys.exit(1)

    if len(unique_paths) > 1:
        print(f"批量模式：找到 {len(unique_paths)} 个待收录的文件。")

    # ---- 逐个收录 ----
    for p in unique_paths:
        ingest(str(p), auto_convert=not no_convert)
