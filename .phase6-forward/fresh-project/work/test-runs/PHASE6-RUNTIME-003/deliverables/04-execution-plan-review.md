# PHASE6-RUNTIME-003 — Execution Plan 候选自审

## 来源与完整性

- 已读取当前 Router `confirmation_bindings.test-cases.contract_path` 指向的 `internal/design/test-cases.json`，并验证该文件实时 SHA-256 与当前 Router `contract_sha256` 完全一致：`5633a350e74718d04754fd01d37e70594fb365f0173427a6f2de4ca34a928fcc`。
- 使用当前 `test-case-design/scripts/case_contract.py` 对绑定 Case、测试点和业务模型执行严格 Contract 验证，再调用 `project_execution_cases` 得到三条实例级规划 Case；不是手工猜测 Case ID。
- Plan 的 `confirmed_case_ids` 精确等于该 projection 的 Case ID 集合；`confirmed_cases_sha256` 绑定整个 Case Contract 文件，而非散列一个手编 Case 列表。
- 逐条核对投影的 `title / steps / expected_results / target_action / test_point_ids / preconditions / test_data` 原样进入 Plan；Expected 的 `checkpoint` 与适用的 `step_id` 也保持不变。执行层字段只增加 Batch、execution mode、dependency、data 和 evidence 设置。

## 执行方案检查

- 所有三条 Case 归属唯一 `B01`；无跨 Case 依赖，Batch `parallel_safe=false`，明确串行。
- API Case 使用 TypeScript + Vitest + Node native fetch；两个 UI Case 使用 TypeScript + Playwright Test。
- 每个自动化 Case 都预留确定的 Run-relative `.test.ts` / `.spec.ts` script target；该计划本身不声称脚本已经生成或运行。
- 三条 Case 的 `data_required=false` 与只读 fixture 基线相符；后续 Manifest 仍需通过 Data Readiness Contract 和 Router binding，不在这里伪造准备完成。
- API 脱敏请求/响应 evidence 映射到两个 API Expected；每条 Case 的 runner report 都作为 `files` evidence 并覆盖该 Case 全部 Expected。普通 UI 截图映射到可见结果 Expected；critical UI 截图映射到标题及结果 Expected，并要求 Case-level recording。
- 普通 UI Case 不要求录屏；critical UI Case 的录屏是证据要求，不是额外数据持久化或业务语义。

## Self-review 结论与边界

计划结构化 Contract 验证若通过，仅说明该候选正确绑定当前投影并满足 Planning schema。`user_confirmation.status` 仍为 `pending`；本自审不是用户确认。当前只生成候选文件，未注册 Plan artifact、未确认 Plan、未改 Router 状态，也未创建 Data Manifest。
