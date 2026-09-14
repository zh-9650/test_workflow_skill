# Test Workflow Skills

一套面向真实项目测试的完整 Skill 流程，从测试范围澄清、业务理解、测试设计，一直覆盖到执行规划、数据准备、真实执行、缺陷回归和最终结果复核。

它的目标不是生成一批看起来完整的测试文档，而是让每个阶段都有真实产物、明确确认、可恢复状态和可追溯证据，最终结论必须由实际执行结果推导。

## 流程总览

```text
clarify-before-testing
        ↓
test-business-modeling
        ↓
test-case-design
        ↓
test-execution-planning
        ↓
test-data-readiness
        ↓
test-execution-runtime
        ↓
test-defect-handling（无缺陷时可跳过）
        ↓
test-result-review
```

## 8 个 Skill

| Skill | 职责 |
|---|---|
| `clarify-before-testing` | 测试总路由，创建或恢复 Run，管理阶段状态、正式产物和人工确认点。 |
| `test-business-modeling` | 基于当前项目资料建立模块化业务理解，覆盖规则、状态、数据影响和跨模块业务链。 |
| `test-case-design` | 先生成并确认测试点，再生成可执行测试用例；要求真正应用测试设计方法并完成 AI 自审。 |
| `test-execution-planning` | 为每条 Case 明确主执行方式、Batch、依赖、并发条件、数据需求和 Evidence Plan。 |
| `test-data-readiness` | 只为当前 Batch 准备并回读验证测试数据，不允许通过 SQL 或内部状态直改伪造业务事实。 |
| `test-execution-runtime` | 按已确认计划执行 Case，管理 Worker、自审、独立 Reviewer、局部补测、状态恢复和实时 Dashboard。 |
| `test-defect-handling` | 对确认的产品问题做重复检查、缺陷提交、Case/Batch 关联和独立回归。 |
| `test-result-review` | 对账全部 Case、Batch、缺陷、阻塞项、执行方式、证据和回归记录，推导最终测试结论。 |

## 核心设计原则

- 当前项目资料优先，不把其他项目经验直接当成当前业务规则。
- 业务理解、测试点、测试用例和执行计划都必须先由 AI 自审，再交给用户确认。
- 人看的 Markdown 与机器追踪的结构化数据分开保存。
- 正式产物登记文件摘要；产物修改后，下游确认自动失效。
- UI Case 不能在执行阶段偷换成 API，辅助接口只能作为补充观察手段。
- 每个 Expected 都必须记录实际结果和对应 Evidence，脚本成功或 HTTP 200 不等于 Case PASS。
- 技术错误、数据错误和环境错误不能直接判为产品缺陷。
- Worker 自审后必须由独立 Reviewer 复核；Reviewer 可以要求局部补测或返回上游阶段。
- FAIL、Bug、Regression 和 `PASS_AFTER_FIX` 必须形成完整可追溯历史。
- 最终结论不只看通过率，而是综合核心流程、严重缺陷、阻塞范围、实际覆盖和回归结果。

## Run 目录

每次正式测试使用独立 Run：

```text
work/test-runs/RUN-xxx/
├─ deliverables/              # 给人阅读和确认的正式产物
│  ├─ 01-business-understanding.md
│  ├─ 02-test-points.md
│  ├─ 03-test-cases.md
│  ├─ 04-execution-plan.md
│  └─ 05-test-report.md
├─ dashboard/                 # 实时测试进度
├─ internal/                  # 状态、模型、计划、任务和结果
├─ scripts/{data,ui,api,temp}/
├─ evidence/                  # 截图、录屏、接口、网络和文件证据
├─ logs/
├─ downloads/
└─ scratch/
```

正式交付物、内部状态、执行脚本和测试证据各自归档，Run 根目录不散落临时文件。

## 使用方式

1. 将这 8 个目录放入 Agent 可读取的 Skills 目录。
2. 在目标项目中发起“按完整测试流程测试”“开始系统测试”或直接调用 `clarify-before-testing`。
3. Router 创建新的 `RUN-xxx`，或者读取已有 `run-status.json` 从 Batch/Case 边界恢复。
4. 依次完成业务理解、测试点、测试用例和执行计划的自审与人工确认。
5. 按 Batch 准备数据、执行、复核；发现产品问题时进入缺陷与回归流程。
6. 最后由 `test-result-review` 对整个 Run 进行对账并生成测试报告。

在 Codex 的个人 Skills 目录中使用时，可将 8 个 Skill 文件夹复制到：

```text
%USERPROFILE%\.codex\skills\
```

复制后重新打开任务，使 Agent 重新发现 Skills。

## Dashboard

Execution Planning 完成后会初始化 Dashboard。测试执行期间，Case、Batch、缺陷、阻塞项、执行方式和核心流程状态会随关键事件更新。

建议通过本地 HTTP 服务打开：

```powershell
python test-execution-runtime/scripts/dashboard_server.py `
  --run-dir work/test-runs/RUN-xxx `
  --port 8765
```

然后访问命令输出的 `http://127.0.0.1:8765/`。

## 运行要求

- Python 3.10 或更高版本。
- Skill 脚本本身只使用 Python 标准库。
- 真实 UI、API、文件下载和缺陷提交能力由运行这些 Skills 的宿主 Agent 提供。
- 禅道或其他缺陷平台必须返回真实 Bug ID；流程不会伪造缺陷提交成功。

## 能力边界

这套 Skills 负责测试方法、流程约束、任务编排、状态恢复、证据归档和结果对账，但不会凭空提供浏览器登录态、测试环境权限、业务账号或缺陷平台连接。

第一次接入新项目时，建议用一条真实主业务链完整走通：

```text
业务理解 → 测试点 → 测试用例 → 执行计划 → 数据准备
→ 真实执行 → Reviewer → Bug/Regression → 最终报告
```

只有真实 Run 的产物、证据、刷新回读和最终对账都成立，才表示该项目已经真正接入完成。
