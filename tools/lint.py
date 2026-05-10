#!/usr/bin/env python3
from __future__ import annotations

"""
Wiki 质量检查脚本 —— 检查 wiki 的内容质量和结构问题。

使用方法：
    python tools/lint.py
    python tools/lint.py --save          # 保存检查报告到 wiki/lint-report.md

检查项目：
  - 孤页（没有入链的页面）
  - 断裂的维基链接（指向不存在的页面）
  - 缺失的实体页（在 3+ 页面中被引用但没有独立页面）
  - 页面之间的矛盾
  - 数据缺口和需要补充的资料建议

与 health.py 的区别：
    health.py 只做纯结构检查（不调用 AI），每次对话都可以跑。
    lint.py 需要调用 AI 做语义分析，比较耗时，每 10-15 次收录跑一次。
"""

import re
import sys
import json
import argparse
import statistics          # 用于计算统计量（平均值、标准差），判断异常节点
from pathlib import Path
from collections import defaultdict
from datetime import date

import os

# ============================================================
# 项目路径常量
# ============================================================
REPO_ROOT = Path(__file__).parent.parent      # 项目根目录
WIKI_DIR = REPO_ROOT / "wiki"                 # wiki 目录
GRAPH_DIR = REPO_ROOT / "graph"               # 图谱目录
GRAPH_JSON = GRAPH_DIR / "graph.json"         # 图谱数据文件
LOG_FILE = WIKI_DIR / "log.md"                # 日志文件
SCHEMA_FILE = REPO_ROOT / "CLAUDE.md"         # 架构说明文件

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
    
    model = os.getenv(model_env, default_model)
    response = completion(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=max_tokens
    )
    return response.choices[0].message.content


def all_wiki_pages() -> list[Path]:
    """返回 wiki/ 下所有知识页面的路径列表（排除 index.md、log.md、lint-report.md）。"""
    return [p for p in WIKI_DIR.rglob("*.md")
            if p.name not in ("index.md", "log.md", "lint-report.md")]


def extract_wikilinks(content: str) -> list[str]:
    """从页面内容中提取所有 [[维基链接]] 的目标名称。"""
    return re.findall(r'\[\[([^\]]+)\]\]', content)


def page_name_to_path(name: str) -> list[Path]:
    """
    通过 [[维基链接]] 的名称找到对应的文件路径。
    
    参数：
        name: 维基链接中的名称（不区分大小写）
    
    返回：
        匹配的文件路径列表（可能有多个同名但不同目录的文件）
    """
    candidates = []
    for p in all_wiki_pages():
        if p.stem.lower() == name.lower() or p.stem == name:
            candidates.append(p)
    return candidates


def find_orphans(pages: list[Path]) -> list[Path]:
    """
    找出孤页 —— 没有其他页面通过 [[链接]] 指向它的页面。
    
    参数：
        pages: 所有 wiki 页面的路径列表
    
    返回：
        孤页的路径列表（排除 overview.md，它是特殊页面）
    
    工作原理：
        遍历所有页面，统计每个页面的入链数量。
        入链为 0 的就是孤页。
    """
    # 统计每个页面的入链次数
    inbound = defaultdict(int)
    for p in pages:
        content = read_file(p)
        for link in extract_wikilinks(content):
            resolved = page_name_to_path(link)
            for r in resolved:
                inbound[r] += 1
    # 返回入链为 0 的页面（排除 overview.md）
    return [p for p in pages if inbound[p] == 0 and p != WIKI_DIR / "overview.md"]


def find_broken_links(pages: list[Path]) -> list[tuple[Path, str]]:
    """
    找出断裂的维基链接 —— [[链接]] 指向了不存在的页面。
    
    参数：
        pages: 所有 wiki 页面的路径列表
    
    返回：
        (包含断裂链接的页面路径, 断裂链接名称) 的列表
    """
    broken = []
    for p in pages:
        content = read_file(p)
        for link in extract_wikilinks(content):
            if not page_name_to_path(link):
                broken.append((p, link))
    return broken


def find_missing_entities(pages: list[Path]) -> list[str]:
    """
    找出缺失的实体页 —— 在 3 个以上页面中被 [[引用]] 但没有独立页面。
    
    参数：
        pages: 所有 wiki 页面的路径列表
    
    返回：
        缺失实体名称的列表
    """
    mention_counts: dict[str, int] = defaultdict(int)
    existing_pages = {p.stem.lower() for p in pages}
    for p in pages:
        content = read_file(p)
        links = extract_wikilinks(content)
        for link in links:
            if link.lower() not in existing_pages:
                mention_counts[link] += 1
    return [name for name, count in mention_counts.items() if count >= 3]


