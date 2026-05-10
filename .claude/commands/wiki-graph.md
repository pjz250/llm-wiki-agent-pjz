构建知识维基的知识图谱。

用法：/wiki-graph

首先尝试运行：python tools/build_graph.py --open

如果失败（缺少依赖），手动构建图谱：

1. 使用 Grep 在所有 wiki/ 文件中找出所有 [[维基链接]]
2. 构建节点列表：每个 wiki 页面一个节点，包含 id=相对路径、label=标题、type=页面类型
3. 构建边列表：每个 [[维基链接]] 一条边，标记为 EXTRACTED
4. 推断维基链接没有捕捉到的隐含关系 —— 标记为 INFERRED 并给置信度分数（0.0–1.0）；低置信度标记为 AMBIGUOUS
5. 写入 graph/graph.json，包含 {nodes, edges, built: 日期}
6. 写入 graph/graph.html，生成自包含的 vis.js 页面（节点按类型着色、边按类型着色、交互式、可搜索）

构建完成后，总结：节点数、边数、按类型分类情况、连接最多的节点（枢纽）。

追加日志到 wiki/log.md：## [当天日期] graph | 知识图谱已重建
