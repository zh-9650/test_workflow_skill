# PHASE6-RUNTIME-003 — Item Lookup 测试点候选

> **状态与边界：**以下是基于隔离 smoke fixture 的测试点候选，来源类型为 `TEST_BASELINE`。它们不是已确认的真实业务需求，也不表示 Router 已注册或确认测试点。

## 测试点

| ID | 覆盖行为 | 机制与期望 | 范围/证据说明 |
| --- | --- | --- | --- |
| `TP-API-EXACT-ITEM` | API Item Lookup | 对 `GET /api/items/1` 检查 HTTP 200，并精确比较 `{ "id": "1", "name": "Smoke item", "status": "ready" }`；`id` 必须是字符串。 | 只读 fixture 观察；不推断生产语义或持久化。 |
| `TP-UI-VISIBLE-ITEM` | UI Item Lookup | 点击 `Load item` 后，断言可见 `#result` 精确等于 `Smoke item — ready`。 | Critical UI Case 对同一可见结果额外检查 `Item lookup` 标题，并按冻结验收要求保存关键截图和非空视频。这些是该 Case 的断言/证据要求，不是额外业务行为，也不构成持久化承诺。 |

## 覆盖说明

- 两个模型事件分别由一个原子测试点覆盖：API 完整响应与 UI 可见结果是不同的观察机制，因此不合并。
- 模型列出的只读失败情况仍需在未来 Runtime 中按实际证据分类；此候选不把 endpoint 不可用或 UI 观察失败直接定性为产品缺陷。
- 读写原子性在该只读 fixture 中为 `out_of_scope`，并非声称真实产品没有写入规则。
- 未设计创建/修改/删除、关系维护、授权、状态迁移、持久化、并发、恢复、跨模块或长流程测试点；这些不属于本冻结 smoke 范围。

## 来源

业务模型及来源审阅：`internal/business/business-model.json`、`internal/business/business-model-review.md`；人工范围说明：`deliverables/01-business-understanding.md`。冻结 Case 基线：`PHASE6-CLAUDE-001` acceptance task。历史 fixture 运行材料只作为历史观察，不代表本次 Runtime 的环境 readiness。
