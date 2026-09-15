# 疑似缺陷交接模板

Runtime 只交接“已排除明显执行技术问题、Reviewer 认为可能为产品问题”的结果。

至少包含：

- Batch；
- Case；
- 主执行方式；
- 前置数据；
- Expected；
- Actual；
- 最小复现步骤；
- Evidence；
- 已排除的技术原因；
- 是否影响其他 Case。

正式 Bug 由 `test-defect-handling` 处理。
