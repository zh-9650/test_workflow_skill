---
name: test-execution-runtime
description: Execute one planned, data-ready Batch reliably and produce trustworthy per-Case results and evidence. 仅在执行方案已确认且当前 Batch 数据已准备完成时使用。1 Batch = 1 Execution Worker，Batch 内默认串行；严格保持 Planning 的主执行方式，逐项验证 Expected，技术错误先诊断而不是判产品 FAIL；Worker 自审后由独立 Reviewer 复核，必要时只局部补测。
---

# Test Execution Runtime｜正式执行

定位：

> **接收已经规划好、数据已经准备好的 Batch，可靠执行并形成可信结果和证据。**

Runtime 不负责：

- 重新决定 UI/API/人工；
- 重新分 Batch；
- 大规模造数；
- 修改 Case；
- 修改 Expected；
- 随便缩减验证范围。

---

# 1. 整体执行流程

```text
Batch 执行前检查
↓
主 Agent 组装 Worker Task
↓
派 1 个 Execution Worker
↓
Worker 按 Case 顺序串行执行
↓
每个 Expected 逐项判断
↓
按 Planning 留证
↓
异常 Diagnose / 恢复
↓
结构化结果
↓
整理脚本和文件
↓
Worker 自审
↓
独立 Result Reviewer
↓
Batch 完成 / 局部补测 / 返回上游
```

---

# 2. Batch 执行前检查

只检查当前 Batch 能不能开始：

- Web/API 可访问；
- 计划账号可登录；
- 前置数据存在；
- 关键状态正确；
- 浏览器/API 工具可用；
- Case / Plan / Data 映射完整；
- 上游 dependency 已满足。

不要重新做 Planning。

---

# 3. 主 Agent 与 Worker 分工

主 Agent：

- 维护全局 Run；
- 决定下一个 Batch；
- 组装 Worker Task；
- 接收结果；
- 派 Reviewer；
- 调度返回上游/缺陷/回归；
- 维护 next_action。

Execution Worker：

```text
1 Batch = 1 Worker
```

负责当前 Batch 里的具体 UI/API 执行、技术诊断、证据和 Case 结果。

不要默认 1 Case = 1 Worker。

---

# 4. Worker Task 必须完整

至少包含：

- Batch ID / 目标；
- Case 列表和顺序；
- 原步骤；
- Expected；
- 真正被测动作；
- 主执行方式；
- 辅助验证；
- Evidence 计划；
- 数据映射；
- 账号；
- dependency context；
- 项目资料路径；
- 输出目录；
- 允许/禁止调整范围。

不能只给 Worker 一句“执行 B01”。

---

# 5. Worker 可以调整什么

允许处理执行技术问题：

- Locator；
- 等待策略；
- 滚动；
- 弹窗；
- iframe；
- 新窗口；
- 非验证性导航；
- 浏览器恢复；
- 脚本 Bug；
- 辅助 API 查询；
- 根据源码重新定位。

禁止：

- UI → API；
- API → UI；
- 修改 Expected；
- 改 Case 目标；
- 跳过关键业务步骤；
- 跳过 Case；
- 改 Batch 范围；
- 偷换测试数据含义。

---

# 6. 单 Case 标准循环

```text
加载 Case
↓
确认前置与业务对象
↓
按 Planning 主执行方式执行真正被测动作
↓
观察关键中间状态
↓
执行辅助验证
↓
逐项验证 Expected
↓
记录 Actual
↓
绑定 Evidence
↓
判定 PASS / FAIL / BLOCKED / NEEDS_REVIEW
↓
进入下一 Case
```

脚本 exit code 0 不等于 Case PASS。

---

# 7. Expected 逐项判断

每个 Expected 都必须有：

```text
Expected
Actual
Evidence
Result
```

例如：

```yaml
- id: E1
  expected: 保存后页面提示成功
  actual: 页面出现“保存成功”
  evidence: ui/01-save.png
  result: pass
- id: E2
  expected: 返回列表后存在项目A
  actual: 列表显示项目A
  evidence: ui/02-list.png
  result: pass
```

所有关键 Expected 满足后 Case 才 PASS。