def check_link_density(pages: list[Path], min_outbound: int = 2) -> list[dict]:
    """
    检查链接密度 —— 找出出站链接少于指定数量的页面。
    
    参数：
        pages: 所有 wiki 页面的路径列表
        min_outbound: 最低出站链接数（默认 2）
    
    返回：
        链接稀疏的页面信息列表
    
    为什么重要：
        出站链接太少的页面容易变成"孤岛"，久而久之就成为孤页。
        每个页面至少应该有 2 个出站链接来维持图谱的连接性。
    """
    results = []
    for p in pages:
        if p.name == "overview.md":
            continue  # overview.md 是综合概述，链接模式不同，跳过
        content = read_file(p)
        links = extract_wikilinks(content)
        # 去重：同一个链接多次出现只算一次
        unique_links = set(link.lower() for link in links)
        if len(unique_links) < min_outbound:
            results.append({
                "path": str(p.relative_to(REPO_ROOT)),
                "outbound_links": len(unique_links),
                "links": sorted(unique_links),
            })
    results.sort(key=lambda x: x["outbound_links"])
    return results


# ============================================================
# 图谱层面的检查（需要 graph.json）
# ============================================================

def load_graph_data() -> dict | None:
    """加载 graph.json 图谱数据。如果文件不存在或损坏，返回 None。"""
    if not GRAPH_JSON.exists():
        return None
    try:
        return json.loads(GRAPH_JSON.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, IOError):
        print("  [警告] graph.json 已损坏 —— 跳过图谱层面的检查")
        return None


def _build_degree_map(graph_data: dict) -> dict[str, int]:
    """根据图谱的边数据，构建每个节点的度（连接数）映射表。"""
    degrees: dict[str, int] = {}
    for node in graph_data.get("nodes", []):
        degrees[node["id"]] = 0
    for edge in graph_data.get("edges", []):
        degrees[edge["from"]] = degrees.get(edge["from"], 0) + 1
        degrees[edge["to"]] = degrees.get(edge["to"], 0) + 1
    return degrees


def _build_community_map(graph_data: dict) -> dict[str, int]:
    """构建节点 ID 到社区 ID 的映射。"""
    return {
        node["id"]: node.get("group", -1)
        for node in graph_data.get("nodes", [])
    }


def check_hub_stubs(graph_data: dict, pages: list[Path], min_content_chars: int = 500) -> list[dict]:
    """
    找出 Hub Stub —— 连接数异常高但内容却很短的页面。
    
    判断标准：度（连接数）超过平均值+2个标准差，但内容长度小于阈值。
    
    参数：
        graph_data: 图谱数据
        pages: 所有 wiki 页面
        min_content_chars: 内容过少阈值（字符数）
    
    返回：
        Hub Stub 页面列表
    """
    degrees = _build_degree_map(graph_data)
    deg_values = list(degrees.values())
    if len(deg_values) < 2:
        return []

    # 计算平均值和标准差
    mean_deg = statistics.mean(deg_values)
    std_deg = statistics.stdev(deg_values)
    # 阈值：平均值 + 2 个标准差
    threshold = mean_deg + 2 * std_deg

    # 建立节点 ID 到页面路径的映射
    node_to_path: dict[str, Path] = {}
    for p in pages:
        nid = p.relative_to(WIKI_DIR).as_posix().replace(".md", "")
        node_to_path[nid] = p

    results = []
    for node_id, deg in degrees.items():
        if deg <= threshold:
            continue  # 不是超级枢纽
        path = node_to_path.get(node_id)
        if not path:
            continue
        content_len = len(read_file(path))
        if content_len < min_content_chars:
            results.append({
                "node_id": node_id,
                "degree": deg,
                "content_len": content_len,
                "path": str(path.relative_to(REPO_ROOT)),
            })
    return sorted(results, key=lambda x: x["degree"], reverse=True)


def check_fragile_bridges(graph_data: dict) -> list[dict]:
    """
    找出脆弱桥梁 —— 两个社区之间只有 1 条边连接的情况。
    
    如果这条边断了，两个社区就彻底隔离了。
    """
    comm_map = _build_community_map(graph_data)
    cross_comm: dict[tuple[int, int], list[dict]] = {}

    for edge in graph_data.get("edges", []):
        ca = comm_map.get(edge["from"], -1)
        cb = comm_map.get(edge["to"], -1)
        if ca < 0 or cb < 0 or ca == cb:
            continue
        key = (min(ca, cb), max(ca, cb))
        cross_comm.setdefault(key, []).append(edge)

    return [
        {
            "comm_a": pair[0],
            "comm_b": pair[1],
            "bridge_from": edges[0]["from"],
            "bridge_to": edges[0]["to"],
        }
        for pair, edges in sorted(cross_comm.items())
        if len(edges) == 1  # 只有一条边的桥梁
    ]


