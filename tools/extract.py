#!/usr/bin/env python3
"""
书籍智慧萃取脚本 —— 对 raw/ 中的书籍进行知识萃取，生成概念卡/模型卡/流程卡/清单卡。

与 ingest.py 的关系：
    这是独立于 wiki 收录流程的书籍萃取工具，不依赖也不修改 wiki 结构。
    萃取结果输出到 wiki/cards/<分类-书名>/ 目录下。

使用方法：
    # 单本萃取
    python tools/extract.py raw/方法实践型/搞定GTD.md

    # 批量萃取某个分类下的所有书籍
    python tools/extract.py raw/方法实践型/

    # 批量萃取所有分类下的所有书籍
    python tools/extract.py raw/

    # 强制重新萃取（即使已经生成过）
    python tools/extract.py raw/方法实践型/搞定GTD.md --force

工作流程：
    第 1 轮：AI 按分类提示词对全书做完整分析，输出 Markdown 报告
    第 2 轮：AI 根据分析结果判断需要生成哪些卡片类型
    第 3 轮：AI 按每种卡片的独立提示词逐类穷尽生成卡片内容
"""

import os
import sys
import json
import re
import argparse
from pathlib import Path
from datetime import date

# ============================================================
# 项目路径常量
# ============================================================
REPO_ROOT = Path(__file__).parent.parent
RAW_DIR = REPO_ROOT / "raw"
PROMPT_DIR = REPO_ROOT / "prompt"
CARDS_DIR = REPO_ROOT / "wiki" / "cards"

CATEGORIES = ["方法实践型", "人类思想型", "行为改变型", "硬核技能型"]
CARD_TYPES = ["概念卡", "模型卡", "流程卡", "清单卡"]


# 分类名称 -> 提示词文件名 映射
CATEGORY_PROMPT_FILES = {
    "方法实践型": "方法实践型全书.txt",
    "人类思想型": "人类思想型全书.txt",
    "行为改变型": "行为改变型全书.txt",
    "硬核技能型": "硬核技能型全书.txt",
}

CARD_PROMPT_FILES = {
    "概念卡": "概念卡提示词.txt",
    "模型卡": "模型卡提示词.txt",
    "流程卡": "流程卡提示词.txt",
    "清单卡": "清单卡提示词.txt",
}

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


# ============================================================
# 工具函数
# ============================================================

def read_file_with_fallback(path: Path) -> str:
    """读取文件内容，自动检测编码（UTF-8 → GBK → UTF-16）。"""
    if not path.exists():
        return ""
    for enc in ("utf-8", "gbk", "utf-16"):
        try:
            return path.read_text(encoding=enc)
        except (UnicodeDecodeError, UnicodeError):
            continue
    return path.read_text(encoding="utf-8", errors="replace")


def call_llm(prompt: str, max_tokens: int = 8192) -> str:
    """调用 AI 语言模型（与 ingest.py 使用相同的 litellm 机制）。"""
    try:
        from litellm import completion
    except ImportError:
        print("错误：litellm 未安装。请运行：pip install litellm")
        sys.exit(1)
    model = os.getenv("LLM_MODEL", "deepseek/deepseek-chat")
    try:
        response = completion(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=max_tokens,
        )
        return response.choices[0].message.content
    except Exception as e:
        if "LLM Provider NOT provided" in str(e):
            print(f"错误：模型 \"{model}\" 缺少 provider 前缀。")
            print(f"litellm 需要 provider/ 前缀，例如：")
            print(f"  $env:LLM_MODEL = \"deepseek/deepseek-chat\"")
            print(f"  $env:LLM_MODEL = \"openai/gpt-4o\"")
            print(f"  $env:LLM_MODEL = \"anthropic/claude-3-5-sonnet-latest\"")
            print(f"了解更多：https://docs.litellm.ai/docs/providers")
        raise