长流程必须验证关键中间状态，不只验证最后一步。

---

# 8. UI 执行方法

详细读取：

`references/runtime-worker-method.md`

核心原则：

- 按业务语义找对象，不靠盲目坐标；
- 表格先定位业务唯一行，再在行内操作；
- 下拉只操作当前打开 overlay；
- 保存后不能只看 Toast；
- 必要时重新读取列表/详情/API/Network；
- 页面状态变化后重新定位元素，不把旧节点当真。

---

# 9. 技术问题先 Observe → Diagnose → Act

```text
Observe
→ Diagnose
→ Act
```

禁止：

```text
失败
→ 原样重试
→ 原样重试
→ 原样重试
```

下一次尝试必须增加信息：

- 重新观察页面；
- 查 DOM/AXTree；
- 查 Network；
- 查源码；
- 验证业务对象；
- 验证状态；
- 验证数据。

技术错误不直接判产品 FAIL。

---

# 10. 对外 Case 状态

```text
PASS
FAIL
BLOCKED
NEEDS_REVIEW
```

### PASS
关键 Expected 全部通过。

### FAIL
确认产品行为与已确认 Expected 不符，并已排除明显脚本/Locator/数据/环境问题。

### BLOCKED
由于真实外部条件无法继续，例如：

- 上游失败；
- 环境；
- 外部资源；
- 人工等待；
- 数据不可用；
- 账号权限。

### NEEDS_REVIEW
当前结果不能可靠判断，例如：

- Case 设计疑似有问题；
- 业务规则仍不确定；
- Evidence 不足；
- Planning 与实际冲突。

存在 NEEDS_REVIEW 时 Reviewer 不能直接关闭 Batch。

---

# 11. Worker 自治停止边界

Worker 自己解决：

- Locator；
- 页面加载；
- 弹窗；
- iframe；
- 新窗口；
- 浏览器掉线；
- 脚本错误；
- 辅助 API 调试。

停止并返回主 Agent：

- 用例前提可能错误；
- Planning 与系统根本冲突；
- 数据准备状态错误；
- 环境整体异常；
- Expected 无法判断；
- 确认的 UI 入口根本不存在。

---

# 12. Evidence 与文件

目录：

```text
evidence/Bxx/TCxxx/
├─ ui/
├─ api/
├─ network/
├─ debug/
├─ files/
├─ bug/
└─ result.json
```

规则：

- 截图按关键判断点，不按点击次数；
- API/Network 只保留与判断有关的内容；
- 敏感信息脱敏；
- PASS 默认不长期保留 Trace；
- FAIL / NEEDS_REVIEW / UI 调试可以保留；
- 录屏由 Planning 决定；
- 日志只是调试材料，不等于测试结果；
- 下载文件归档到 Case；
- scratch 和无价值 temp 脚本在 Batch 结束清理。

---

# 13. Worker 自审

Batch 执行完成先检查：

- 是否漏 Case；
- 是否漏 Expected；
- 是否假 PASS；
- 是否 UI/API 偷换；
- Evidence 是否错绑；
- Evidence 是否真实位于当前 Run 的 `evidence/Bxx/TCxxx/` 下，而不是旧 Run 或任意外部文件；
- FAIL 是否排除脚本/数据问题；
- BLOCKED 是否合理；
- temp/scratch 是否清理；
- 正式脚本是否归类；
- 日志是否泄露敏感信息。

有问题先补。

---

# 14. 独立 Result Reviewer

Worker 自审通过后派干净上下文 Reviewer。

Reviewer 不重新完整执行系统。

读取：

- Batch Plan；
- Case；
- Result；
- Expected 映射；
- Evidence；
- 必要脚本/日志。

检查：

- Case 完整性；
- 执行方式；
- PASS 可信度；
- FAIL 是否误判；
- BLOCKED 是否成立；
- Evidence 是否能证明判断；
- 是否存在假执行。

结果：

- 通过 → Batch Completed；
- 局部问题 → Retest Task；
- 上游问题 → Case Design / Planning / Data Readiness。

详细：

`references/runtime-review-method.md`

---

# 15. 局部补测

