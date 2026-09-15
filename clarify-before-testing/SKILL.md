---
name: clarify-before-testing
description: Route and resume the current software-testing Run across business understanding, test design, execution planning, data preparation, runtime execution, defect/regression, and final review. 仅在用户正在开展一个具体测试任务、明确要求继续/恢复测试流程，或当前工作区已存在 Run 状态时使用；不要用于普通测试知识问答。Router 只负责识别当前 Run、当前阶段、人工确认和下一动作，不承担业务分析或测试执行。
---

# Clarify Before Testing｜测试流程路由

这个 Skill 是总路由，不是“总 Agent 大脑”。

它只解决五件事：

1. 当前是哪个测试 Run；
2. 当前 Run 处于哪个阶段；
3. 当前阶段应该加载哪个 Skill；
4. 哪些正式产物已经完成 AI 自审和人工确认；
5. 下一步真正应该做什么，以及中断后从哪里继续。

它**不负责**业务理解、测试点设计、用例生成、执行规划、数据准备、Case 执行、Bug 判断或最终质量结论。

---

# 1. 总流程

用户侧使用正常测试语言：

```text
业务理解
→ 等待业务理解确认
→ 测试点设计
→ 等待测试点确认
→ 测试用例生成
→ 等待测试用例确认
→ 执行规划
→ 等待执行方案确认
→ 当前 Batch 数据准备
→ 正式执行
→ 缺陷处理 / 等待修复 / 回归
→ 最终结果复核
→ 测试完成
```

内部阶段可以保持：

```text
business-modeling
case-design
execution-planning
data-readiness
execution-runtime
defect-handling
result-review
closed
```

不要向用户输出 Gate、Lease、Heartbeat、Control Plane、Resume Pack 等框架术语。

---

# 2. 首先判断当前 Run

进入任何阶段前，先检查是否已有当前 Run。

优先：

```bash
python clarify-before-testing/scripts/workflow_state.py discover --root work/test-runs
```

处理：

- 只有一个未关闭 Run：直接继续；
- 有多个未关闭 Run：根据当前任务名称、路径和最近更新时间选择；如果无法可靠判断，再让用户选择；
- 没有 Run：只有在用户正在开始具体测试任务时才创建；
- 已关闭 Run：不要默认重新打开，除非用户明确要求继续该 Run。

不要每次新会话都新建 Run。

---

# 3. Run 工作目录

统一：

```text
work/test-runs/RUN-xxx/
├─ deliverables/
│  ├─ 01-business-understanding.md
│  ├─ 02-test-points.md
│  ├─ 03-test-cases.md
│  ├─ 04-execution-plan.md
│  └─ 05-test-report.md
├─ dashboard/
├─ internal/
│  ├─ business/
│  ├─ design/
│  ├─ execution/
│  ├─ data/
│  ├─ defects/
│  ├─ coverage/
│  ├─ decisions/
│  └─ state/
├─ scripts/
│  ├─ api/
│  ├─ ui/
│  ├─ data/
│  └─ temp/
├─ evidence/
├─ logs/
├─ downloads/
└─ scratch/
```

用户正式阅读的产物只放 `deliverables/`。

内部追踪、稳定 ID、映射、状态和机器字段放 `internal/`。

临时脚本、临时文本、临时 DOM、临时响应不要散落在 Run 根目录。

---

# 4. 前半程人工确认是真实状态，不只是 Prompt

三个核心产物必须遵循：

```text
生成初稿
↓
AI 完整自审
↓
自行修订
↓
重新自审
↓
自审通过
↓
登记当前正式产物及摘要
↓
人工确认当前产物
↓
确认结果与该产物版本绑定
```

对应：

- `01-business-understanding.md`
- `02-test-points.md`
- `03-test-cases.md`

不能：

```text
刚生成文件
→ 直接 set flag
→ 进入下一阶段
```

产物发生修改后，旧确认不能自动沿用。重新自审，再重新确认受影响部分。

---

# 5. 后半程执行方案也必须确认

测试用例确认后：

```text
execution-planning
→ AI 自审执行方案
→ 用户确认执行方案
→ data-readiness
```

Runtime 不允许在执行过程中重新决定：

- UI / API / 人工主执行方式；
- Batch；
- Case 顺序；
- 证据策略；
- 是否录屏；
- Case 依赖。

这些属于 Planning。

---

# 6. 正常返回上游，不靠 Hook

如果执行过程中发现：

- Case 设计有问题；
- Planning 与系统实际冲突；
- 前置数据状态不对（当前批次数据需要异常打回）；
- 业务规则仍未确认；

显式返回对应阶段：

```text
execution-runtime → data-readiness
execution-runtime → execution-planning
execution-runtime → case-design
```

异常打回必须记录真实 `return_reason`。

