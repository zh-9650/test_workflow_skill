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
4. 哪些正式产物已经完成自审、问题处理和人工确认；
5. 下一步真正应该做什么，以及中断后从哪里继续。

它**不负责**业务理解、测试点设计、用例生成、执行规划、数据准备、Case 执行、Bug 判断或最终质量结论。

`case-design` 内部明确分成两个子阶段：

```text
test-point-design
→ 测试点自审
→ 人工确认
→ test-case-design
→ 用例自审
→ 人工确认
```

Router 根据当前已确认产物选择对应 Skill，不允许一个 Skill 同时重做两层。

---

# 1. 总流程

进入目标项目前，先检查 `test-project-bootstrap` 的项目 Profile、工作流版本和 `CLAUDE.md` 测试托管区块。缺失或漂移时先完成项目级 Bootstrap，再发现或创建 Run。Bootstrap 不写 `current_stage`，普通 Run 恢复不重复初始化。目标项目若尚未经用户授权，不运行 Bootstrap 修改该项目。

正式 Runtime 的 `next_action=execute_batch` 只授权主 Agent 组装任务和派独立 Execution Worker。Worker 自审后必须派新会话的 Result Reviewer；子 Agent 不可用时停在明确等待/阻塞状态，不能由主 Agent代跑。自动化 Case 的正式执行必须是最终 TypeScript 脚本运行。

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

不要向用户输出内部调度、控制、租约或状态机实现术语。人工文档统一使用“人工确认、进入下一阶段条件、结构校验、当前阶段、恢复信息”等正常测试语言。

---

# 2. 首先判断当前 Run

项目 Bootstrap 已完成且版本匹配后，再检查是否已有当前 Run。

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
│  ├─ 01-business-understanding-review.md
│  ├─ 02-test-points.md
│  ├─ 02-test-point-review.md
│  ├─ 03-test-cases.md
│  ├─ 03-test-case-review.md
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

用户正式阅读和确认的产物只放 `deliverables/`。

前半程每一阶段都必须遵循“**主文档 + 审查摘要 + 内部 JSON**”三层输出：

```text
业务理解：01-business-understanding.md + 01-business-understanding-review.md + business-model.json
测试点：02-test-points.md + 02-test-point-review.md + test-points.json
测试用例：03-test-cases.md + 03-test-case-review.md + test-cases.json
```

其中人工确认主要看两个 MD；JSON 是机器合同与追踪依据，不要求用户阅读。不得只生成 JSON 或只给内部摘要就要求用户确认。

内部追踪、稳定 ID、映射、状态和机器字段放 `internal/`。

临时脚本、临时文本、临时 DOM、临时响应不要散落在 Run 根目录。

---

# 4. 前半程人工确认是真实状态，不只是 Prompt

三个核心产物必须遵循：

```text
生成初稿
↓
完整自审并主动查漏补缺
↓
自行修订
↓
把当前可回答的待确认问题集中放到正式文档末尾
↓
如仍有问题：等待用户批量回复，不能进入下一阶段
↓
更新正式文档 + 内部模型 + 审查摘要
↓
重新自审与结构校验
↓
问题处理完成后提交人工最终确认
↓
确认结果与当前三份产物版本绑定
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


## 4.1 待确认问题默认集中处理

默认不要一个问题一轮对话。

前半程三个阶段都应把当前可回答的待确认问题集中放到对应正式文档末尾，并给出建议方案和推荐原因。用户可以一次性批量回复；Router 收到回复后，先让当前阶段 Skill 更新文档和结构化数据，再重新自审。

如果某个问题必须依赖前一个答案才能成立，只把它标记为依赖项，等前置结论回填后再刷新问题清单。

业务理解阶段负责业务规则确认；测试点或测试用例阶段发现业务 Expected 不明确时，必须返回业务理解，不在当前阶段代替产品做决定。

详细规范：

```text
references/human-review-and-confirmation.md
```

---

# 5. 后半程执行方案也必须确认

测试用例确认后：

```text
execution-planning
→ 执行方案自审
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

不要通过额外的拦截器、租约或心跳机制去阻止正常工作。

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

4. **回归解锁不等于下游通过**：
   Regression PASS 后，原 FAIL 可进入 `PASS_AFTER_FIX`；因该缺陷而 BLOCKED 的 Case 只能进入待恢复队列。Router 必须按 Batch 给出：
   ```yaml
   next_action:
     type: prepare_resumed_cases_data
     batch_id: B2
     case_ids: [C07, C08]
     bug_ref: BUG-123
   ```
   这些 Case 重新通过 `data-readiness → execution-runtime → Worker 自审 → Reviewer` 后才算闭环。不能在回归事件中直接把它们改为 PASS。

`current_stage` 只由 Router 的显式 transition 改变。Dashboard/Runtime/Defect 事件若声明了不同 Stage，必须拒绝，不能反向覆盖 Run Status。

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
| 测试点设计 | `test-point-design` |
| 测试用例设计 | `test-case-design` |
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
- 依赖额外拦截器保证正确性；
- 额外租约或心跳机制；
- 高频状态落点；
- 每个操作都更新状态；
- 只改 flag 不绑定真实产物；
- 一个局部阻塞冻结所有无关 Batch；
- 用户已提供的信息重复询问；
- 恢复时重新从业务理解第一步开始。

详细阶段转换和恢复规则见：

- `references/workflow-contract.md`
- `references/decision-and-resume.md`


# 13. 设计产物版本与失效

前半程正式依赖链固定：

```text
Business Model Version
        ↓
Test Point Design Version
        ↓
Test Case Design Version
```

要求：

- Test Point 必须声明其基于的 `business_model_version`；
- Test Case 必须声明其基于的 `test_point_version` 和 `business_model_version`；
- 上游正式产物重新注册后，下游确认立即失效；
- 不允许只改关联映射来伪装旧测试用例兼容新测试点；
- 如果只是下游执行数据变化，不应反向修改 Business Model 或 Test Point。

`case-design` 阶段的下一动作由确认状态决定：

```text
业务理解已确认 + 测试点未确认
→ design_test_points

测试点已确认 + 测试用例未确认
→ design_test_cases

测试用例已确认
→ plan_execution
```

---
# 14. 工程绑定要求

人工确认不是一个可手改的布尔值。

阶段产物进入“等待最终确认”前，流程必须同时绑定：

- 用户可读正式产物；
- 用户可读审查摘要；
- 对应内部结构化数据；
- 三者的 SHA-256；
- 当前阶段结构校验的真实结果。

`register-artifact --self-review-status passed` 会实际执行当前阶段结构校验。业务理解、测试点、测试用例还必须提供 `--review-path` 绑定审查摘要。

自审阶段允许存在“已明确记录、等待人工回复”的问题；这时产物可以登记为已自审，但下一动作只能是处理问题，不能最终确认。`confirm-artifact` 会再次执行更严格的最终确认校验，未解决的阻塞问题会直接拒绝确认。

任何同类产物重新注册都会立即废除该产物以及受其影响的下游旧确认。确认后正式产物、审查摘要或内部结构化数据任一发生变化，也不能继续使用旧确认进入下一阶段。
