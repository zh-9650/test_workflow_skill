<USER_REQUEST>
## 审查结论

**未通过验收，当前版本不能宣布“新版测试 Skill 改造完成”，也不应进入全局 Skill 覆盖同步。**

已经证实的局部能力包括 Bootstrap 安全写入框架、TypeScript 自动化骨架、API/UI runner、脚本与报告 Hash 校验，以及一部分 Worker/Reviewer 合约。但从 Data Readiness 到最终报告的主闭环仍有多处阻断，其中当前 Final Review 甚至无法关闭一个全 PASS Run。

本次仅做只读审查和安全验证，未修改或清理任何仓库文件，未调用 Jev，未操作真实业务系统。

## 按严重度排序的问题

### P0-1：全 PASS Run 的 Final Review 必然崩溃

文件：[final_review.py:284](</C:/Users/17381/Desktop/测试全流程skill/test-result-review/scripts/final_review.py:284>)

实际证据：

- `derive_assessment()` 只给“有严重失败”和“有普通 FAIL/BLOCKED”设置 `conclusion`，全 PASS 时没有 `else`，随后在 [第 292 行](</C:/Users/17381/Desktop/测试全流程skill/test-result-review/scripts/final_review.py:292>)读取未赋值变量。
- 直接调用复现为：
  `UnboundLocalError: cannot access local variable 'conclusion'`
- 用当前代码重新复核历史 `PHASE5-FORWARD-004`，同样在此处退出码 1。计划中的历史“Final Review ok=true”因此不是当前 checkout 的通过证据。
- 现有 68 条通过测试没有覆盖这个最基本的全 PASS 路径。

违反计划：计划要求无待办时生成唯一最终报告并关闭 Run，而当前最理想的全 PASS Run 反而不能完成。

影响：所有成功闭环都无法正式结束；Phase 5、Phase 6 和最终完成定义均被直接阻断。

最小修正方向：补齐明确的 `ready` 分支，并增加至少四类真实 Final Review 测试：全 PASS、PASS_AFTER_FIX、带合法 BLOCKED、带未处置动作；必须重新用当前代码复核完整 Run。

---

### P0-2：Jev 仅停留在 Planning/Adapter 零散代码，Runtime 与 Final Review 没有接通

文件：

- [execution_plan.py:65](</C:/Users/17381/Desktop/测试全流程skill/test-execution-planning/scripts/execution_plan.py:65>)
- [execution_control.py:249](</C:/Users/17381/Desktop/测试全流程skill/test-execution-runtime/scripts/execution_control.py:249>)
- [final_review.py:294](</C:/Users/17381/Desktop/测试全流程skill/test-result-review/scripts/final_review.py:294>)
- [jev-adapter.ts:108](</C:/Users/17381/Desktop/测试全流程skill/test-project-bootstrap/assets/typescript-runtime/framework/jev-adapter.ts:108>)

实际证据：

- Planning 文档规定 UI 使用 `ui_candidate_revalidation`：[SKILL.md:445](</C:/Users/17381/Desktop/测试全流程skill/test-execution-planning/SKILL.md:445>)；验证器却只接受 `ui_candidate_selection`：[execution_plan.py:78](</C:/Users/17381/Desktop/测试全流程skill/test-execution-planning/scripts/execution_plan.py:78>)。按文档构造策略实测被验证器拒绝。
- 策略只做到 Case 级对象，没有按步骤/Expected 表达完整的调用次数、最大输入、证据、不调用原因和弃答约束。
- Runtime 的正式结果校验完整覆盖脚本、Runner、Evidence，却完全不读取 `jev_policy`。因此 `required` 未调用仍可能 PASS。
- Final Review 也没有对账 Jev 调用、不调用原因、预算、输入摘要或 Reviewer 独立判断。
- Adapter 明确写着“移除预算检查”：[jev-adapter.ts:120](</C:/Users/17381/Desktop/测试全流程skill/test-project-bootstrap/assets/typescript-runtime/framework/jev-adapter.ts:120>)、[jev-adapter.ts:265](</C:/Users/17381/Desktop/测试全流程skill/test-project-bootstrap/assets/typescript-runtime/framework/jev-adapter.ts:265>)。
- Adapter 允许任意非 TypeSafe endpoint 走备用 payload：[jev-adapter.ts:122](</C:/Users/17381/Desktop/测试全流程skill/test-project-bootstrap/assets/typescript-runtime/framework/jev-adapter.ts:122>)；只检查候选 ID 非空/唯一，没有在调用前拒绝隐藏或禁用候选，也没有 freshness、页面归属和操作前重验。
- 响应通过无上限 `res.text()` 读取，[置信度](</C:/Users/17381/Desktop/测试全流程skill/test-project-bootstrap/assets/typescript-runtime/framework/jev-adapter.ts:221>)也没有有限数值和 `[0,1]` 校验。
- 搜索不到正式 Jev 请求/响应、费用或用户批准证据；研究 Manifest 仍明确记录预算和冻结等待确认。

