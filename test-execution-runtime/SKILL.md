---
name: test-execution-runtime
description: 严格按已确认 Execution Plan 和当前 Batch Data Manifest 执行；由 Runtime Orchestrator 驱动主 Agent→Worker→Worker 自审→独立 Reviewer→局部补测/完成/回退上游。
---
# Test Execution Runtime

## 1. 入口
只接收：已确认 Execution Plan、当前 Batch、Data Manifest、Execution Context。已完成 Case 的最终结果由 Runtime 自动维护在 `internal/execution/results/case-results-ledger.json`，主 Agent 不再手工拼接跨 Batch `global-results`。Runtime 不重新决定执行方式、Batch、Expected 或证据要求。

文件模式的 `prepare` 会重新校验 Execution Plan 的自审/人工确认、Case↔Batch、依赖和 Evidence Plan，并初始化 Run Dashboard；不能把未确认或未校验的 Plan 直接交给 Worker。

Data Manifest 的 `readiness.ready` 不能靠 Agent 手填取得信任。Runtime Precheck 会再次调用 Data Contract，根据对象、状态、关联、read-back 等字段重新计算是否 ready；非法 Manifest 必须 `return_to_data`。

## 2. Runtime Orchestrator
`scripts/runtime_orchestrator.py` 维护 Batch：

```text
Batch Precheck
→ build Worker Task
→ pending/running
→ Worker Results
→ self_review
→ reviewing
→ completed | needs_rework | return_upstream | blocked
```

Worker Task 写入 `internal/execution/tasks/Bxx-task.json`。跨 Batch dependency 必须写入 `dependency_context`：当前 Batch 内依赖读取 Worker Results，跨 Batch 依赖由 Runtime 自动读取全局 Case 结果账本。只有 Reviewer 通过后的最终结果才写入账本；Regression 通过后原失败 Case 写为 `PASS_AFTER_FIX`、影响范围 Case 写为 `PASS`。上游 FAIL/BLOCKED/其他未通过状态时，下游必须 `BLOCKED(upstream_case)`。

## 3. Worker Result
默认 `1 Batch = 1 Execution Worker`，Batch 内串行。Worker 可以调整 Locator、等待、滚动、弹窗、非验证导航、浏览器恢复、脚本 Bug 和辅助查询；禁止修改 `primary_execution`、Expected、Case 目标、关键业务步骤、Case/Batch 范围和测试数据含义。

提交结果前先检查：
- Case ID 不得重复；
- 不得遗漏 Planned Case；
- 不得多出未计划 Case；
- 每条结果都必须过 `execution_control.validate()`。

## 4. Case Result Contract
每个 Expected 必须有具体 `actual/result/evidence_refs`。证据确实不需要时，只能使用 Planning 已声明的 `evidence_not_required + reason`。

- PASS：所有 Expected 为 pass。
- FAIL：只能是 `reason_type=product_issue`，有 Expected/Actual/Evidence，并已复现或明确说明复现不适用。
- BLOCKED：必须有允许的阻塞类型、原因和 `affected_by`；Locator/脚本错误不能长期 BLOCKED。
- NEEDS_REVIEW：必须有 review reason 和 `required_action`。

`actual_execution` 必须等于 Planning 的 `primary_execution`。辅助 API/数据库等只属于 supporting observations。

## 5. Worker 自审与 Reviewer
Worker `status=passed` 不能裸通过。必须同时有固定 checks：Case、Expected、执行方式、证据绑定、异常分类、文件清理均已检查。Reviewer `status=passed` 也必须有完整性、方式一致性、判断、证据、异常分类 checks 全部为 true。

只有 Worker Self Review passed 后才能进入 Reviewer；只有 Reviewer passed 才能 Batch completed。只要当前 Batch 仍存在 `NEEDS_REVIEW`，Reviewer 就禁止 `passed`，必须先局部补测或返回上游处理。

## 6. Retest
Reviewer `rework_required` 只生成 `retest_case_ids` 对应的局部任务，不整 Batch 重跑。Retest：

```text
retest task
→ retest results
→ 同一个 Case Result Contract
→ retest self-review
→ retest reviewer
→ completed / 再次局部补测 / return upstream
```

文件模式必须持久化 Task、Results、自审、Reviewer 状态。若补测 Case 依赖未重跑 Case，Retest Task 必须携带这些依赖的已知结果作为 `dependency_context`。

## 7. Dashboard 与 Run State
Planning 确认后一次性把全部 Planned Case 初始化为 PENDING，所以总进度始终是 `completed_cases / planned_total_cases`。Batch 级录屏按 Batch ID 映射，Case 级录屏按 Case ID 映射。Dashboard 展示：Batch 进度、Core Flow、规划/实际执行方式、Recording、BLOCKED、Bug、当前 Worker/Reviewer/动作，并每 3 秒读取 `dashboard-data.json`。Reviewer 或 Batch 完成后必须清空旧的 `current_case/current_worker/current_reviewer`。

`dashboard_update.py` 是 Runtime/Defect/Regression 共用的状态事件更新入口，同时维护 `run-status.json` 与 Dashboard。文件式 Runtime 接收结果、进入复核、完成复核和补测时会自动写入这些事件；不要依赖 Agent 额外手工补事件。`last_event` 表示刚发生的事，`current_action` 表示当前动作，`next_action` 表示真实下一步；可运行的下一 Batch 会按跨 Batch dependency 自动筛选。

Dashboard 不建议直接用 `file://` 打开。使用标准库本地 HTTP：`python test-execution-runtime/scripts/dashboard_server.py --run-dir work/test-runs/RUN-xxx --port 8765`，然后访问命令输出的 `http://127.0.0.1:8765/`。

## 8. 证据与恢复
按 `evidence/Bxx/TCxxx/{ui,api,network,debug,files,bug}/` 归档。录屏、截图、API/Network、下载文件完全服从 Planning。恢复只到 Case/Batch 边界；执行中断时从当前 Case 开头重跑，不保存点击级 checkpoint。
