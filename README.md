# 测试 Skill

这套 Skill 按已经确认的“前半程改造指导 + 后半程改造指导”实施，目标是让 AI 更接近真实资深测试人员的工作方式，而不是继续扩展工作流框架。

```text
业务理解
→ AI 自审
→ 人工确认
→ 测试点设计
→ AI 自审
→ 人工确认
→ 测试用例
→ AI 自审
→ 人工确认
→ 执行规划（绑定目标环境、缺陷平台、Jev 策略与证据等级）
→ AI 自审
→ 人工确认
→ 当前 Batch 数据准备（API 优先、真实 actor/秘密引用、读回验证）
→ Batch Worker 正式执行（TypeScript 脚本驱动，禁止临时点页面）
→ Worker 自审
→ 独立 Reviewer
→ 阶段快照 / 缺陷处理（双来源）/ 等待修复部署 / 多轮回归 / 用户处置
→ 被回归解锁的 BLOCKED Case 重新校验本 Batch 数据并恢复执行
→ 最终结果复核与唯一测试报告
```

## 项目入口与 9 个流程 Skill

`test-project-bootstrap` 是项目级前置入口：安全维护 Claude 的 `CLAUDE.md` 与 Codex 的 `AGENTS.md` 托管区块，初始化共享项目测试索引与 TypeScript 自动化骨架；它不是 Run 阶段。随后由 Router 在以下 9 个流程 Skill 间路由：

1. `clarify-before-testing`：Run / 阶段 / 确认 / 恢复路由 / 阶段快照 / 等待状态
2. `test-business-modeling`：业务理解
3. `test-point-design`：业务机制级测试点设计
4. `test-case-design`：测试用例设计
5. `test-execution-planning`：执行方式（API: Vitest+Node fetch; UI: Playwright Test）、Batch、依赖、Jev 策略与 Evidence 规划
6. `test-data-readiness`：当前 Batch 前置数据准备、对象回读与准备阶段缺陷识别
7. `test-execution-runtime`：Batch 执行、证据、自审、独立 Reviewer、局部补测
8. `test-defect-handling`：双来源 Bug（执行失败/数据准备）、缺陷平台绑定、多轮回归与用户延期/无需修复处置
9. `test-result-review`：最终对账、版本一致性与最终质量报告

## 核心原则

- 正式文档面向测试人员，机器追踪放 `internal/`。
- 自动化 Case 必须先写 TypeScript 脚本，再由脚本运行；禁止把临时 AI 点页面当正式执行。
- API 自动化统一 `TypeScript + Vitest + Node.js 原生 fetch`；UI 自动化统一 `TypeScript + Playwright Test`。
- 每个 Batch 必须由独立 Execution Worker 执行，再由独立 Result Reviewer 复核；主 Agent 仅做编排，子 Agent 不可用时进入等待状态，绝不代跑。
- Jev 策略在 Planning 预先确定（`required | conditional | none`，有界候选/语义），仅在预写脚本的 Runtime 执行，不写脚本、不生成任意动作、不单独决定 PASS。
- 数据准备阶段确诊的产品 Bug 记录 `source_kind="data_readiness"`，受影响 Case 标记为 BLOCKED，绝不伪造未发生的 Runtime FAIL。
- 所有首轮 Batch 复核后生成阶段快照，不关闭 Run；初测后有缺陷进入等待修复，修复部署到环境后才组织新 Worker 回归。
- 用户明确延期/无需修复（`postponed`/`wontfix`）记录正式处置并移出待回归队列，保留原始失败/未测事实与风险，不伪造 PASS。
- 最终复核只有在无待回归、待恢复、未处置 Bug 时才可进行；有合法 BLOCKED 时 `coverage_complete=false`。最终报告唯一且冻结。
- 不保留旧执行契约兼容层。