违反计划：直接违反计划 2.3、Phase 8.1–8.5 以及“required 未调用不得 PASS、固定 TypeSafe、预算触顶即停、Jev 不独立判 PASS”。

影响：当前 Jev 路径既不可审计，也可能绕过费用、供应商和 PASS 门禁。

最小修正方向：先统一 Planning schema，再将策略固化到 Worker Task、Runtime Result、Reviewer Result 和 Final Review；Adapter 必须拒绝计划外调用、固定 endpoint/model、执行调用前预算门禁、响应大小限制、脱敏和 UI 候选重验。真实请求仍须用户另行批准。

---

### P0-3：Data Readiness → Bug → Final Review 合同互相不兼容

文件：

- [data_manifest.py:80](</C:/Users/17381/Desktop/测试全流程skill/test-data-readiness/scripts/data_manifest.py:80>)
- [defect_contract.py:276](</C:/Users/17381/Desktop/测试全流程skill/test-defect-handling/scripts/defect_contract.py:276>)
- [final_review.py:363](</C:/Users/17381/Desktop/测试全流程skill/test-result-review/scripts/final_review.py:363>)

实际证据：

- Planning 已声明 `base_resource / batch_dedicated / runtime_generated`，但 Data Manifest 仍消费旧的 Case `data_required`：[data_manifest.py:85](</C:/Users/17381/Desktop/测试全流程skill/test-data-readiness/scripts/data_manifest.py:85>)。
- Manifest 不强制数据类别、actor、secret 引用、作用域/所有权/版本、创建尝试；且仍接受 `creation.implementation="direct"`：[data_manifest.py:115](</C:/Users/17381/Desktop/测试全流程skill/test-data-readiness/scripts/data_manifest.py:115>)。
- 数据准备 Bug 分支可把 PENDING/NOT_EXECUTED 直接改成 BLOCKED，并自行设置 `reviewer_confirmed=true`：[defect_contract.py:282](</C:/Users/17381/Desktop/测试全流程skill/test-defect-handling/scripts/defect_contract.py:282>)。没有核验独立 Reviewer receipt、任务或审查产物。
- Final Review 又要求每个计划 Batch 都存在 `completed` Runtime state、Task、Worker Result 和 Worker/Reviewer receipt：[final_review.py:363](</C:/Users/17381/Desktop/测试全流程skill/test-result-review/scripts/final_review.py:363>)；普通 BLOCKED 也要求完整 `runtime_result`：[final_review.py:422](</C:/Users/17381/Desktop/测试全流程skill/test-result-review/scripts/final_review.py:422>)。

违反计划：计划明确要求数据准备阶段 Bug 不伪造 Runtime FAIL/Task，独立复核后可作为正式 BLOCKED，并允许 Final Review 按“执行结果或正式受阻处置”对账。

影响：合法的数据准备 BLOCKED 无法关闭 Run；实现者只能伪造 Runtime 或永远无法通过 Final Review。

最小修正方向：新增独立的 Data Readiness Review 合同和 receipt；Manifest 消费 Planning 的正式数据需求；Final Review 为 `source_kind=data_readiness` 建立无需 Runtime 的严格分支。

---

### P0-4：延期/无需修复处置路径必然失败，而且会先写账本再失败

文件：

- [defect_contract.py:389](</C:/Users/17381/Desktop/测试全流程skill/test-defect-handling/scripts/defect_contract.py:389>)
- [dashboard_update.py:137](</C:/Users/17381/Desktop/测试全流程skill/test-execution-runtime/scripts/dashboard_update.py:137>)
- [workflow_state.py:456](</C:/Users/17381/Desktop/测试全流程skill/clarify-before-testing/scripts/workflow_state.py:456>)

实际证据：