Reviewer 只对真正有问题的 Case 生成 Retest Task。

Retest 必须重新走同一个 Case Result Contract：

```text
Case
→ Expected
→ Actual
→ Evidence
→ Result
→ Worker Self Review
→ Reviewer
```

不能用更弱的结果格式。

局部补测完成后只替换被补测 Case 的最新结果；未补测 Case 保留原结果与原审查事实。最终 Batch 自审/Reviewer 状态由“原完整 Batch 审查 + 局部补测审查”合并形成，不能让只检查 TC1 的补测审查覆盖原先 TC1、TC2、TC3 的完整审查。

---

# 16. 全局 Case 结果账本与跨 Batch 依赖

Reviewer 确认 Batch 后更新：

```text
internal/execution/results/case-results-ledger.json
```

下一个 Batch 自动读取上游结果。

上游：

- PASS / PASS_AFTER_FIX → 依赖满足；
- FAIL / BLOCKED → 下游相关 Case BLOCKED(upstream_case)。

主 Agent 不手工拼临时 `global-results`。

完成一个 Batch 后，Runtime 不直接启动下一个 Batch。若 Router 的 `next_action` 为 `prepare_batch_data(Bxx)`，必须返回 `data-readiness`，待该 Batch 的 Manifest 校验并绑定后再执行。

Bug 回归通过而解锁旧 BLOCKED Case 时，先完成 Router 指定 Batch 的数据重检与绑定，再准备恢复任务：

```bash
python test-execution-runtime/scripts/runtime_orchestrator.py resume-blocked-prepare \
  --run-dir <run> \
  --batch B02 \
  --cases C07,C08 \
  --bug-ref BUG-123
```

该命令只接受 Router 批准的 Case 集合，并验证它们确实已有 Reviewer 确认的 BLOCKED 历史、依赖已变为 PASS/PASS_AFTER_FIX、当前 Batch 数据仍有效。之后使用 `retest-case-start / retest-case-finish / retest-self-review / retest-reviewer` 完成恢复；不能直接改 Dashboard 或 Ledger。

---

# 17. Dashboard

Worker 执行 Batch 时必须按 Case 上报生命周期，而不是等整个 Batch 结束后一次性刷新：

```text
Case 开始 → Runtime `case-start` → Dashboard 显示当前 Case / Worker
↓
执行并完成该 Case
↓
Runtime `case-finish` → 校验 Result/Evidence → 保存该 Case 结果 → Dashboard 更新
↓
进入下一 Case
```

Batch 内仍由同一个 Worker 串行执行，不因此变成“一 Case 一个 Agent”。如果执行中断，已经 `case-finish` 的 Case 结果保留；当前未完成 Case 从 Case 开头重新执行。局部补测使用对应的 `retest-case-start / retest-case-finish`。

运行中持续更新：

- 总 Case / 已完成 / PASS / FAIL / BLOCKED / 待复核；
- Batch 进度；
- 当前 Batch / Case / Worker / Reviewer；
- Bug；
- BLOCKED 原因；
- 最近动态；
- Planning vs Actual 执行方式；
- 核心业务流进度；
- 录屏状态。

只 Case 级更新，不每个点击更新。

使用本地 HTTP server 打开，不依赖 `file:// fetch`。

---

# 18. 恢复

中断后从 Case 开头重跑。

先重新检查数据当前状态。

不做步骤级恢复，不假设最后一个动作已成功。

# 19. Evidence 与 Dashboard 的工程约束

Case Result 中写一个 Evidence 路径不代表证据存在。

Runtime Contract 会在 Run 目录下实际检查：

- 每个 Expected 的 Evidence 文件；
- FAIL 的正式证据；
- Planning 要求的录屏；
- 下载/文件类证据。

文件不存在时 Case 不能 PASS/FAIL 落账。

Runtime 的文件化编排会自动更新 `dashboard/dashboard-data.json`：Batch 开始、Case 结果、Reviewer 开始/完成以及局部补测都会同步，不依赖 Agent 额外记住调用 Dashboard。独立的旧 `batch_result.py` 已删除，Batch 完成只允许通过 Runtime Orchestrator + Reviewer 链路。
