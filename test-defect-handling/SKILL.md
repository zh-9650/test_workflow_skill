---
name: test-defect-handling
description: Turn reviewer-confirmed product issues from Runtime into high-quality defects and close the fix/regression loop. 仅在 Runtime 已排除明显脚本、Locator、数据和环境问题且独立 Reviewer 确认疑似产品问题后使用。负责稳定复现、最小合法路径、重复 Bug 检查、同根因聚合、Bug 自审/提交、关联 Case/Batch、修复后的新 Regression Worker 及必要影响范围回归。
---

## 项目知识协作入口

处理具体项目工作前，读取 [项目知识读取与沉淀协议](../clarify-before-testing/references/project-knowledge-protocol.md)。该协议覆盖已有项目背景、非 Skill 材料接收、测试线选择和公共能力复用；本阶段职责仍由下文规定。


# Test Defect Handling｜缺陷与回归

定位：

> **把确认的产品问题变成高质量缺陷，并在开发修复后完成可信回归。**

Runtime 技术错误不进入本 Skill。

---

# 1. 入口

Runtime 已完成：

- 按真实主执行方式执行；
- 排除明显脚本/Locator；
- 排除数据问题；
- 排除明显环境问题；
- 复现关键异常；
- Reviewer 确认疑似产品问题。

然后才进入 Defect Handling。

---

# 2. 完整缺陷流程

```text
确认产品问题（来源：Runtime 执行失败 或 数据准备受阻）
↓
稳定复现
↓
提炼最小合法复现路径
↓
整理 Evidence
↓
检查是否已有 Bug（查重）
↓
判断多个 Case 是否同根因
↓
生成 Bug（支持已绑定的缺陷平台：禅道、Jira、GitLab、GitHub 等）
↓
AI 自审
↓
提交缺陷平台 / 关联已有 Bug
↓
Bug ↔ Case ↔ Batch 绑定
↓
判断真正受阻的 Case（标记 BLOCKED）
↓
无影响测试继续（生成阶段快照）
↓
开发修复并部署到目标环境 / 或 用户明确延期/无需修复处置
↓
[修复分支] 验证部署 → 新 Regression Worker → 原问题及影响回归 → 独立 Reviewer → 解锁受阻 Case
[处置分支] 用户明确延期/无需修复 → 记录处置理由/操作人/版本 → 移出待回归队列（保留风险，不改 PASS）
```

---

# 3. 最小合法复现

“最小”不是绕过业务前提。

保留所有真正业务必须条件，去掉无关步骤。

例如 Bug 出现在“已审核项目编辑限制”：

可以用 API 合法创建/提交/审核作为前置；

但不能直接改数据库 status 绕过状态机。

---

# 4. Duplicate Bug

正式提单前检查现有 Bug。

如果已经存在同根因 Bug：

- 不重复提；
- 关联现有 Bug；
- 关联本次 Case/Batch/Evidence。

状态应清楚表达“已有 Bug，未重复提交”，不要把它记成“提交失败”。

---

# 5. 同根因聚合

多个 Case 同根因：

```text
一个 Bug
→ 关联多个 Case
```

表现相似但根因不同：拆 Bug。

不要为了减少 Bug 数量强行合并。

---

# 6. Bug 内容

至少：

- 标题；
- 项目；
- 模块；
- 开发负责人；
- 严重程度/优先级；
- 环境；
- 前置条件；
- 复现步骤；
- Actual；
- Expected；
- 复现率；
- 关联 Case；
- Evidence。

---

# 7. Bug 自审

提交前检查：

- 真的是产品问题吗；
- Expected 有业务依据吗；
- 复现稳定吗；
- 最小路径是否合法；
- 是否已有 Bug；
- 是否同根因；
- 模块/开发是否正确；
- Evidence 是否足够；
- 是否泄露敏感信息；
- 严重程度是否合理。

---

# 8. Bug 只阻塞真实依赖范围

Bug 导致某条关键 Case FAIL：

- 依赖它的 Case 可 BLOCKED；
- 无依赖的其他 Batch 继续。

不要一个 Bug 把整个 Run 暂停。

---

# 9. 回归必须用新的 Worker

