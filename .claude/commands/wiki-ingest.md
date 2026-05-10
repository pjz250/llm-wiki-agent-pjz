把一份原始文档收录到知识维基中。

用法：/wiki-ingest $参数

$参数 应该是 raw/ 目录下的文件路径，例如 `raw/articles/my-article.md`

严格按照 CLAUDE.md 中定义的收录工作流执行：
1. 读取指定路径的原始文件
2. 读取 wiki/index.md 和 wiki/overview.md 了解当前上下文
3. 创建 wiki/sources/<slug>.md（使用 CLAUDE.md 中规定的资料页格式）
4. 更新 wiki/index.md —— 在"资料"分类下添加新条目
5. 更新 wiki/overview.md —— 如果新资料补充了重要知识，修改综合概述
6. 创建/更新实体页（wiki/entities/）—— 关键人物、公司、项目等
7. 创建/更新概念页（wiki/concepts/）—— 关键思想、框架等
8. 标记与新资料矛盾的已有知识
9. 追加日志到 wiki/log.md：## [当天日期] ingest | <标题>

完成所有写入后，总结：新增了什么、创建/更新了哪些页面、发现了哪些矛盾。
