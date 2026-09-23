# 测试 Skill

这套 Skill 正按 [`新版测试Skill改造计划.md`](新版测试Skill改造计划.md) 升级。项目接入先完成一次 Bootstrap；每个测试 Run 再按 9 个阶段 Skill 流转。

```text
项目 Bootstrap（首次接入或版本漂移时）
→ 读取项目测试索引
业务理解
→ AI 自审
→ 人工确认
→ 测试点设计
→ AI 自审
→ 人工确认
→ 测试用例
→ AI 自审
→ 人工确认
→ 执行规划
→ AI 自审
→ 人工确认
→ 当前 Batch 数据准备
→ Batch Worker 正式执行
→ Worker 自审
→ 独立 Reviewer
→ 缺陷 / 回归
→ 被回归解锁的 BLOCKED Case 重新校验本 Batch 数据并恢复执行
→ 最终结果复核
```

## 1 个项目 Bootstrap + 9 个 Run Skill

`test-project-bootstrap`：仅管理指定项目的测试入口托管区块、项目测试索引/Profile、Claude Worker/Reviewer 定义和 TypeScript 公共骨架，不写 Run 阶段状态。

Run 内依次使用：

1. `clarify-before-testing`：Run / 阶段 / 确认 / 恢复路由
2. `test-business-modeling`：业务理解
3. `test-point-design`：业务机制级测试点设计
4. `test-case-design`：测试用例设计
5. `test-execution-planning`：执行方式、Batch、依赖、Evidence 规划
6. `test-data-readiness`：当前 Batch 前置数据准备
7. `test-execution-runtime`：Batch 执行、Evidence、自审、Reviewer、局部补测
8. `test-defect-handling`：Bug 与 Regression
9. `test-result-review`：最终对账与测试报告

## 核心原则

- 正式文档面向测试人员，机器追踪放 `internal/`。
- AI 自审未通过，不进入人工确认。
- 人工确认由 Router 的版本绑定记录，不依赖各阶段 JSON 自报 `confirmed=true`。
- 已确认 Case 是 Planning 的事实源；Planning 不能改步骤、Expected、测试目标和测试数据语义。
- UI/API 主执行方式由 Planning 决定，Runtime 与 Regression 都不能偷换。
- API 自动化固定使用 TypeScript + Vitest + Node 原生 fetch；UI 自动化固定使用 TypeScript + Playwright Test。首次执行也先写脚本，再正式运行最终脚本。
- 主 Agent 只编排 Batch：实际派独立 Execution Worker，Worker 完成并自审后再派新的 Result Reviewer；缺少子 Agent 能力时停止，不自演。
- Case 结果按 `Expected → Actual → Evidence → Result` 判断；脚本成功不等于 PASS。
- Evidence 必须属于当前 Run / Batch / Case，不能拿任意旧文件或 Run 外文件充数。
- 技术执行错误不等于产品 FAIL。
- 局部补测只更新受影响 Case，不覆盖整个 Batch 已完成的审查事实。
- `FAIL → Bug → Regression → PASS_AFTER_FIX` 的历史由事实账本产生，Regression 不能伪造初始 FAIL。
- 每个 Batch 都单独经过数据校验与绑定；完成 B1 不会让 B2 自动获得执行资格。
- 回归只解除真实依赖，原 BLOCKED Case 仍需重新校验数据、正式执行、自审和 Reviewer，不能直接改成 PASS。
- 阶段只能由 Router 改变；Runtime、Dashboard 和缺陷事件只能同步事实，不能自行跳阶段。
- Run Status、Case Ledger、Dashboard 和 Final Review 使用同一执行事实，不各自维护互相矛盾的结果。
- 不依赖 Hook / Lease / Heartbeat / 复杂 Resume Pack。

## 最终包结构

发布包包含 1 个项目 Bootstrap Skill 与 9 个 Run Skill。当前仓库的计划与 `tests/` 是开发和验收资料，不属于目标项目的测试数据；缓存文件和旧执行兼容层不应进入发布包。

工程 Contract 用来拦关键旁路，但 Skill 是否可用仍应以真实前向流程验证为准：正常主流程、局部补测、产品 Bug 与影响回归、中断恢复、最终关闭等。
