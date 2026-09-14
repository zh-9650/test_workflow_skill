# Defect / Regression Method

正式缺陷来自 Reviewer 已确认的 `product_issue`。提交前完成重复检查；已有 Bug 使用 `not_submitted_existing` 并关联 `existing_bug_ref`，新 Bug 只有拿到真实 `bug_ref` 才算 submitted。

Regression Task 必须包含真实 `cases`、`original_case_ids`、`impact_case_ids`，使用新 Worker，并保持原 `primary_execution`。Regression Result 直接复用 Runtime `execution_control.validate()`，所以 UI→API 偷换、Expected/Actual/Evidence 缺失都会失败。

PASS_AFTER_FIX 只允许来自：initial FAIL → Bug → Regression Worker → 原 Case Regression PASS → 最终 PASS_AFTER_FIX。
