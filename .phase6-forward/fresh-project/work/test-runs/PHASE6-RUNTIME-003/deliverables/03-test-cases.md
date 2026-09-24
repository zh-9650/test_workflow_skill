# PHASE6-RUNTIME-003 — 冻结 Fixture Smoke 测试用例

> **范围与状态：**本文件只把已确认的隔离 fixture smoke 测试基线展开为三条独立执行 Case。所有预期均来自冻结的 `PHASE6-CLAUDE-001/acceptance-task.md`，来源仍是 `TEST_BASELINE`；不代表新增或确认真实产品业务规则。结构自审通过不等于本阶段已由 Router 注册或由用户确认。

## TC-P6-API-001 — API Item Lookup 返回冻结的精确响应

- 优先级：P1
- 关联测试点：`TP-API-EXACT-ITEM`
- 执行方式：TypeScript + Vitest + Node 原生 `fetch`
- 前置条件：隔离 fixture endpoint 在本 Batch 可访问；仅使用冻结 fixture 基线。
- 执行数据组：固定请求 `GET /api/items/1`。

| 步骤 | 操作 | 逐步预期 |
|---|---|---|
| `STEP-P6-API-001` | 由正式 TypeScript/Vitest 脚本向隔离 fixture 发送 `GET /api/items/1`。 | `ASSERT-P6-API-STATUS-001`（step，绑定本步骤）：HTTP 状态码精确为 `200`。 |
| 最终 | 完成本次响应检查。 | `ASSERT-P6-API-BODY-001`（final）：完整 JSON 精确为 `{"id":"1","name":"Smoke item","status":"ready"}`，其中 `id` 为 JSON 字符串。 |

结构化证据策略：`level=standard`、不要求录屏；必须提供脱敏 `request_response`（覆盖本 Case 的状态码与响应体断言）及 `runner_report`（Vitest 正式运行报告）。

## TC-P6-UI-001 — UI Item Lookup 显示冻结的条目结果

- 优先级：P1
- 关联测试点：`TP-UI-VISIBLE-ITEM`
- 执行方式：TypeScript + Playwright Test
- 前置条件：隔离 fixture Item lookup 页面可访问并提供 `Load item` 按钮；不检查刷新持久化。
- 执行数据组：点击一次 `Load item`。

| 步骤 | 操作 | 逐步预期 |
|---|---|---|
| `STEP-P6-UI-001` | 由正式 TypeScript/Playwright Test 脚本打开隔离 fixture Item lookup 页面并点击 `Load item`。 | `ASSERT-P6-UI-RESULT-001`（final）：可见 `#result` 文本精确等于 `Smoke item — ready`。 |

结构化证据策略：`level=standard`、不要求录屏；必须提供覆盖 `ASSERT-P6-UI-RESULT-001` 的结果截图及本 Case 的 Playwright `runner_report`。

## TC-P6-UI-002 — Critical UI Item Lookup 检查标题、结果并录制视频

- 优先级：P1
- 关联测试点：`TP-UI-VISIBLE-ITEM`
- 执行方式：TypeScript + Playwright Test（critical）
- 前置条件：隔离 fixture Item lookup 页面可访问并提供 `Item lookup` 标题及 `Load item` 按钮；不作刷新持久化主张。
- 执行数据组：先检查标题，再点击一次 `Load item`。

| 步骤 | 操作 | 逐步预期 |
|---|---|---|
| `STEP-P6-UI-002-HEADING` | 打开隔离 fixture Item lookup 页面。 | `ASSERT-P6-UI-002-HEADING`（step，绑定本步骤）：点击前 `Item lookup` 标题可见。 |
| `STEP-P6-UI-002-LOAD` | 点击 `Load item`。 | `ASSERT-P6-UI-002-RESULT`（final）：可见 `#result` 文本精确等于 `Smoke item — ready`。 |

结构化证据策略：`level=critical`、`recording_required=true`；必须提供同时覆盖标题与结果断言的截图、本 Case 的 Playwright `runner_report`，以及非空 Playwright video。标题断言对应点击前检查；结果断言对应点击后的最终可见文本。此证据门槛不增加业务状态或持久化承诺。

## 待确认问题与建议

当前无需要人工确认的测试用例设计问题。本阶段仍须按正式流程登记并完成 Router Case 确认；当前结构自审本身不代表用户确认。
