#!/usr/bin/env python3
"""
自主 Wiki 守护进程 —— 自动监控 raw/ 目录，发现新文件就自动收录。

这个守护进程在后台运行，定时扫描 raw/ 目录，发现新的或修改过的资料文件后，
自动执行以下操作：
  1. 收录新文件（调用 ingest.py）
  2. 修复断裂的维基链接（调用 heal.py）
  3. 重建知识图谱（调用 build_graph.py）
  4. 把全部操作记录到控制台和日志文件

使用方法：
    python tools/daemon.py                        # 前台运行
    python tools/daemon.py --interval 60           # 每隔 60 秒扫描一次
    python tools/daemon.py --once                  # 只跑一轮就退出
    python tools/daemon.py --no-graph              # 收录后不重建图谱
    python tools/daemon.py --log-file daemon.log   # 指定日志文件路径

优雅关闭：按 Ctrl+C 或者发送 SIGTERM 信号。
"""

# ============================================================
# 导入标准库模块
# ============================================================
import argparse      # 用于解析命令行参数
import hashlib       # 用于计算文件的 SHA256 哈希值（判断文件是否变化）
import json          # 用于读写 JSON 格式的缓存文件
import os            # 操作系统接口
import signal        # 用于捕获系统信号（SIGINT/SIGTERM），实现优雅关闭
import subprocess    # 用于在 Python 中运行其他命令（如调用 ingest.py）
import sys           # 系统相关功能
import time          # 用于定时休眠（轮询间隔）
from datetime import datetime  # 获取当前时间，用于日志时间戳
from pathlib import Path       # 跨平台路径操作

# ============================================================
# 项目路径常量
# ============================================================
REPO_ROOT = Path(__file__).parent.parent      # 项目根目录（tools/ 的上一级）
RAW_DIR = REPO_ROOT / "raw"                   # 原始资料目录，守护进程监控的就是这个目录
GRAPH_DIR = REPO_ROOT / "graph"               # 图谱数据目录，缓存文件也放在这里
LOGS_DIR = REPO_ROOT / "logs"                 # 日志文件目录
DAEMON_CACHE = GRAPH_DIR / ".daemon_cache.json"  # 守护进程的缓存文件路径
                                                  # 缓存中记录了每个文件的最新哈希值，
                                                  # 用来判断文件是否是新文件

