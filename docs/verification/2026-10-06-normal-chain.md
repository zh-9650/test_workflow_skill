# 正常隔离链验收检查点

执行日期：2026-10-04 至 2026-10-06；整理日期：2026-10-07。

结论：Codex 宿主上的正常隔离 Run 已闭合，整个测试 Skill 尚未全项验收。本记录不替代本地唯一验收依据 `新版测试Skill改造计划.md`。

## 实际证实的范围

Run `FORWARD-20261004-001` 使用当前 v3 执行契约、隔离服务及合成账号，不操作真实业务项目。三个 Batch 分别执行 API health、UI 查询、UI 状态变更并刷新读回。API 使用 TypeScript + Vitest + Node 原生 fetch；UI 使用 TypeScript + Playwright Test。正式脚本在执行前落盘，保存脚本 Hash、原始 Runner 报告及逐 Expected 证据。

三个 Batch 均有实际宿主调用、任务绑定及完成记录：独立 Worker 完成并冻结自审后，主 Agent 才派新的独立 Reviewer。不是仅凭 JSON 中不同的会话 ID 判定隔离。B01 的首次 Worker 中断后由新 Worker 恢复；首次审查退回后再派新 Worker 技术补测和新 Reviewer，旧拒绝记录未覆盖。B02 的首次静态检查失败也保留，未伪造产品 FAIL。

三 Case 最终均为独立复核确认的 PASS。正式阶段快照、Final Review、报告生成及 Router 关闭命令均实际运行成功；重开状态为 `closed`、`final_review_status=passed`、待恢复队列为空，报告与复核 Hash 与 Router 绑定一致。技术补测未写成产品修复后的 `PASS_AFTER_FIX`。

UI 状态刷新读回仅证明该隔离进程中的页面行为，不证明数据库持久化。数据准备只核验隔离基础对象、合成权限与读回，不证明真实账号绑定或合法业务造数。

## 本次定向修补

- Runtime 在首次 Case 前支持真实 Worker 终止后的新角色恢复；不伪造旧角色执行记录。
- 冻结正式结果引用的脚本、前置、依据、原报告与诊断；保持失败 Attempt 证据，后续新增文件不改变旧快照。
- UI scope 返回完整路径字段与类型声明，修复正式 UI 类型检查失败。
- Final Review 区分明确退回的历史与仍被接受的结果：所有快照保留 Hash 校验，接受结果仍严格检查冻结完整性；报告展示原始审查退回状态。
- Router 阶段快照核对正式契约与实际审查资料，处理 Windows 路径分隔符并拒绝重复键；关闭时重新读取绑定的 Final Review 和报告，修复缺失状态路径参数。

## 可复查的本地证据

完整记录：`.verification-forward/20261004/acceptance-audit.md`。

Run 根目录：`.verification-forward/20261004/project/work/test-runs/FORWARD-20261004-001/`。其中 `internal/execution/host-evidence/` 保存宿主调用/完成元数据，`runner-results/` 保存 Runner 报告，`evidence/` 保存逐项原始观察、截图及录像，`internal/execution/` 保存结果、自审、独立审查与冻结快照。

| 产物（相对 Run 根目录） | SHA-256 |
| --- | --- |
| `deliverables/test-report.md` | `b75dce84313138cd4dbd87253c95b9e9bb48e7b9b64113b6232ffbceaa6eee57` |
| `internal/review/final-review-oct06-normal-001.json` | `0e7230dd2f42dde2a4b91dbd4eddea70d948f5a9c6d7e82a24f5e6dac5a2bbb0` |
| `deliverables/stage-snapshot-oct06-normal-001.json` | `244d776bda0a08b25ca40237a6625a65d7aa6b21b26267fa26bde32e9030bad7` |

原始运行资料及宿主会话不上传远程；以上是本地复查入口，不宣称远程源码包含完整验收证据。用户 ZIP、本地计划和全局 Skill 均未覆盖。

## 安全验证命令

```powershell
python -m pytest -q test-project-bootstrap/scripts/tests clarify-before-testing/scripts/tests test-execution-runtime/scripts/tests test-execution-planning/scripts/tests test-data-readiness/scripts/tests test-defect-handling/scripts/tests test-result-review/scripts/tests
node --test test-project-bootstrap/scripts/tests/test_run_scope.mjs test-project-bootstrap/scripts/tests/test_api_url.mjs
git diff --check
```

2026-10-07 提交前重新运行：Python 191 passed、3 skipped（13.29s）；Node 7 passed；diff 检查无错误。报告、复核和阶段快照的 SHA-256 也重新读取核对一致。三项 skip 为 Windows 符号链接权限限制，不算通过；junction 拒绝负例已执行。单元/合同测试与上述实际宿主隔离链是不同证据层级，不能互相替代；本次整理没有重跑已关闭的 Run。

## 剩余前向验收

完整验收矩阵、合法业务造数、数据准备产品 Bug 正式提单、产品 FAIL → 目标环境修复部署与旧 PASS 影响分析 → 数据重验 → 多轮回归、BLOCKED 恢复、用户延期/无需修复保留风险、新主聊天恢复，均不能由本正常 Run 推断通过。Claude 等另一宿主的派发须在该宿主实际核验。

正式 Jev 仍需明确外发字段与费用授权、冻结标签集 shadow 评估及正式 Case 调用证据；本次整理没有新的付费请求。全局覆盖同步未执行。
