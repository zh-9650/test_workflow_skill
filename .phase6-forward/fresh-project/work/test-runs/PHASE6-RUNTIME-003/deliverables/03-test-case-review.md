# PHASE6-RUNTIME-003 — 测试用例自审摘要

## 审查结论

内部结构化设计含 **3 个用例主项、3 个独立执行场景/数据组**，全部为 P1；参数化用例 0 个，多测试点共用用例主项 0 个。失败后数据一致性、恢复、并发、旧状态及长流程专项均为 0 个，因为冻结范围只有只读 fixture 观察，不引入这些业务机制。

所有已确认测试点均有实际执行场景和明确断言；当前 JSON 中逐步检查点与步骤的显式绑定如下：

| 测试点 | 独立执行场景 | 断言覆盖 |
|---|---|---|
| `TP-API-EXACT-ITEM` | `TC-P6-API-001` / `INS-P6-API-001` | `ASSERT-P6-API-STATUS-001` 在 `STEP-P6-API-001` 检查 HTTP 200；`ASSERT-P6-API-BODY-001` 在 final 检查精确 JSON（含 `id` 为字符串） |
| `TP-UI-VISIBLE-ITEM` | `TC-P6-UI-001` / `INS-P6-UI-001`；`TC-P6-UI-002` / `INS-P6-UI-002` | `TC-P6-UI-001` 在 final 精确检查可见结果；`TC-P6-UI-002` 将标题断言绑定至 `STEP-P6-UI-002-HEADING`，并在 final 检查结果 |

## 结构化证据策略

逐 Case 核对当前 Case JSON 中结构化 `evidence_policy` 的类型、断言关联与录屏门槛：

| Case | 等级与录屏 | 必需证据及断言映射 |
|---|---|---|
| `TC-P6-API-001` | `standard`；`recording_required=false` | 脱敏 `request_response` 与 `runner_report`，均覆盖 `ASSERT-P6-API-STATUS-001`、`ASSERT-P6-API-BODY-001` |
| `TC-P6-UI-001` | `standard`；`recording_required=false` | `screenshot` 与 `runner_report`，均覆盖 `ASSERT-P6-UI-RESULT-001` |
| `TC-P6-UI-002` | `critical`；`recording_required=true` | `screenshot` 与 `runner_report`，均覆盖 `ASSERT-P6-UI-002-HEADING`、`ASSERT-P6-UI-002-RESULT`；另须保留非空 Playwright video |

两条 UI Case 的截图均需关联相应断言；API 的 request/response 必须脱敏。`TC-P6-UI-002` 的录屏门槛属于冻结验收基线证据要求，不是新增业务预期。

## 展开与遮蔽检查

- API 测试点展开为一个普通 Case 和一个执行场景：基线只规定一个固定只读 GET 响应，无等价类或边界组可展开。
- UI 测试点由普通 UI smoke 与结构化策略为 `critical` 的独立验收场景分别执行。第二条 UI Case 的 heading 是独立、可观察断言；视频是冻结验收基线中的证据要求，不作为额外业务预期。Case `case_type` 字段仍为 `ordinary`；critical 在此明确描述 `evidence_policy.level`，两者含义不同。两条 UI Case 不合并，因此不存在多测试点合并或前序断言失败遮蔽其他机制的问题。
- 两个 UI 场景代表不同的验收/证据配置，不伪装成参数化数据，也未增加新的业务测试点。
- 用例期望逐项限定为冻结 fixture 的 HTTP 状态、完整 JSON、页面标题及可见文本；未添加持久化、真实产品生命周期、权限或写入断言。

## 边界与后续门槛

fixture 的功能预期没有新增待澄清项。展示文档中的逐步断言与结构化证据策略对应当前 Case JSON；真实业务语义、生命周期、权限及持久化仍明确处于本 Run 范围之外。

`test_cases_self_review.status=passed` 仅表示本轮结构与覆盖自审通过；它不等于 Router artifact 注册或用户对用例的正式确认。后续应先按 Router 流程注册本文件、审查摘要和 JSON 并满足结构校验，再由有权确认者完成 Case 确认后进入执行计划。