def check_isolated_communities(graph_data: dict) -> list[dict]:
    """
    找出孤立社区 —— 完全没有外部连接的集群（知识孤岛）。
    """
    comm_map = _build_community_map(graph_data)

    # 构建社区 → 成员列表
    comm_members: dict[int, list[str]] = {}
    for node_id, comm_id in comm_map.items():
        if comm_id < 0:
            continue
        comm_members.setdefault(comm_id, []).append(node_id)

    # 记录哪些社区有外部连接
    has_external = set()
    for edge in graph_data.get("edges", []):
        ca = comm_map.get(edge["from"], -1)
        cb = comm_map.get(edge["to"], -1)
        if ca >= 0 and cb >= 0 and ca != cb:
            has_external.add(ca)
            has_external.add(cb)

    results = []
    for comm_id, members in sorted(comm_members.items()):
        if len(members) < 2:  # 跳过单节点"社区"
            continue
        if comm_id not in has_external:
            results.append({
                "community_id": comm_id,
                "node_count": len(members),
                "members": members[:10],  # 最多显示 10 个成员
            })
    return results


# ============================================================
# 主检查函数
# ============================================================

def run_lint():
    """运行所有 lint 检查，输出报告。"""
    pages = all_wiki_pages()
    today = date.today().isoformat()

    if not pages:
        print("wiki 是空的。没有需要检查的内容。")
        return ""

    print(f"正在检查 {len(pages)} 个 wiki 页面...")

    # ---- 确定性检查（不调用 AI） ----
    orphans = find_orphans(pages)                     # 孤页
    broken = find_broken_links(pages)                 # 断裂链接
    missing_entities = find_missing_entities(pages)    # 缺失实体

    print(f"  孤页：{len(orphans)}")
    print(f"  断裂链接：{len(broken)}")
    print(f"  缺失实体页：{len(missing_entities)}")

    # 链接密度检查
    sparse_pages = check_link_density(pages)
    print(f"  链接稀疏页（出站链接 < 2）：{len(sparse_pages)}")

    # ---- 图谱层面的检查（需要 graph.json） ----
    graph_data = load_graph_data()
    hub_stubs: list[dict] = []
    fragile_bridges: list[dict] = []
    isolated_comms: list[dict] = []

    if graph_data and graph_data.get("nodes") and graph_data.get("edges"):
        print("  正在运行图谱层面的检查...")
        hub_stubs = check_hub_stubs(graph_data, pages)
        fragile_bridges = check_fragile_bridges(graph_data)
        isolated_comms = check_isolated_communities(graph_data)
        print(f"    Hub Stub（大枢纽但内容少）：{len(hub_stubs)}")
        print(f"    脆弱桥梁：{len(fragile_bridges)}")
        print(f"    孤立社区：{len(isolated_comms)}")
    elif graph_data:
        print("  [跳过] graph.json 中没有数据 —— 跳过图谱层面检查")
    else:
        print("  [跳过] 没有 graph.json —— 请先运行 python tools/build_graph.py")

    # ---- 语义检查（调用 AI） ----
    # 取前 20 个页面作为样本（避免上下文溢出）
    sample = pages[:20]
    pages_context = ""
    for p in sample:
        rel = p.relative_to(REPO_ROOT)
        pages_context += f"\n\n### {rel}\n{read_file(p)[:1500]}"

    print("  正在通过 AI 进行语义检查...")
    prompt = f"""你正在对一个知识维基进行质量检查。请审阅以下页面，找出：

1. 页面之间的矛盾（不同页面对同一问题的说法有冲突）
2. 过时的内容（新资料已经更新了知识，但旧页面的摘要还没跟上）
3. 数据缺口（有哪些重要问题是这个 wiki 回答不了的 —— 建议需要补充什么资料）
4. 被提及但缺乏深度的概念

Wiki 页面（共 {len(sample)} 页的样本）：
{pages_context}

请返回一份 Markdown 格式的检查报告，包含以下小节：
## 矛盾
## 过时的内容
## 数据缺口与建议补充的资料
## 需要加深的概念

请具体指出涉及哪些页面的哪些说法。
"""
    semantic_report = call_llm(prompt, "LLM_MODEL", "claude-3-5-sonnet-latest", max_tokens=3000)

    # ---- 组装完整报告 ----
    report_lines = [
        f"# Wiki 质量检查报告 — {today}",
        "",
        f"扫描了 {len(pages)} 个页面。",
        "",
        "## 结构问题",
        "",
    ]

    if orphans:
        report_lines.append("### 孤页（没有入链的页面）")
        for p in orphans:
            report_lines.append(f"- `{p.relative_to(REPO_ROOT)}`")
        report_lines.append("")

    if broken:
        report_lines.append("### 断裂的维基链接")
        for page, link in broken:
            report_lines.append(f"- `{page.relative_to(REPO_ROOT)}` 链接到 `[[{link}]]` —— 找不到目标页面")
        report_lines.append("")

    if missing_entities:
        report_lines.append("### 缺失的实体页（被引用 3 次以上但没有独立页面）")
        report_lines.append("> [!warning] 建议操作\n> 运行 `python tools/heal.py` 自动创建这些缺失的实体页。")
        for name in missing_entities:
            report_lines.append(f"- `[[{name}]]`")
        report_lines.append("")

    if not orphans and not broken and not missing_entities and not sparse_pages:
        report_lines.append("没有发现结构问题。")
        report_lines.append("")

    if sparse_pages:
        report_lines.append(f"### 链接稀疏页（出站链接密度低）—— {len(sparse_pages)} 页")
        report_lines.append("这些页面的出站链接少于 2 个。添加更多链接可以防止它们变成孤页：")
        report_lines.append("")
        report_lines.append("| 页面 | 出站链接数 | 已有链接 |")
        report_lines.append("|---|---|---|")
        for sp in sparse_pages:
            existing = ", ".join(f"`[[{l}]]`" for l in sp["links"]) if sp["links"] else "—"
            report_lines.append(f"| `{sp['path']}` | {sp['outbound_links']} | {existing} |")
        report_lines.append("")

    # ---- 图谱层面的问题 ----
    report_lines.append("## 图谱层面的问题")
    report_lines.append("")

    if not graph_data:
        report_lines.append("> [!tip]")
        report_lines.append("> 图谱层面的检查被跳过了。请先运行 `python tools/build_graph.py`，然后重新运行 lint。")
        report_lines.append("")
    elif not graph_data.get("nodes") or not graph_data.get("edges"):
        report_lines.append("> [!tip]")
        report_lines.append("> 图谱数据为空。请先收录一些资料再运行 `python tools/build_graph.py`。")
        report_lines.append("")
    else:
        # Hub Stub
        report_lines.append(f"### 内容不足的枢纽页面（{len(hub_stubs)} 页）")
        if hub_stubs:
            report_lines.append("这些节点连接数异常高，但内容很少：")
            report_lines.append("")
            report_lines.append("| 页面 | 连接数 | 内容长度 | 状态 |")
            report_lines.append("|---|---|---|---|")
            for hs in hub_stubs:
                status = "🔴 空壳" if hs["content_len"] < 250 else "🟡 单薄"
                report_lines.append(f"| `{hs['path']}` | {hs['degree']} | {hs['content_len']} 字 | {status} |")
        else:
            report_lines.append("没有发现 Hub Stub —— 所有高连接节点都有足够的内容。")
        report_lines.append("")

        # 脆弱桥梁
        report_lines.append(f"### 脆弱桥梁（{len(fragile_bridges)} 对社区）")
        if fragile_bridges:
            report_lines.append("以下社区连接依赖单条边 —— 一旦断了就隔离了：")
            for fb in fragile_bridges:
                report_lines.append(f"- 社区 {fb['comm_a']} ↔ 社区 {fb['comm_b']} 通过 `{fb['bridge_from']}` → `{fb['bridge_to']}`")
        else:
            report_lines.append("没有发现脆弱桥梁 —— 所有社区连接都有冗余。")
        report_lines.append("")

        # 孤立社区
        report_lines.append(f"### 孤立社区（{len(isolated_comms)} 个）")
        if isolated_comms:
            report_lines.append("以下社区完全没有外部连接 —— 知识孤岛：")
            report_lines.append("")
            report_lines.append("| 社区 | 节点数 | 成员 |")
            report_lines.append("|---|---|---|")
            for ic in isolated_comms:
                members_str = ", ".join(ic["members"][:5])
                if ic["node_count"] > 5:
                    members_str += ", …"
                report_lines.append(f"| {ic['community_id']} | {ic['node_count']} | {members_str} |")
        else:
            report_lines.append("没有发现孤立社区 —— 所有集群都有外部连接。")
        report_lines.append("")

    report_lines.append("---")
    report_lines.append("")
    report_lines.append(semantic_report)

    report = "\n".join(report_lines)
    print("\n" + report)
    return report


def append_log(entry: str):
    """在 log.md 顶部追加一条日志。"""
    existing = read_file(LOG_FILE)
    LOG_FILE.write_text(entry.strip() + "\n\n" + existing, encoding="utf-8")


# ============================================================
# 程序入口
# ============================================================
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Wiki 质量检查 —— 找出孤页、断裂链接、矛盾等")
    parser.add_argument(
        "--save", action="store_true",
        help="保存检查报告到 wiki/lint-report.md"
    )
    args = parser.parse_args()

    report = run_lint()

    if args.save and report:
        report_path = WIKI_DIR / "lint-report.md"
        report_path.write_text(report, encoding="utf-8")
        print(f"\n报告已保存到：wiki/lint-report.md")
