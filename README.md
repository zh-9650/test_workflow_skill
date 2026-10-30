# 测试 Skill

## 设计阶段定向优化（2026-10-19）

针对现场暴露的状态、输入处理和配置未生效风险，补充业务理解的真实完成条件、测试点的不一致风险，以及用例的具体数据/触发动作/判定基准。新增只读静态筛查辅助定位场景名称型数据与空泛步骤；筛查结果不代替语义审查或产品执行。

修改范围为仓库内三个设计 Skill，未同步安装目录，未改变执行合同。验证和已有业务设计样例见 [本轮记录](docs/verification/2026-10-19-design-improvement.md)。真实执行可信度与历史 PASS 证据仍需另行核查。

## 当前交付检查点（2026-10-07）

Codex 上的三 Batch 隔离正常链已经实际跑通：正式 API/UI 脚本 → 独立 Worker 执行与自审 → 新独立 Reviewer → 阶段快照 → 最终报告 → 官方关闭。同一 Run 保留了首次失败、审查退回、恢复及技术补测记录。这不是仅离线单测，但也不代表整个 Skill 已全部验收。

本次整理提交包含前向执行暴露的定向修补、对应测试和[精简验收记录](docs/verification/2026-10-06-normal-chain.md)。完整原始证据保留在本地 `.verification-forward/20261004/`，不随源码上传；用户 ZIP 与被忽略的唯一验收计划也保持本地不变。

尚未验收：合法业务造数与数据准备产品 Bug、产品修复部署及多轮回归、BLOCKED 恢复与延期处置、新主聊天恢复、Claude 等另一宿主实际派发、正式 Jev 外发与费用核对。全局 Skill 未同步。

## 历史仓库修补检查点（2026-09-30）

以下保留当时的验证结果与边界；当前正常链的新增证据见上方检查点，历史数字不是当前测试统计。

唯一验收依据仍是本地 `新版测试Skill改造计划.md`，该文件被 Git 忽略但真实存在。以下仅说明当前源码验证，不取代真实宿主前向验收或历史记录。

本轮从 `8d5dfce687e281917f8329c9102e6d8d3edaf7df` 修补：执行契约升级 v3 并拒绝 v2；Planning 数据需求与 Data Manifest 逐项对账、账号/权限/秘密引用绑定；部署事件冻结并贯穿新 Batch、回归和 BLOCKED 恢复；用户延期/无需修复保留 FAIL/BLOCKED；数据准备 Bug 保留 BLOCKED 历史后首次执行；Jev 正式脚本调用封装、审批/外发字段/跨 Case 预算/原始证据/独立判断门禁；最终报告呈现各轮与实际验证版本，关闭前再次对账。删除了硬编码真实项目、关闭 TLS 验证并可推送远端的 `sync_case_repo.py`，可从 Git 恢复，未执行外部同步。

### 实际验证与证据

在仓库根目录运行：

- `python -m pytest -q`：150 passed、2 skipped（Windows 符号链接权限 WinError 1314），包含真实本地 Vitest API / Playwright UI runner smoke。
- `node --test test-project-bootstrap/scripts/tests/jev-adapter.test.mjs`：7 passed，全部 mock fetch，无付费请求。
- 编译 framework 到临时目录后设置 `JEV_RUNTIME_MODULE=<编译输出>/jev-runtime.js`，运行 `node --test test-project-bootstrap/scripts/tests/jev-runtime.test.mjs`：4 passed，覆盖跨 Case Run 预算、外发字段、未知费用和 evidence junction 拒绝。
- TypeScript `tsc --project <临时副本>/tsconfig.json --noEmit false --rootDir <临时副本>/framework --outDir <临时副本>/build`：exit 0。依赖复用 `.phase6-forward/fresh-project/work/test-automation/node_modules`，未下载或更改全局目录。临时目录：`C:/Users/17381/AppData/Local/Temp/skill-typecheck-f3720f9738c641079a50001d5e45ecd9`。
- `git diff --check`：通过（只有 CRLF 转换提示）。
- 对本轮修改的 5 个 SKILL.md 运行 `python -X utf8 <skill-creator>/scripts/quick_validate.py <Skill目录>`：全部 valid；不带 UTF-8 的初次调用遇到 GBK 解码错误，重试通过，未修改全局 Skill。

本地 runner smoke 证据保留在 `.phase6-forward/fresh-project/work/test-runs/RUN-SMOKE-0e00c128880b/`：正式脚本 `scripts/api/B01/TC-API-001.test.ts`、`scripts/ui/B01/TC-UI-002.spec.ts`；`runner-results/` 原始 Runner 报告；`evidence/` 脱敏 HTTP 结果、刷新后截图、webm 录屏。该 Run 的派发 receipt 明确是合成 scope 输入，**不是宿主真实派发验收**。跨 Batch 账本测试也只在临时副本中生成 v3 合成契约，原始 Phase 5 历史夹具未改写。

| Phase | 当前证实边界 |
| --- | --- |
| 0 | 已证实源码基线与 dirty 状态；未把未跟踪 zip 或被忽略计划归为本轮交付 |
| 1 | Bootstrap 原有本地测试通过；多宿主真实发现/加载仍未验证 |
| 2 | Planning v3 正反例通过；真实项目人工确认链仍未验证 |
| 3 | 数据分类/账号/权限/证据契约通过；真实产品合法造数与准备 Bug 复验仍未验证 |
| 4 | Runtime/Reviewer 契约与隔离 runner smoke 通过；真实宿主派发顺序未验收 |
| 5 | Bug/跨 Batch 回归/处置/版本与准备恢复单元 seam 通过；完整准备 Bug 修复及多轮部署前向仍未验收 |
| 6 | Final Review 门禁和版本报告单元测试通过；新 v3 Run 到唯一报告关闭的宿主前向仍未验收 |
| 7 | 未授权同步，未操作全局 Skill 或真实业务项目 |
| 8 | Jev 离线 mock/类型检查通过；实网费用核对、冻结标签集 shadow 指标、正式 Case 前向未验证 |

### 尚需的前向验收

运行新的隔离 v3 Run，真实主 Agent 派 Worker、等待完成及自审后再派新 Reviewer，保存宿主调用/任务/完成记录；覆盖数据准备产品 Bug、部署修复、数据重验、首次 Runtime、多 Batch 多轮回归、旧 PASS 影响、恢复 BLOCKED、新聊天恢复与最终报告关闭。Claude 等其他宿主只能由该宿主实际验收，不能用 Codex 或合成 JSON 替代。

真实 Jev 请求仍须用户单独确认环境、外发字段、费用上限。官方响应没有可核对金额时，封装保存 usage 后拒绝生成正式调用结果，尚需真实账单证据核对路径，不能估零或凭连通性宣布通过。独立 Spec/Standards 审查发现的问题已作定向修补；最后一次新准备恢复分支的独立复审因 Agent 额度中断，不能写成复审全通过。

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