# ============================================================
# 支持的格式列表（与 ingest.py 保持一致）
# ============================================================
SUPPORTED_EXTENSIONS = {
    ".md", ".pdf", ".docx", ".pptx", ".xlsx", ".html", ".htm",
    ".txt", ".csv", ".json", ".xml", ".rst", ".rtf", ".epub",
    ".ipynb", ".yaml", ".yml", ".tsv",
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
# 全局变量 —— 关闭标志
# shutdown_flag 用于优雅关闭：
#   当用户按下 Ctrl+C（SIGINT）时，信号处理函数把这个变量设为 True，
#   主循环看到它为 True 就会在完成当前任务后退出，而不是立即强制终止。
# ============================================================
shutdown_flag = False


def signal_handler(signum, frame):
    """
    信号处理函数 —— 当进程收到 SIGINT（Ctrl+C）或 SIGTERM 时被调用。
    
    参数：
        signum: 接收到的信号编号
        frame: 当前的堆栈帧（用不上，但 signal 模块要求有这个参数）
    
    工作原理：
        把全局变量 shutdown_flag 设为 True，主循环检测到这个变化后，
        会在完成当前轮次的工作后优雅退出。
    """
    global shutdown_flag
    print(f"\n  收到信号 {signum}，正在优雅关闭守护进程...")
    shutdown_flag = True


def sha256(content: str) -> str:
    """
    计算字符串的 SHA256 哈希值（取前 16 位作为短标识）。
    
    参数：
        content: 要计算哈希的文本内容
    
    返回：
        一个 16 位的十六进制字符串，作为文件内容的"指纹"
    
    用途：
        通过比较文件内容的哈希值，判断文件是否被修改过。
        如果哈希值没变，说明内容没变，就不需要重新处理。
    """
    return hashlib.sha256(content.encode()).hexdigest()[:16]


def read_file(path: Path) -> str:
    """
    读取文件的全部内容（以 UTF-8 编码）。
    
    参数：
        path: 要读取的文件路径
    
    返回：
        文件内容字符串。如果文件不存在，返回空字符串。
    """
    return path.read_text(encoding="utf-8") if path.exists() else ""


def load_cache() -> dict:
    """
    从磁盘加载守护进程的缓存数据。
    
    缓存文件是一个 JSON 对象，格式为：
    {
        "raw/某文件.md": "文件内容的哈希值",
        "raw/另一篇.md": "文件内容的哈希值",
        ...
    }
    
    如果缓存文件不存在或格式损坏，返回空字典。
    """
    if DAEMON_CACHE.exists():
        try:
            return json.loads(DAEMON_CACHE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            # JSON 解析失败或文件读取出错，返回空缓存重新开始
            return {}
    return {}


def save_cache(cache: dict):
    """
    把缓存数据保存到磁盘。
    
    参数：
        cache: 要保存的缓存字典，格式同 load_cache 的返回值
    
    保存前确保 graph/ 目录存在，因为缓存文件放在 graph/ 下。
    """
    GRAPH_DIR.mkdir(parents=True, exist_ok=True)
    DAEMON_CACHE.write_text(
        json.dumps(cache, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )


def log(msg: str, log_file: Path | None = None):
    """
    记录一条带时间戳的日志。
    
    参数：
        msg: 要记录的日志消息
        log_file: 日志文件的路径（可选）。如果提供了路径，日志会同时写入文件和控制台。
    
    日志格式：[2026-05-08 18:30:00] 消息内容
    """
    # 获取当前时间，格式化为年-月-日 时:分:秒
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] {msg}"
    # 始终输出到控制台
    print(line)
    # 如果指定了日志文件，也写入文件
    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(line + "\n")


def find_new_files(cache: dict) -> list[Path]:
    """
    扫描 raw/ 目录，找出新增或内容发生了变化的文件。
    
    参数：
        cache: 当前缓存字典，包含已处理文件的路径和哈希值
    
    返回：
        新增或内容发生变化文件的路径列表
    
    工作原理：
        1. 遍历 raw/ 目录下的所有文件
        2. 跳过隐藏文件（以 . 开头的）
        3. 跳过不支持的格式
        4. 计算每个文件的哈希值，与缓存中的值比较
        5. 如果哈希值不同（新文件或修改过的文件），加入返回列表
    """
    # 如果 raw/ 目录还不存在，直接返回空列表
    if not RAW_DIR.exists():
        return []

    new_files = []
    # 递归遍历 raw/ 下的所有文件
    for f in sorted(RAW_DIR.rglob("*")):
        # 只处理文件，跳过目录
        if not f.is_file():
            continue
        # 跳过隐藏文件（文件名以 . 开头）
        if f.name.startswith("."):
            continue
        # 检查文件扩展名是否在支持的格式列表中
        ext = f.suffix.lower()
        if ext not in SUPPORTED_EXTENSIONS:
            continue

        # 计算当前文件内容的哈希值
        content = read_file(f)
        current_hash = sha256(content)
        # 从缓存中获取上次记录的哈希值
        cached_hash = cache.get(str(f))

        # 如果哈希值不同（新文件 或 内容修改过），加入待处理列表
        if cached_hash != current_hash:
            new_files.append(f)

    return new_files


def run_tool(script_name: str, args: list[str], log_file: Path | None) -> bool:
    """
    运行 tools/ 目录下的一个 Python 工具脚本。
    
    参数：
        script_name: 脚本文件名，例如 "ingest.py"
        args: 传递给脚本的命令行参数列表
        log_file: 日志文件路径（用于记录错误信息）
    
    返回：
        True 表示脚本运行成功，False 表示失败
    
    工作原理：
        使用 subprocess.run 在子进程中运行脚本，会等待脚本执行完毕。
    """
    # 构建脚本的完整路径
    script_path = REPO_ROOT / "tools" / script_name
    # 检查脚本文件是否存在
    if not script_path.exists():
        log(f"  [错误] 找不到脚本：{script_name}", log_file)
        return False

    # 构建完整的命令：python tools/xxx.py [参数...]
    cmd = [sys.executable, str(script_path)] + args
    try:
        # 运行命令，等待执行完成
        # capture_output=False 表示脚本的输出直接显示在控制台上
        result = subprocess.run(cmd, capture_output=False, text=True)
        return result.returncode == 0  # 返回码为 0 表示成功
    except Exception as e:
        log(f"  [错误] 运行 {script_name} 失败：{e}", log_file)
        return False


def run_cycle(cache: dict, log_file: Path | None, build_graph: bool) -> dict:
    """
    执行一轮守护进程工作：检测新文件 → 收录 → 修复链接 → 重建图谱。
    
    参数：
        cache: 当前缓存字典
        log_file: 日志文件路径
        build_graph: 是否要重建知识图谱
    
    返回：
        更新后的缓存字典
    
    执行流程：
        1. 调用 find_new_files 检测新文件
        2. 如果有新文件，逐个调用 ingest.py 进行收录
        3. 调用 heal.py 修复断裂的维基链接
        4. 如果需要，调用 build_graph.py 重建知识图谱
        5. 保存更新后的缓存
    """
    # ---- 第 1 步：检测新文件 ----
    new_files = find_new_files(cache)

    # 如果没有新文件，直接返回，不浪费资源
    if not new_files:
        log("  没有检测到新文件", log_file)
        return cache

    # 打印检测到的新文件列表
    log(f"  检测到 {len(new_files)} 个新文件或已修改的文件：", log_file)
    for f in new_files:
        rel = f.relative_to(REPO_ROOT) if f.is_relative_to(REPO_ROOT) else f
        log(f"    + {rel}", log_file)

    # ---- 第 2 步：逐文件收录 ----
    ingested = 0  # 记录成功收录了多少个文件
    for f in new_files:
        # 如果收到了关闭信号，停止处理新文件
        if shutdown_flag:
            break
        rel = str(f.relative_to(REPO_ROOT))
        log(f"  正在收录：{rel}", log_file)
        # 调用 ingest.py 来收录这个文件
        if run_tool("ingest.py", [str(f)], log_file):
            # 收录成功，更新缓存中的哈希值
            content = read_file(f)
            cache[str(f)] = sha256(content)
            ingested += 1
        else:
            log(f"  [警告] 收录失败：{rel}", log_file)

    # 如果没有成功收录任何文件，直接返回
    if ingested == 0:
        return cache

    # 如果收到了关闭信号，在修复链接之前退出
    if shutdown_flag:
        return cache

    # ---- 第 3 步：修复断裂的维基链接 ----
    log(f"  正在修复断裂链接（新增了 {ingested} 份资料）...", log_file)
    run_tool("heal.py", [], log_file)

    # ---- 第 4 步：重建知识图谱 ----
    if build_graph:
        log("  正在重建知识图谱...", log_file)
        run_tool("build_graph.py", [], log_file)

    # ---- 第 5 步：保存缓存 ----
    save_cache(cache)
    log(f"  本轮完成：收录 {ingested} 份，重建图谱={'是' if build_graph else '否'}", log_file)
    return cache


def main():
    """
    主函数 —— 程序入口。
    
    解析命令行参数，启动守护进程主循环。
    """
    global shutdown_flag

    # ---- 注册信号处理函数 ----
    # SIGINT：用户按 Ctrl+C 时触发
    signal.signal(signal.SIGINT, signal_handler)
    # SIGTERM：系统发来的终止信号（如关机或 kill 命令）
    signal.signal(signal.SIGTERM, signal_handler)

    # ---- 解析命令行参数 ----
    parser = argparse.ArgumentParser(
        description="自主 Wiki 守护进程 —— 自动监控 raw/ 目录，发现新文件就自动收录",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--interval", type=int, default=30,
        help="轮询间隔（秒），默认 30 秒扫描一次",
    )
    parser.add_argument(
        "--once", action="store_true",
        help="只运行一轮扫描就退出（适合配合系统定时任务使用）",
    )
    parser.add_argument(
        "--no-graph", action="store_true",
        help="收录后跳过知识图谱重建（速度更快）",
    )
    parser.add_argument(
        "--log-file", type=str, default=None,
        help="日志文件路径（默认：logs/daemon.log）",
    )
    args = parser.parse_args()

    # ---- 设置日志文件路径 ----
    # 如果用户没有指定日志路径，使用默认的 logs/daemon.log
    log_file = None
    if args.log_file:
        log_file = Path(args.log_file)
    else:
        log_file = LOGS_DIR / "daemon.log"
    # 确保日志目录存在
    log_file.parent.mkdir(parents=True, exist_ok=True)

    # 是否重建图谱（默认重建，--no-graph 参数可以关闭）
    build_graph = not args.no_graph
    # 加载缓存
    cache = load_cache()

    # ---- 打印启动信息 ----
    log(f"{'='*50}", log_file)
    log(f"  Wiki 守护进程已启动", log_file)
    log(f"  监控目录：{RAW_DIR}", log_file)
    log(f"  轮询间隔：{args.interval} 秒", log_file)
    log(f"  重建图谱：{'是' if build_graph else '否'}", log_file)
    log(f"  日志文件：{log_file}", log_file)
    log(f"{'='*50}", log_file)

    # ---- 单次运行模式（--once） ----
    if args.once:
        log("  正在运行单次扫描（--once）...", log_file)
        cache = run_cycle(cache, log_file, build_graph)
        save_cache(cache)
        log("  执行完毕。", log_file)
        return

    # ---- 持续运行模式（主循环） ----
    cycle_count = 0  # 记录运行了多少轮
    while not shutdown_flag:
        cycle_count += 1
        log(f"[第 {cycle_count} 轮] 正在扫描...", log_file)
        # 执行一轮工作
        cache = run_cycle(cache, log_file, build_graph)
        save_cache(cache)

        # 如果收到了关闭信号，退出循环
        if shutdown_flag:
            break

        # ---- 等待下一次扫描 ----
        # 按秒递减等待，这样每次循环都检查一下关闭信号，
        # 避免用户按 Ctrl+C 后还要等完整轮询时间才退出
        for remaining in range(args.interval, 0, -1):
            if shutdown_flag:
                break
            time.sleep(1)

    # ---- 退出时打印统计 ----
    log(f"  守护进程已停止，共运行 {cycle_count} 轮。", log_file)


# ============================================================
# 程序入口
# 当直接运行本文件（python tools/daemon.py）时执行 main()
# 当被其他模块导入时不执行
# ============================================================
if __name__ == "__main__":
    main()