- `apply_disposition_to_ledger()` 在 [第 412 行](</C:/Users/17381/Desktop/测试全流程skill/test-defect-handling/scripts/defect_contract.py:412>)先落盘账本，再发送 `defect_disposition_applied`。
- Dashboard 不支持此事件，未知事件在 [dashboard_update.py:179](</C:/Users/17381/Desktop/测试全流程skill/test-execution-runtime/scripts/dashboard_update.py:179>)直接抛错。
- 直接调用该事件已复现：
  `AssertionError: event.type: unsupported defect_disposition_applied`
- Router 只有在上述调用成功后才移除 open defect，因此实际会留下“Ledger 已变、Dashboard/Run State 未变”的部分提交状态。

违反计划：用户明确延期/无需修复应一次正式记录并移出待回归队列，同时保留 FAIL/BLOCKED 和风险。

影响：用户处置不能完成，Run 无法可靠结束，且会产生跨账本不一致。

最小修正方向：增加正式 Dashboard 事件语义，并把 Ledger、Dashboard、Run State 改成先全量校验、后原子提交；补失败回滚和幂等测试。

---

### P1-1：不存在可核验的部署版本事件和旧 PASS 影响评估

文件：

- [execution_plan.py:105](</C:/Users/17381/Desktop/测试全流程skill/test-execution-planning/scripts/execution_plan.py:105>)
- [defect_contract.py:195](</C:/Users/17381/Desktop/测试全流程skill/test-defect-handling/scripts/defect_contract.py:195>)
- [final_review.py:284](</C:/Users/17381/Desktop/测试全流程skill/test-result-review/scripts/final_review.py:284>)

实际证据：

- Planning 只保存初始版本。
- Router 只有字符串状态 `waiting_for_fix_deployment`，没有“部署已核验”的环境、版本、证据和时间事件。
- Regression Contract 的必填字段中没有目标环境、部署版本或部署核验引用。
- `derive_assessment()` 把 `regression_complete` 固定写成 `True`：[final_review.py:292](</C:/Users/17381/Desktop/测试全流程skill/test-result-review/scripts/final_review.py:292>)。
- Final Review 没有校验旧 PASS 是否受新部署影响，也没有核对每轮回归实际版本。

违反计划：缺陷平台“已修复”不等于目标环境已部署；每次部署必须评估旧 PASS 和数据重验，最终报告必须面向最新版本。

影响：可能在旧版本或未部署环境做回归，并把旧 PASS 错报为最新版质量结论。

最小修正方向：建立 Router 独占的 deployment event，记录环境、版本、核验方式和证据 Hash；Regression Task/Result 必须绑定该事件；显式保存旧 PASS 影响决策和数据重验结果。

---

### P1-2：“不保留旧契约兼容层”没有落实

文件：

- [execution_plan.py:175](</C:/Users/17381/Desktop/测试全流程skill/test-execution-planning/scripts/execution_plan.py:175>)
- [execution_plan.py:301](</C:/Users/17381/Desktop/测试全流程skill/test-execution-planning/scripts/execution_plan.py:301>)
- [final_review.py:344](</C:/Users/17381/Desktop/测试全流程skill/test-result-review/scripts/final_review.py:344>)

实际证据：

- Planning 的程序接口默认 `require_context=False`。
- CLI 仍提供 `--allow-legacy-context`。
- Final Review 调用 Planning 验证时没有开启 `require_context=True`。
- 缺少新 `run_context / target_environment / defect_platform / jev_policy` 的历史 Phase 5 Plan，使用当前 Final Review 仍能一直进入最终结论计算，说明旧结构没有在入口被拒绝。

违反计划：计划第 2.6 节明确要求验证器只接受新结构，不保留 fallback。

影响：旧 Plan 可混入当前 Runtime/Final Review，当前新增规则无法保证贯穿消费者。

最小修正方向：升级 schema 版本，删除 legacy 参数，默认且强制新上下文；所有程序调用者显式使用同一个严格验证入口，并加入旧 fixture 必须失败的测试。

---

### P1-3：阶段快照没有“所有首轮 Batch 已复核”的门禁

文件：[workflow_state.py:424](</C:/Users/17381/Desktop/测试全流程skill/clarify-before-testing/scripts/workflow_state.py:424>)

实际证据：

- `create_stage_snapshot()` 在任何阶段都可调用，只是读取现有 Ledger/Plan 后写快照。
- 没有核对所有 Case 是否已有 Reviewer 结果或独立复核的数据准备阻塞。
- `--output` 也没有限制在当前 Run 目录内。