**注意**：多批次正常循环推进（如 B1 完成后进入 `data-readiness` 为下一批次 B2 准备并绑定数据）属于正向批次流转，不属于异常回退，不需要填写 `return_reason`。

不要用 Stop Hook、PreToolUse Hook、Lease、Heartbeat 去阻止正常工作。

---

# 7. 中断恢复

恢复粒度：

```text
Run
→ Stage
→ Batch
→ Case
```

不做“点击步骤级恢复”。

如果一个 Case 执行中断：

1. 读取 `run-status.json`；
2. 确认 Batch / Case；
3. 重新检查当前测试数据状态；
4. 从该 Case 开头重新执行；
5. 不假设中断前最后一个 UI 点击一定成功。

详细见：

`references/decision-and-resume.md`

---

# 8. Router 的 next_action

`next_action` 表示“接下来该做什么”，不是“刚刚发生了什么”。

核心流转契约：

1. **多 Batch 准备与执行隔离**：
   B1 完成后，若有下一个无依赖的待执行批次 B2，系统给出的权威动作必须是：
   ```yaml
   next_action:
     type: prepare_batch_data
     batch_id: B2
   ```
   严禁跳过数据准备直接输出 `execute_batch`。只有当 B2 的 Data Manifest 在 `data-readiness` 阶段通过 `set-batch-data-ready` 验证并绑定后，`next_action` 才会变为 `execute_batch(B2)`。

2. **缺陷路由优先于结果复核**：
   只要存在 Reviewer 确认但尚未提交或关联 Bug 的产品 FAIL Case，严禁输出 `result_review` 或推进无关批次，权威动作必须是：
   ```yaml
   next_action:
     type: handle_defects
     batch_id: B1
     case_ids: [C01]
   ```
   缺陷提交并关联后，无依赖批次可继续 `prepare_batch_data`，有依赖批次等待修复。

3. **全部闭环后方可复核**：
   只有当所有批次均已执行完成、所有缺陷完成回归闭环（`PASS_AFTER_FIX`）、无未决异常时，权威动作才为：
   ```yaml
   next_action:
     type: result_review
   ```

---

# 9. Defect 不冻结整个 Run

确认产品 Bug 后：

- 受影响 Case / Batch 可以等待修复；
- 无依赖的其他 Batch 继续；
- Bug 修复后生成 Regression Task；
- 回归通过以后更新相关 Case；
- 再解除真正的下游依赖。

Router 只调度，不自行判断产品 Bug。

---

# 10. Final Review 与关闭 Run

不能手工把 `final_review_status` 写成 passed 就关闭 Run。

必须有真实 Final Review 产物，并由 `test-result-review/scripts/final_review.py` 校验。

使用：

```bash
python clarify-before-testing/scripts/workflow_state.py set-final-review \
  --state <run>/internal/state/run-status.json \
  --review-file <final-review-json>
```

只有真实复核产物绑定成功后，才允许 `result-review → closed`。

测试结论可以是：

- 测试完成，可进入下一阶段；
- 测试基本完成，但仍有风险；
- 不建议进入下一阶段；
- 测试未完成，当前无法形成完整质量结论。

“Run 已完成复核”不等于“产品质量通过”。

---

# 11. Router 读取哪个 Skill

| 当前工作 | Skill |
|---|---|
| 业务理解 | `test-business-modeling` |
| 测试点 + 测试用例 | `test-case-design` |
| 执行规划 | `test-execution-planning` |
| 当前 Batch 数据准备 | `test-data-readiness` |
| 正式执行 | `test-execution-runtime` |
| Bug 与回归 | `test-defect-handling` |
| 最终对账与报告 | `test-result-review` |

Router 只加载当前需要的 Skill，不一次性把所有 Skill 全部读入上下文。

---

# 12. 禁止事项

禁止：

- Router 自己做业务分析；
- Router 自己写测试点/用例；
- Hook 参与正确性；
- Lease / Heartbeat；
- 高频 checkpoint；
- 每个操作都更新状态；
- 只改 flag 不绑定真实产物；
- 一个局部阻塞冻结所有无关 Batch；
- 用户已提供的信息重复询问；
- 恢复时重新从业务理解第一步开始。

详细阶段转换和恢复规则见：

- `references/workflow-contract.md`
- `references/decision-and-resume.md`

# 13. 工程绑定要求

人工确认不是一个可手改的布尔值。

阶段产物进入“等待人工确认”前，Router 必须同时绑定：

- 用户可读正式产物；
- 对应内部 Contract 输入；
- 两者的 SHA-256；
- Contract 的真实校验结果。

`register-artifact --self-review-status passed` 会实际调用当前阶段 Contract；Contract 不通过时不能登记为自审通过。必要时使用 `--contract-input` 指向当前内部模型。

任何同类产物重新注册都会立即废除该产物以及受其影响的下游旧确认。确认后正式产物或内部 Contract 输入发生变化，也不能继续使用旧确认进入下一阶段。
