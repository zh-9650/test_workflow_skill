# PHASE6-RUNTIME-003 — Execution Plan 候选

> **状态：待确认。**本计划仅针对用户授权的仓库内隔离 fixture smoke，不代表真实业务系统验证。计划中的三条 Runtime Case 来自当前已确认 `test-cases.json` 的 Contract projection；所有确认 Case 字段须原样保持。

## 执行批次

| Batch | 顺序与 Case | 执行方式 | 数据策略 | 证据 |
| --- | --- | --- | --- | --- |
| `B01` | 串行：`TC-P6-API-001` → `TC-P6-UI-001` → `TC-P6-UI-002` | API：TypeScript + Vitest + Node 原生 `fetch`；UI：TypeScript + Playwright Test | 三条 Case 均 `data_required=false`；后续 Manifest 只声明不需要创建或绑定 mutable business data。 | API 脱敏 request/response；普通 UI 关键结果截图；critical UI 关键截图与该 Case 的非空录屏。每条 Case 的正式 runner report 都作为 `files` evidence，并映射该 Case 的全部 Expected。 |

该 Batch 标为 `parallel_safe=false`，按表中顺序执行，不并行。此方案针对只读 fixture smoke，不涉及准备真实业务数据或对真实项目写入。

## Case 级执行约束

- `TC-P6-API-001`：正式 TypeScript + Vitest 脚本通过 Node native `fetch` 请求固定 fixture 路径，校验 HTTP 200、完整 JSON 及字符串型 `id`。脱敏 request/response 映射两个 Expected；runner report 作为 `files` evidence 映射该 Case 全部 Expected。
- `TC-P6-UI-001`：正式 TypeScript + Playwright Test 脚本点击 `Load item`，断言可见 `#result` 精确文本，并保存映射到该 Expected 的关键截图；runner report 作为 `files` evidence 映射该 Case 全部 Expected。
- `TC-P6-UI-002`：正式 TypeScript + Playwright Test 脚本先验证 `Item lookup` 标题，再点击并验证结果；保存映射标题与结果 Expected 的关键截图，并录制本 Case 的非空视频；runner report 作为 `files` evidence 映射该 Case 全部 Expected。
- 所有 Case 第一次正式执行前必须已经有最终 TypeScript 脚本。任何临时交互不能替代正式脚本运行。
- 不将 smoke fixture 的结果推断为刷新持久性、真实业务语义或产品缺陷。

## Case Contract 来源绑定

`internal/execution/execution-plan.json` 的 `confirmed_cases_sha256` 绑定当前 Router 已确认的完整 Case Contract 输入文件 SHA-256（`5633a350e74718d04754fd01d37e70594fb365f0173427a6f2de4ca34a928fcc`）。规划 Case 集合由 Case Contract projection 确定；本计划不编辑源 Cases。Contract 校验要求确认字段 `steps / expected_results / target_action / test_point_ids / preconditions / test_data` 与 projection 完全相同，其中 Expected 的 `checkpoint` 和 `step_id` 也原样保留。

## 确认状态

本文件及结构化 Plan 都处于候选/待确认状态。Self-review 只检查投影字段、执行栈、串行 Batch、数据策略与证据映射，不代表对本 Execution Plan 的用户确认。只有 Router 的合法 artifact 注册和确认流程完成后，才可进入 Data Readiness。
