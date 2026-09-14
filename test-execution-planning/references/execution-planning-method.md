# 执行规划方法

执行规划的职责是把所有会影响正式执行的决定前置，并形成可机器校验的 `execution-plan.json`。

## Case 级必填
- `case_id` 与唯一 `batch_id`，Batch 侧 `case_ids` 必须反向包含该 Case。
- `primary_execution`: `UI | API | 人工`。
- `supporting_observations`: UI/API/数据库只读/Network/日志/文件/其他系统。
- `dependencies`: 只能引用真实 Case；禁止自依赖、循环依赖以及“依赖项在更晚 Batch 执行”。
- `evidence_plan`: 显式包含 `screenshots/recording/api/network/files`。不能用空对象占位。

## Evidence 约束
UI Case 至少规划截图或录屏，确实不需要时必须写 `waiver_reason`。API Case 至少规划 request/response 证据。下载类 Case 必须规划文件证据。录屏使用：

```yaml
recording:
  required: true
  scope: batch | case
```

## Batch
Batch 按业务链、状态依赖、共享数据、角色、执行方式和破坏性操作划分。`parallel_safe` 必须显式布尔值。默认 UI 与共享状态 Batch 串行。

## 完成条件
`self_review.status=passed` 且 `user_confirmation.status=confirmed` 后，计划才允许进入 Data Readiness。
