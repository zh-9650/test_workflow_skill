# Runtime Review Method

## Worker Self Review
`status=passed` 时必须同时确认：所有 Case、所有 Expected、执行方式、Evidence 绑定、异常分类、文件清理均已检查；`checked_case_ids` 必须覆盖当前 Task 全部 Case。

## Reviewer
Reviewer 独立检查完整性、执行方式一致性、Case 判定、Evidence、异常分类。`status=passed` 时上述 checks 全部必须为 true。

`rework_required` 只生成 `retest_case_ids` 对应的局部 Retest Task。Retest Result 使用和首次执行完全相同的 Case Result Contract；若 Retest Case 依赖未重跑 Case，必须把已知依赖结果带入 `dependency_context`。

`return_upstream` 必须给出 findings 和 `case_design | execution_planning | data_readiness` 之一。只有 Reviewer passed 才能 Batch completed。