违反计划：阶段快照只能在全部首轮 Case 已有经复核执行/受阻结论后生成，且不能冒充最终结果。

影响：可在 PENDING、Worker 运行中或 Reviewer 尚未完成时生成看似正式的初测快照。

最小修正方向：从冻结 Plan、Ledger、Runtime/Data Review receipts 重新计算资格；输出路径限制在当前 Run 的 deliverables，并增加提前调用负向测试。

---

### P1-4：Bug 提交失败会继续发出“bug_submitted”，甚至写入空 Bug ID

文件：

- [defect_contract.py:40](</C:/Users/17381/Desktop/测试全流程skill/test-defect-handling/scripts/defect_contract.py:40>)
- [defect_contract.py:340](</C:/Users/17381/Desktop/测试全流程skill/test-defect-handling/scripts/defect_contract.py:340>)
- [dashboard_update.py:148](</C:/Users/17381/Desktop/测试全流程skill/test-execution-runtime/scripts/dashboard_update.py:148>)

实际证据：

- 新 Bug 允许 `submission.status="failed"` 且没有 `bug_ref`。
- 随后仍更新 Ledger，并发出 `bug_submitted`。
- Dashboard 会将该空引用作为 submitted defect，并把 Batch 标成等待修复。

违反计划：提交失败不得产生虚假 Bug 引用或清空待办。

影响：Bug 实际未建立，但 Run 可能进入等待修复或错误推进状态。

最小修正方向：失败提交保持显式 `submission_pending/failed` 待办，禁止写 `bug_ref`、禁止发 `bug_submitted`，仅成功提交或明确 existing link 才能更新缺陷关联。

---

### P2-1：Bootstrap 局部实现较好，但机器 Profile 尚不足，且整个目录仍未跟踪

文件：

- [bootstrap_project.py:358](</C:/Users/17381/Desktop/测试全流程skill/test-project-bootstrap/scripts/bootstrap_project.py:358>)
- [bootstrap_project.py:393](</C:/Users/17381/Desktop/测试全流程skill/test-project-bootstrap/scripts/bootstrap_project.py:393>)
- [.gitignore:7](</C:/Users/17381/Desktop/测试全流程skill/.gitignore:7>)

实际证据：

- 安全预检、双入口托管块和保留项目内容的实现是成立的；Bootstrap 测试为 `14 passed, 2 skipped`。
- 但 Profile 的缺陷平台机器字段只有 `default_type/supported/mapping_ready`，没有能力、字段映射、非敏感默认值和凭据引用的正式结构。
- `test-project-bootstrap/` 整体仍是未跟踪文件；其 `scripts/tests/` 又被通用 `tests/` 规则忽略。
- Execution Planning 文档仍写死“禅道项目/模块/开发负责人映射”：[SKILL.md:65](</C:/Users/17381/Desktop/测试全流程skill/test-execution-planning/SKILL.md:65>)。

影响：本地能跑不等于交付可复现；通用缺陷平台设计仍有硬编码和缺失机器配置。

最小修正方向：完善 Profile schema，移除通用流程的禅道硬编码；确保 Bootstrap 源码和测试被正式纳入交付。

---

### P2-2：现有测试全绿不能覆盖当前关键断点，部分测试仍被忽略/未跟踪

实际证据：

- `pytest --collect-only`：71 条。
- 排除会改写固定历史目录的 live smoke 后：`68 passed, 2 skipped`。
- Planning：`6 passed`；Bootstrap：`14 passed, 2 skipped`。
- 两项 Skip 都是 Windows 无符号链接权限。
- 测试未发现全 PASS Final Review 崩溃、处置事件不支持、Data Readiness 正式 BLOCKED 无法 Final Review、Jev Runtime 未消费等问题。
- `.gitignore` 仍忽略 Planning 和 Bootstrap 的 tests。
- live smoke 测试会固定删除并重建 `.phase6-forward/.../RUN-LIVE-VERIFIED-001`：[test_live_smoke_execution.py:88](</C:/Users/17381/Desktop/测试全流程skill/test-execution-runtime/scripts/tests/test_live_smoke_execution.py:88>)，因此本次没有直接执行它。

影响：绿色测试结果显著高估完成度，并且无法保证换 checkout 后仍包含测试。

最小修正方向：把 smoke 改成 `tmp_path` 或唯一临时目录；补齐上述闭环负向/正向测试并纳入 Git。

---

