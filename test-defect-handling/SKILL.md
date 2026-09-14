---
name: test-defect-handling
description: 对 Reviewer 已确认的真实产品问题做重复检查、缺陷提交、Case/Batch 关联与独立回归，并保留 FAIL→Bug→Regression→最终结果完整历史。
---
# Test Defect Handling

## 1. 入口
只有 Runtime 已排除脚本/Locator/数据/明显环境问题，且 Reviewer 确认产品问题后才能正式进入。

## 2. Defect Contract
必须有来源 Case/Batch、`reviewer_confirmed=true`、重复检查、根因分组、完整 payload、自审和 submission。

- 新 Bug：只有 `submission.status=submitted` 且拿到真实 `bug_ref` 才算完成。
- 已有 Bug：必须 `duplicate_check.result=existing + existing_bug_ref`，submission 使用 `not_submitted_existing`，并关联原 Bug；不能伪装成“提交失败”，也不能重复新建。

## 3. Regression
Regression Task 使用新的 Worker，并携带原始计划快照 `baseline_cases`；必须保持原 `primary_execution`、Expected ID 及 Expected 文本映射，至少包含原失败 Case 和受影响 Case。每个 Regression Result 直接复用 Runtime 的 `execution_control.validate()`：执行方式、Expected、Actual、Evidence、Status 与正式执行完全同一标准。

因此 `worker_is_new=true`、`preserve_primary_execution=true` 只是必要元数据，不能代替真实结果。Regression 是否通过必须同时检查原失败 Case 和全部 `impact_case_ids`；任一影响范围 Case 未 PASS，整个 Regression 都不能判通过。只有完整回归范围全部 PASS 后，原失败 Case 才有资格形成 PASS_AFTER_FIX。

## 4. 状态联动
Bug 提交、等待修复、回归完成通过统一事件更新器同步到 `run-status.json` 和 Dashboard。完整 Regression PASS 后，同时回写 Runtime 的全局 Case 结果账本：原失败 Case=`PASS_AFTER_FIX`，影响范围 Case=`PASS`；之后跨 Batch dependency 自动使用新状态恢复受影响业务链。

## 5. 历史
最终 PASS_AFTER_FIX 必须可追溯：initial FAIL → bug_ref → regression record(PASS) → final PASS_AFTER_FIX。详细规则见 `references/defect-regression-method.md`。
