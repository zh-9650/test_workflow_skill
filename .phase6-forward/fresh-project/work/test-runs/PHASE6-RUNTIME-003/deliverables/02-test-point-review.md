# PHASE6-RUNTIME-003 — 测试点候选自审

## 审查结论

`internal/design/test-points.json` 的两个测试点均保持 `TEST_BASELINE` 来源状态，只覆盖当前隔离 fixture 的只读观察：

1. `TP-API-EXACT-ITEM`：HTTP 状态及完整 JSON 响应精确匹配。
2. `TP-UI-VISIBLE-ITEM`：点击加载后可见结果精确匹配。

它们分别对应模型里的 `EV-API-ITEM-LOOKUP` 与 `EV-UI-ITEM-LOOKUP`，每个事件都有 `event_behavior` 覆盖义务和反向 Case 映射。模型中的失败条件还要求覆盖失败原子性/负向规则类型；由于这些事件没有业务写入，对应原子性义务明确为 `out_of_scope`，而不是遗漏，也不将技术/环境失败升级成产品缺陷。

## 粒度与证据审查

- API 与 UI 是不同的可观察机制，保留为两个 atomic 测试点。
- Critical UI 的标题断言、关键截图和非空视频在 UI 测试点范围说明中记录为该 Case 的附加断言/证据要求；它们不代表新的持久化或业务结果。
- 两个测试点均未引入业务模型以外的对象、事件或期望；没有多测试点共享覆盖，也无需按数据实例拆分。
- `design_questions` 当前为空，因为此候选严格限于冻结 fixture baseline。真实业务语义、生命周期、权限与持久化的不确定性仍按业务模型 `UNK-REAL-BUSINESS-SEMANTICS` 保持在 out-of-scope，不在测试点阶段擅自回答。

## 非目标与确认状态

本候选不覆盖或确认真实系统的写入、关系、授权、状态迁移、并发、恢复、跨模块效果或持久化规则。Contract 自审只证明候选结构与当前模型一致，不是用户确认。

本文为人工可读自审材料。尚未调用 Router 的 `register-artifact` / `confirm-artifact`，也未修改任何 Router stage 或 Run 状态。
