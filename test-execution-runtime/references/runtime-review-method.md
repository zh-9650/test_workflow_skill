# Runtime Review Method｜Worker 自审与独立复核

## 派发身份与冻结输入

主 Agent 必须分别实际派发 Worker 和 Reviewer。Reviewer 只能在 Worker 完成自审并冻结结果哈希后创建；必须是新 Task、新的真实 Agent 会话，并且 `agent_session_id` 与 Worker 不同。检查真实 Task ID、两端 session ID、宿主 receipt 及结果哈希引用是否闭合对应。主 Agent 不能兼任或模拟任一角色。Runtime 对本地回执的字段/哈希校验不是宿主真实性证明；Reviewer 和最终前向验收必须把回执与当前会话的真实派发、完成记录相互核对。缺真实宿主派发能力、session 或 receipt 时，停止并报告阻塞，不能手填伪造字段。

Reviewer 必须以冻结结果哈希为审查输入，并核对 Worker Task/receipt、Runtime Result、脚本哈希、runner report 哈希之间的关联。Worker 自审完成时，Runtime 还要把脚本、runner report 与 Case Evidence 按 Task 版本复制到不可变快照目录，并把快照清单及哈希写入 Reviewer Task。哈希不一致、快照文件缺失或被改写、报告缺失，均不得通过该 Case/Batch。

## Worker Self Review

目标：Worker 在交给 Reviewer 前自己发现明显假成功和漏执行。

必须检查：

- task 中所有 Case 都有结果；
- 每个 Expected 都有 Actual；
- 每个 Expected 有足够 Evidence 或明确豁免；
- planned primary_execution == actual_execution；
- FAIL 真的是产品问题；
- BLOCKED 有真实阻塞原因；
- NEEDS_REVIEW 已明确需要什么动作；
- Evidence 没绑定错 Case/对象；
- 文件已整理。
- 当前 Batch 确由真实 Worker Task 执行，真实 session/receipt 与 Runtime 结果关联一致；
- 自动化 Case 的正式脚本先于首次正式执行创建，且实际由约定官方 runner 执行；没有 AI 临时操作替代；
- 每个自动化 Case 均有计划内脚本路径、最终脚本哈希、官方 runner report 及其哈希；
- 结果冻结后 Worker 未静默修改脚本、报告或结果；
- Case 计划要求的录屏独立存在并与该 Case 对应；
- 每次失败诊断均保留当时的诊断证据、脚本哈希和处理记录。

## Reviewer

Reviewer 使用干净上下文，不相信 Worker 的“passed”文字。

Reviewer 的输入还必须包含 Worker 与 Reviewer 的真实 Task/session/receipt，以及 Worker 冻结结果哈希清单。

### 完整性

- Case 数量；
- 顺序；
- Expected 数量；
- 缺失结果。

### 执行方式

- UI Case 是否真实 UI；
- API Case 是否真实 API；
- 辅助验证有没有代替主动作。

### PASS

抽查 Evidence：

- 是当前环境吗；
- 是当前账号吗；
- 是当前业务对象吗；
- 时间上与本次执行对应吗；
- 能证明 Expected 本身吗；
- 只证明交互成功还是能证明业务结果。

### FAIL

确认已排除：

- script_error；
- locator_error；
- data_error；
- environment_error；
- account_permission_error；
- case_design_issue。

### BLOCKED

阻塞必须真实存在，不能用 BLOCKED 掩盖“不会执行”。

### NEEDS_REVIEW

只要仍有 NEEDS_REVIEW，Reviewer 不允许 `passed` 关闭 Batch。

应：

- 局部补测；
- 或返回上游。

复核时还必须确认：

- Worker 与 Reviewer 是不同真实 Agent session，Reviewer Task 在冻结哈希产生后才创建；
- Worker Task、Runtime result、官方 runner report、最终脚本及两侧派发 receipt 通过 ID/hash 互相对应；
- 自动化首次执行前已写脚本，且实际执行命令来自固定官方 runner；
- Case 级录屏和诊断失败证据齐全，且未被覆盖。

## Retest

只重跑需要补测的 Case。

Retest 结果和第一次 Runtime 使用完全相同的 Expected/Actual/Evidence Contract。

局部 Retest 也必须由主 Agent 创建并实际派发新的独立 Worker Task。该 Worker 必须先按已确认 `script_target` 编写或更新脚本，再运行官方 runner、保存报告和最终脚本哈希并自审冻结。主 Agent 收到冻结哈希后再创建另一个新的 Reviewer Task，使用不同于 Retest Worker 的真实 `agent_session_id` 独立复核。Retest Worker/Reviewer 均不得复用首轮或先前 Retest 的角色会话；所有新 Task/receipt/session、结果版本和哈希都要关联到原 Case 与 Retest 结果。每轮自审完成时都必须创建不可变脚本/report/evidence 快照；Retest 不能改写前一轮的结果或快照。缺少真实派发能力时停止该 Retest。