def get_category(filepath: Path) -> str:
    """根据文件所在目录判断分类。"""
    for cat in CATEGORIES:
        if cat in filepath.parts:
            return cat
    return "未分类"


def build_book_slug(filepath: Path) -> str:
    """构建书籍 slug（带分类前缀，避免跨分类同名冲突）。"""
    category = get_category(filepath)
    stem = filepath.stem
    safe = re.sub(r'[^\w\u4e00-\u9fff-]', "-", stem)
    safe = re.sub(r"-+", "-", safe).strip("-")
    return f"{category}-{safe}"


def is_already_extracted(slug: str) -> bool:
    """检查该书是否已经萃取过（存在 元信息.json 即视为已萃取）。"""
    return (CARDS_DIR / slug / "元信息.json").exists()


def collect_md_files(path: Path) -> list[Path]:
    """收集要处理的 .md 文件列表。"""
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


def parse_json_from_response(text: str) -> dict:
    """从 AI 回复中提取 JSON 对象，自动修复常见 JSON 错误。"""
    text = re.sub(r"^```(?:json)?\s*", "", text.strip())
    text = re.sub(r"\s*```$", "", text.strip())
    match = re.search(r"\{[\s\S]*\}", text)
    if not match:
        raise ValueError("AI 回复中没有找到 JSON 对象")

    raw = match.group()

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    fixed = re.sub(r",\s*}", "}", raw)
    fixed = re.sub(r",\s*]", "]", fixed)

    try:
        return json.loads(fixed)
    except json.JSONDecodeError:
        pass

    return json.loads(raw)


def write_file(path: Path, content: str):
    """写入文件，自动创建目录。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    print(f"  ✓ 已写入：{path.relative_to(REPO_ROOT)}")


# ============================================================
# 第 1 轮：书籍分析（按分类提示词）
# ============================================================

def build_round1_prompt(book_content: str, category: str) -> str:
    """构建第 1 轮提示词：按分类提示词做完整书籍分析，输出 Markdown 报告。"""
    category_prompt = read_file_with_fallback(
        PROMPT_DIR / CATEGORY_PROMPT_FILES.get(category, f"{category}.txt")
    )

    return f"""你是一位资深的书籍智慧萃取专家。请根据以下分类专属的萃取指导，对这本书做完整的分析。

## 书籍分类
这本书被放置在「{category}」分类下。

## 分类专属萃取指导
{category_prompt}

## 书籍内容
{book_content}

## 输出要求
请严格按照分类专属萃取指导的要求，输出一份完整的书籍分析报告。
全部内容必须使用中文撰写。
直接输出 Markdown 格式的报告，不要包含 JSON 包装，不要包含代码块标记。"""


# ============================================================
# 第 2 轮：卡片决策
# ============================================================

def build_round2_prompt(analysis_report: str, category: str) -> str:
    """构建第 2 轮提示词：根据分析报告判断需要生成哪些卡片。"""
    return f"""你是一位资深的书籍智慧萃取专家。请根据以下书籍分析报告，判断需要生成哪些知识卡片。

## 书籍分类
{category}

## 分析报告
{analysis_report}

## 卡片类型判断规则
根据以下规则逐一判断四种卡片是否需要生成：

- **概念卡**：几乎每本书都有（除非纯工具手册）。
- **模型卡**：任何有"理论框架"的书都有；纯故事/传记可能没有。
- **流程卡**：只有当你**可以照着做**时才需要。哲学、纯文学、大部分历史没有。
- **清单卡**：只有当你需要**并行核对多个条件或事项**时才需要。硬科学解题、心理学反制、方法实践常见，哲学罕见。

## 输出要求
你必须严格按以下 JSON 格式输出，不要包含其他文字：

```json
{{
  "cards_decision": {{
    "概念卡": true,
    "模型卡": false,
    "流程卡": false,
    "清单卡": false
  }},
  "skip_reasons": {{
    "模型卡": "没有提供可迁移的理论框架",
    "流程卡": null,
    "清单卡": null
  }}
}}
```

