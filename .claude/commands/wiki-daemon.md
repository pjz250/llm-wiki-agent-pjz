启动自主维基守护进程。

用法：/wiki-daemon $ARGUMENTS

$ARGUMENTS 可以包含传递给 tools/daemon.py 的标志，例如 `--interval 60` 或 `--once`。

守护进程会轮询 raw/ 目录，查找新增或修改过的文件并自动处理。

通过 Python 脚本运行守护进程：
```
python tools/daemon.py $ARGUMENTS
```

常用标志：
- `--interval N` — 每隔 N 秒轮询一次（默认：30 秒）
- `--once` — 只运行一轮，然后退出
- `--no-graph` — 收录后不重建知识图谱
- `--log-file PATH` — 自定义日志路径（默认：logs/daemon.log）

启动后，告知用户：
- 守护进程正在监控 raw/ 目录中的新文件
- 如何停止（Ctrl+C 或 SIGTERM）
- 在哪里可以找到日志（logs/daemon.log）
