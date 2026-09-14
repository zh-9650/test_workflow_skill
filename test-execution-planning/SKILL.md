---
name: test-execution-planning
description: 测试用例人工确认后的后半程第一阶段；提前决定每条 Case 的主执行方式、Batch、依赖、并发、数据需求与证据计划，并用 Contract 阻止不一致规划。
---
# Test Execution Planning

## 1. 入口
仅在测试点、测试用例均已自审并人工确认后进入。先复用已有环境、账号、接口、源码和脚本信息，再补真正缺失的执行上下文。密码/Token 只进 `.test-secrets.env`。

## 2. Case 执行定义
每条 Case 必须声明：
- `primary_execution`: UI | API | 人工。
- `supporting_observations`: 仅辅助验证，不替代主执行。
- `batch_id` 与 `dependencies`。
- `evidence_plan`: screenshots / recording / api / network / files。

UI Case 不允许主执行偷换 API；API Case 不允许因为 UI 更方便而临时改入口。

## 3. Batch 和依赖
按业务链、共享状态、角色、数据生命周期和上下文划 Batch。Case↔Batch 必须双向一致且唯一；dependency 必须引用真实 Case，禁止自依赖、循环依赖以及依赖项排在更晚 Batch。

## 4. Evidence Plan
UI 至少规划截图或录屏，确实不需要必须写 waiver；API 至少规划 request/response；下载类必须规划文件证据。录屏要求显式 `required + scope(batch|case)`。

## 5. 输出
- `deliverables/04-execution-plan.md`
- `internal/execution/execution-plan.json`
- 初始化 `dashboard/dashboard-data.json` 与 `dashboard/index.html`

## 6. 完成条件
先自审，再人工确认。将 `deliverables/04-execution-plan.md` 和 `internal/execution/execution-plan.json` 登记为 `execution_plan` Artifact，并确认文件未发生变化；只有 `self_review.status=passed` 且 `user_confirmation.status=confirmed` 的 Plan 才允许进入 Data Readiness。详细方法见 `references/execution-planning-method.md`。