开发修复后：

```text
主 Agent
→ Regression Task
→ 新 Regression Worker
```

不要复用之前执行失败时已经很长的 Worker 上下文。

---

# 10. 回归范围

至少：

1. 原失败 Case；
2. 同业务相关场景；
3. 根据修复影响选择必要上下游 Case。

回归必须从原 Execution Planning 读取主执行方式并保持一致。

原 UI Case 不能为了方便回归成 API；不能靠 `preserve_primary_execution=true` 之类自报字段证明没有偷换。

---

# 11. 回归判定

Regression Task 中的**所有 Case**都必须通过，整次回归才算通过。

不允许：

```text
原失败 Case PASS
影响范围 Case FAIL
→ regression_passed=true
```

如果原问题修复但影响回归失败：

- 原问题可记录“现象已修”；
- 整次 regression 仍失败；
- 新失败按根因判断是否产生新 Bug；
- 不关闭完整回归闭环。

---

# 12. 历史必须保留

例如：

```yaml
initial_result: FAIL
bug_ref: BUG-123
regression_1: PASS
final_result: PASS_AFTER_FIX
```

不要把初始 FAIL 覆盖掉只剩最终 PASS。`initial_result=FAIL` 必须来自 Runtime 已经 Reviewer 确认的真实历史；Regression 不能自己补写一个从未发生过的 FAIL，也不能把原 PASS 直接改成 `PASS_AFTER_FIX`。

详细：

`references/defect-regression-method.md`

# 13. Defect / Regression 状态同步

正式 Bug / Regression 通过 `defect_contract.py --apply-run-dir <RUN>` 落账时，同时更新全局 Case Result Ledger 和 Dashboard。

Regression 仍必须：

- 使用新的 Regression Worker；
- Regression Runtime 必须由 Router/主 Agent通过 Runtime `regression-prepare` 创建正式 Task，再派独立 Worker、自审后派全新 Reviewer；禁止用 `worker_is_new` 等自报布尔值证明角色隔离；
- 保留原主执行方式；
- 完整覆盖原失败 Case + 已确定影响范围；
- Regression Contract 的 `runtime_evidence` 必须绑定当前 Run 中每个实际 Regression Runtime Task、Case 范围及 Worker/Reviewer receipts；Final Review 会重新核验脚本、结果、会话身份和复核输出；
- 整个 Regression Task 全部 PASS 后才允许写入 `PASS_AFTER_FIX` / PASS。

同一个 Regression 跨多个 Batch 时，每个 Batch 分别生成 Runtime Task，并通过相同的 `regression_id` 关联；某个 Batch 仅含影响 Case 时不必伪造初始 FAIL，但 Run 中必须有同一 Bug 关联的 Reviewer-confirmed 初始 FAIL。Regression Reviewer 要求局部重测时必须保留 `product_regression` 模式和 Bug/Regression 标识；结果未通过 Reviewer 前不得更改 Case Ledger。

Regression PASS 只更新本次 Regression Task 中实际执行且通过的原失败/影响 Case。因 Bug 而 BLOCKED、但未包含在 Regression Task 中的下游 Case，只能解除阻塞并进入恢复队列；Router 随后按 Batch 路由到 `data-readiness`，Runtime 重新执行并复核这些 Case。禁止把“依赖已修复”直接等同于“下游 Case 已通过”。

---

# 14. 用户明确延期 / 无需修复处置（Disposition）

当用户在修复沟通过程中明确表示某缺陷“延期修复”或“无需修复”时：
- 使用命令记录正式处置：
  ```bash
  python test-defect-handling/scripts/defect_contract.py \
    --input <disposition-payload.json> \
    --type disposition \
    --apply-run-dir <run-dir>
  ```
- 处置记录包含：`defect_id`、`disposition`（`postponed` 或 `wontfix`）、`operator`、`rationale`、`affected_case_ids`、`target_version`；
- **保留原始 FAIL / BLOCKED 事实，绝不篡改为 PASS**；
- 该缺陷移出当前 Run 待回归队列，不阻塞最终结案；
- 最终复核将受影响 Case 计入剩余风险范围，结论给出 `ready_with_risk`。