### P2-3：未跟踪 scratch 中存在可直接发起付费/真实页面操作的脚本

文件：

- [test_jev_live.mjs:1](</C:/Users/17381/Desktop/测试全流程skill/scratch/test_jev_live.mjs:1>)
- [test_jev_live.mjs:6](</C:/Users/17381/Desktop/测试全流程skill/scratch/test_jev_live.mjs:6>)
- [run_live_audit_test.mjs:102](</C:/Users/17381/Desktop/测试全流程skill/scratch/run_live_audit_test.mjs:102>)

实际证据：

- `test_jev_live.mjs` 会请求 TypeSafe API，并打印 API Key 前 10 个字符。
- 另有脚本通过 CDP 连接真实 Chrome，并执行页面点击。
- 这些文件均未跟踪；无法可靠判断作者、是否属于正式交付或此前是否执行过。
- 本次没有运行它们，也没有读取任何秘密值。

影响：误执行可能产生费用、泄露密钥片段或操作真实项目；也不能作为正式 Jev/Runtime 证据。

最小修正方向：经文件所有者确认后从正式交付隔离；需要保留时改成显式 opt-in、默认 mock、禁止输出任何密钥片段，并绑定批准记录和预算门禁。

## Git 与历史证据边界

- 当前 `HEAD` 与 `origin/main` 同为 `e330af66e59808b7de730183632dd2bb870b4857`。
- 当前有 21 个已跟踪文件修改，约 `906 insertions / 173 deletions`，以及多个未跟踪目录。
- 计划文件真实存在但被 [.gitignore:16](</C:/Users/17381/Desktop/测试全流程skill/.gitignore:16>)忽略。
- 我只能确认：

  - HEAD 以前的提交属于已提交历史基线；
  - 当前 tracked diff 是候选开发改动；
  - `.phase*`、`.real-execution`、research、scratch 和未跟踪 tests 是本地材料。

- 无法仅凭 Git 状态确认每个未跟踪文件由哪位 Agent 创建，因此没有猜测归属。
- 两个辅助审查 Agent 均因额度限制失败，没有产出审查内容，本报告没有把它们算作独立证据。

## Phase 0–8 状态

| Phase | 状态 | 审查结论 |
|---|---|---|
| Phase 0 冻结基线 | 部分通过 | Git、版本和历史边界可识别，但仍有 legacy 入口，新增关键场景测试也不完整。 |
| Phase 1 Bootstrap | 部分通过 | 双入口和安全预检代码、14 条测试成立；机器 Profile 不完整，目录未跟踪，两宿主新会话发现性未前向验证。 |
| Phase 2 Planning V2 | 阻塞 | Jev 文档/验证器冲突，策略非逐步骤，Data/凭据约束不足，程序入口仍接受旧上下文。 |
| Phase 3 TypeScript 骨架 | 已证实通过 | 当前 18 个骨架文件与 `.phase6-forward` 副本 Hash 全部一致；`tsc --noEmit` 通过；历史合成 API/UI 报告和脚本 Hash 均匹配，critical UI 有视频。此结论仅限骨架和隔离 smoke。 |
| Phase 4 Runtime/Agent 隔离 | 部分通过 | Task/receipt/session/hash 合约和历史产物较完整；但当前聊天无法核验历史宿主真实调用序列，不能只靠 JSON session ID 验收。 |
| Phase 5 跨阶段闭环 | 阻塞 | Data Readiness Bug、用户处置、部署版本、阶段快照、BLOCKED 最终复核及全 PASS Final Review 均有阻断。 |
| Phase 6 独立前向验收 | 阻塞 | Codex 有历史 baseline 候选；Claude Run 仍是 0/3、Worker/Reviewer receipt pending：[dashboard-data.json:66](</C:/Users/17381/Desktop/测试全流程skill/.phase8-forward/claude-host/project/work/test-runs/PHASE6-CLAUDE-003/dashboard/dashboard-data.json:66>)。 |
| Phase 7 覆盖同步 | 未验证 | 按计划暂不执行，且用户未授权覆盖全局目录。 |
| Phase 8 Jev | 阻塞 | 评估集未冻结、预算/外发边界未确认、API 路径数据集不足、Adapter 不安全、Runtime/Reviewer/Final Review 未接通、无双宿主正式路径。 |

## 实际运行的验证

- `git status --short --branch`
  - 结果：main 与 origin/main 同步；21 个 tracked 修改及多个 untracked 目录。
