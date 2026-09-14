---
name: test-result-review
description: 对整个 Run 做最终 Case/Batch/Bug/BLOCKED/执行方式/证据/回归对账，并由结构化数据推导最终质量结论。
---
# Test Result Review

## 1. Case 与 Batch 对账
正式用例 Case 集、Planning Case 集、最终结果 Case 集必须完全一致。所有 Planned Batch 都必须有最终 Batch Result，且 Batch=completed。

最终复核输入必须同时带已确认的 `planned_cases`、完整 `batch_results` 和每条 Case 的完整结果；不能只提交一个摘要 JSON。复核脚本会重新调用 Runtime Case Contract，并在提供 Run 目录时检查 Evidence 文件真实存在。

Worker Self Review 和 Reviewer 不能只写 `status=passed`：最终复核会再次检查固定 mandatory checks 全部为 true。

## 2. 规划 vs 实际
逐 Case 检查 planned primary execution 与 actual execution；规划录屏/文件等 Evidence 必须有真实产物。最终 Run 不允许非最终 Case 状态。

## 3. FAIL / BLOCKED / PASS_AFTER_FIX
- `FAIL` 永远代表 unresolved，过程字段 `fixed=true` 不参与最终质量判断。
- `BLOCKED` 必须有真实原因。
- `PASS_AFTER_FIX` 必须有 initial FAIL、bug_ref，以及带 regression_id/worker_id/executed_at 的真实 PASS 回归记录。

`PASS_AFTER_FIX` 还必须附带完整 Regression 记录；复核脚本会重新检查原失败 Case、影响范围 Case、原始执行方式和 Expected 映射。

因此不存在 `FAIL + fixed=true → ready` 的绕过路径。

## 4. Final Assessment
脚本从数据推导：coverage_complete、core_flow_passed、unresolved_critical_defects、blocked_scope、regression_complete，以及 `ready | ready_with_risk | not_recommended | incomplete`。Critical/Major 未解决 FAIL 会阻止 ready。

## 5. 输出
生成并校验 `deliverables/05-test-report.md` 对应的结构化复核结果，再用 Router 的 `record-final-review` 登记校验结果；不能直接把 `final_review_status` 写成 passed。正式报告只能映射 `final_assessment.conclusion`，不能接受 Agent 自由填写最终结论。