注意：
- `cards_decision` 中值为 `false` 的卡片，必须在 `skip_reasons` 中写明理由；值为 `true` 的对应 `null`。
- `skip_reasons` 中"概念卡"对应的值也必须存在，如果不跳过则设置为 `null`。
- `skip_reasons` 中的理由必须使用中文撰写。
- 不要输出除 JSON 外的任何内容。"""


# ============================================================
# 第 3 轮：逐类生成卡片（每种卡片独立调用）
# ============================================================

def build_round3_prompt_for_card(
    card_type: str,
    analysis_report: str,
    book_content: str,
    category: str,
) -> str:
    """构建第 3 轮提示词：按该卡片类型的提示词穷尽生成内容。"""
    card_prompt_text = read_file_with_fallback(
        PROMPT_DIR / CARD_PROMPT_FILES.get(card_type, f"{card_type}.txt")
    )

    return f"""你是一位资深的书籍智慧萃取专家。请根据以下书籍分析报告和卡片输出规格，生成「{card_type}」。

## 书籍分类
{category}

## 分析报告（供参考）
{analysis_report}

## {card_type} 输出规格
{card_prompt_text}

## 书籍内容
{book_content}

## 输出要求
请严格按照上述卡片输出规格，生成「{card_type}」的完整内容。
全部内容必须使用中文撰写。
直接输出 Markdown 格式的内容，不要包含 JSON 包装，不要包含代码块标记。
内容必须详尽、穷尽书中所有相关的知识点。"""


# ============================================================
# 核心萃取流程
# ============================================================

def extract_book(filepath: Path, force: bool = False) -> bool:
    """对一本书执行完整的 3 轮知识萃取流程。"""
    category = get_category(filepath)
    book_slug = build_book_slug(filepath)

    if not filepath.exists():
        print(f"  ✗ 文件不存在：{filepath}")
        return False

    if is_already_extracted(book_slug) and not force:
        print(f"  → 已跳过（已萃取过）：{filepath.relative_to(REPO_ROOT)}")
        return True

    book_title = filepath.stem
    print(f"\n{'='*60}")
    print(f"  书籍：{book_title}")
    print(f"  分类：{category}")
    print(f"{'='*60}")

    # 读取书籍内容
    print("  [1/5] 读取书籍内容...")
    book_content = read_file_with_fallback(filepath)
    if not book_content.strip():
        print(f"  ✗ 文件内容为空：{filepath}")
        return False

    output_dir = CARDS_DIR / book_slug

    # ── 第 1 轮：书籍分析 ──
    print("  [2/5] 第 1 轮：按分类提示词进行书籍分析...")
    round1_prompt = build_round1_prompt(book_content, category)
    analysis_report = ""
    try:
        analysis_report = call_llm(round1_prompt, max_tokens=16384)
    except Exception as e:
        print(f"  ✗ 第 1 轮失败：{e}")
        return False

    analysis_file = output_dir / "书籍分析报告.md"
    full_analysis = (
        f"---\n"
        f"title: \"{book_title} 分析报告\"\n"
        f"type: analysis\n"
        f"book: \"{book_title}\"\n"
        f"category: \"{category}\"\n"
        f"generated_at: {date.today()}\n"
        f"---\n\n"
        f"{analysis_report}\n"
    )
    write_file(analysis_file, full_analysis)

    # ── 第 2 轮：卡片决策 ──
    print("  [3/5] 第 2 轮：根据分析结果判断需要生成哪些卡片...")
    round2_prompt = build_round2_prompt(analysis_report, category)
    round2_raw = ""
    round2_result = {}
    try:
        round2_raw = call_llm(round2_prompt)
        round2_result = parse_json_from_response(round2_raw)
    except Exception as e:
        print(f"  ✗ 第 2 轮失败：{e}")
        if round2_raw:
            print(f"  AI 原始回复：{round2_raw[:500]}")
        return False

    cards_decision = round2_result.get("cards_decision", {})
    skip_reasons = round2_result.get("skip_reasons", {})

    active_cards = [ct for ct in CARD_TYPES if cards_decision.get(ct, False)]
    skipped_cards = [ct for ct in CARD_TYPES if not cards_decision.get(ct, False)]

    print(f"  将生成：{', '.join(active_cards) if active_cards else '无'}")
    for ct in skipped_cards:
        reason = skip_reasons.get(ct) or "未提供理由"
        print(f"  跳过 {ct}：{reason}")

    # ── 第 3 轮：逐类生成卡片 ──
    generated_cards = []
    for ct in active_cards:
        print(f"  [4/5] 第 3 轮：生成 {ct}...")
        card_prompt = build_round3_prompt_for_card(ct, analysis_report, book_content, category)
        card_content = ""
        try:
            card_content = call_llm(card_prompt, max_tokens=16384)
        except Exception as e:
            print(f"  ✗ 生成 {ct} 失败：{e}")
            continue

        card_file = output_dir / f"{ct}.md"
        full_card = (
            f"---\n"
            f"title: \"{book_title} - {ct}\"\n"
            f"type: card\n"
            f"book: \"{book_title}\"\n"
            f"category: \"{category}\"\n"
            f"card_type: \"{ct}\"\n"
            f"generated_at: {date.today()}\n"
            f"---\n\n"
            f"{card_content}\n"
        )
        write_file(card_file, full_card)
        generated_cards.append(ct)

    # 写入元信息
    meta = {
        "title": book_title,
        "category": category,
        "source_file": str(filepath.relative_to(REPO_ROOT)),
        "cards_generated": generated_cards,
        "cards_skipped": skipped_cards,
        "skip_reasons": skip_reasons,
        "generated_at": str(date.today()),
    }
    write_file(output_dir / "元信息.json",
               json.dumps(meta, ensure_ascii=False, indent=2))

    print(f"  [5/5] 完成！")
    print(f"  分析报告：书籍分析报告.md")
    print(f"  生成了 {len(generated_cards)}/{len(active_cards)} 张卡片")
    print(f"{'='*60}")
    return True


# ============================================================
# 主入口
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description="书籍智慧萃取工具 —— 对书籍进行知识萃取，生成概念卡/模型卡/流程卡/清单卡",
    )
    parser.add_argument(
        "path",
        nargs="?",
        default=None,
        help=(
            "要萃取的路径。支持：\n"
            "  - 单本书：raw/方法实践型/搞定GTD.md\n"
            "  - 单分类：raw/方法实践型/\n"
            "  - 全部分类：raw/\n"
            "  - 不指定：自动扫描 raw/ 下所有分类"
        ),
    )
    parser.add_argument(
        "--force", "-f",
        action="store_true",
        help="强制重新萃取（即使已经生成过也会重新生成）",
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
        print("没有找到要萃取的书籍文件（.md）。")
        print(f"请确保在 raw/ 的分类目录下放置了 Markdown 格式的书籍文件。")
        print(f"当前分类目录：{', '.join(CATEGORIES)}")
        sys.exit(0)

    print(f"找到 {len(files)} 本书籍待处理")
    print(f"{'='*60}")

    success = 0
    skipped = 0
    failed = 0

    for fp in files:
        slug = build_book_slug(fp)
        if is_already_extracted(slug) and not args.force:
            print(f"  → 已跳过：{fp.name}（已萃取过）")
            skipped += 1
            continue
        if extract_book(fp, args.force):
            success += 1
        else:
            failed += 1

    print(f"\n{'='*60}")
    print(f"批量萃取完成！")
    print(f"  成功：{success} 本")
    print(f"  跳过：{skipped} 本")
    print(f"  失败：{failed} 本")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