- `git diff --check`
  - 结果：非零；README、Data Readiness SKILL、Defect SKILL 有新增 EOF 空行。
- `python -m pytest --collect-only -q`
  - 结果：71 tests collected。
- `python -m pytest -q -p no:cacheprovider --ignore=...test_live_smoke_execution.py`
  - 结果：68 passed，2 skipped。
- Bootstrap suite
  - 结果：14 passed，2 skipped。
- Planning suite
  - 结果：6 passed。
- 当前 `final_review.py` 复核 `PHASE5-FORWARD-004`
  - 结果：exit 1，`UnboundLocalError`。
- 直接发送 `defect_disposition_applied`
  - 结果：exit 1，unsupported event。
- 按 Planning 文档校验 `ui_candidate_revalidation`
  - 结果：exit 1，验证器要求 `ui_candidate_selection`。
- `workspace_validate.py` 分别检查 Phase 5、Codex Phase 6、未完成 Claude Run
  - 三者都返回 `ok=true`；这只证明目录布局，因为验证器本身只检查文件位置：[workspace_validate.py:5](</C:/Users/17381/Desktop/测试全流程skill/clarify-before-testing/scripts/workspace_validate.py:5>)。
- 当前 TypeScript 骨架副本执行 `tsc --noEmit`
  - 结果：exit 0。
- 10 个相关 `.mjs` 执行 `node --check`
  - 结果：10/10 通过。
- Phase 6 smoke 产物只读复算
  - TC-API-001、TC-UI-001、TC-UI-002 的脚本 Hash、runner 报告 Hash 均匹配，Runner 均成功；UI 录屏 Hash 匹配。
- 没有运行固定目录 live smoke、scratch 实网脚本、Jev 请求或真实业务操作。

## 关键证据路径

- Codex API/UI baseline：  
  [.phase6-forward/PHASE6-JEV-BASELINE-001](</C:/Users/17381/Desktop/测试全流程skill/.phase6-forward/fresh-project/work/test-runs/PHASE6-JEV-BASELINE-001>)
- Claude 未完成 Run：  
  [run-status.json:5](</C:/Users/17381/Desktop/测试全流程skill/.phase8-forward/claude-host/project/work/test-runs/PHASE6-CLAUDE-003/internal/state/run-status.json:5>)
- 当前代码复核失败的历史 Phase 5 输入：  
  [final-review-input.json](</C:/Users/17381/Desktop/测试全流程skill/.phase5-forward/synthetic-project/work/test-runs/PHASE5-FORWARD-004/internal/review/final-review-input.json>)
- 真实业务历史材料：  
  [case-result-v2.json:8](</C:/Users/17381/Desktop/测试全流程skill/.real-execution/RUN-20260927-B01-CASE-001/results/case-result-v2.json:8>)明确为 BLOCKED、Case 步骤未开始；[closure.md:34](</C:/Users/17381/Desktop/测试全流程skill/.real-execution/RUN-20260927-B01-CASE-001/closure.md:34>)又要求后续新 Worker，因此不能作为新版闭环完成证据。
- Jev 批准状态：  
  [jev-runtime-ui-evidence-manifest-draft-003.json](</C:/Users/17381/Desktop/测试全流程skill/research/artifacts/jev-runtime-ui-evidence-manifest-draft-003.json>)仍记录阈值、停止条件、预算和评估冻结待用户确认。

## 仍需的前向验收

修正上述代码后，至少还需要：

1. 新隔离 Run 覆盖真实的基础数据、Batch 数据、Runtime 产物分类和 actor/secret 引用。
2. Data Readiness 产品 Bug → 独立复核 → 正式提单 → 保持未执行 BLOCKED。
3. 初测快照 → 等待修复 → 部署版本核验 → 多轮回归 → BLOCKED 重新 Data Readiness → 新 Worker → 新 Reviewer。
4. 延期/无需修复的原子处置及 Final Review 风险保留。
5. 当前代码下重新跑 API、普通 UI、critical UI smoke。
6. Codex 与 Claude 各自提供宿主可核验的 Worker 完成后再派 Reviewer 的真实调用顺序；Claude 当前仍未验收。
7. 用户另行确认数据外发、预算和停止条件后，才可进行 Jev shadow/隔离真实调用；UI 与 API 两条路径分别验收。
</USER_REQUEST>
<ADDITIONAL_METADATA>
The current local time is: 2026-09-29T09:15:40+08:00.
</ADDITIONAL_METADATA>