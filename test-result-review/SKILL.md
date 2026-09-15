---
name: test-result-review
description: Reconcile the entire completed testing Run and produce the final human-readable quality conclusion and report. 仅在计划内 Batch 已执行/复核完毕，缺陷与回归状态已稳定后使用。对账正式 Case、Execution Planning、最终结果、Bug、BLOCKED、执行方式、证据与回归历史；不重新执行测试，也不能只看通过率。生成最终报告后由 Router 绑定真实复核产物再关闭 Run。
---

# Test Result Review｜最终结果复核

定位：

> **对账整个 Run，确认测试是否真正完成，并形成最终质量结论。**

不重新执行 Case。

---

# 1. 最终 Case 对账

必须满足：

```text
正式测试用例
=
Execution Planning Case
=
最终结果 Case
```

每条 Case 最终状态只能是：

```text
PASS
FAIL
BLOCKED
PASS_AFTER_FIX
```

`NEEDS_REVIEW` 不允许留到最终报告。

---

# 2. Batch 对账

每个 Planning Batch 必须有最终 Batch Result。

检查：

- Worker self-review；
- Reviewer；
- Retest 是否完成；
- 是否仍有 needs_rework；
- 是否有未执行 Case。

---

# 3. 执行方式对账

检查：

- UI 是否真实 UI；
- API 是否真实 API；
- 人工是否真实人工回填；
- 是否发生未经 Planning 允许的偷换；
- 是否有核心业务流程缩水。

---

# 4. Evidence 对账

不是只检查“有引用”。

重点抽：

- P0；
- 核心业务链；
- 严重 Bug；
- FAIL 后回归通过；
- BLOCKED；
- 跨模块；
- Reviewer 曾要求补测的 Case。

判断 Evidence：

- 当前环境；
- 当前账号；
- 当前业务对象；
- 本次执行时间；
- 真能证明 Expected；
- 不是只证明“点击过”。

---

# 5. FAIL 对账

每个 FAIL 必须有：

- 新 Bug；
- Existing Bug；
- 或明确合理的 no_bug_reason。

不能有“产品 FAIL 但什么都没处理”。

---

# 6. BLOCKED 对账

BLOCKED 必须有真实原因：

- 产品 Bug；
- 环境；
- 外部资源；
- 上游失败；
- 人工等待；
- 数据不可用。

检查阻塞范围是否被夸大。

---

# 7. PASS_AFTER_FIX 对账

必须保留：

```text
initial FAIL
→ Bug
→ Regression Task
→ 新 Worker
→ 原 Case + 必要影响范围
→ PASS
→ PASS_AFTER_FIX
```

不允许用 `fixed=true` 把仍是 FAIL 的 Case 当已解决。

---

# 8. Planning Evidence 对账

检查：

- 规划录屏是否实际存在；
- 下载文件是否保存；
- 关键 API/Network Evidence 是否按计划留；
- 有豁免时是否有真实理由。

---

# 9. 最终质量判断不能只看通过率

综合：

- P0/P1；
- 核心业务流程；
- 未修复 Bug；
- Bug 严重程度；
- BLOCKED 范围；
- 回归；
- 实际完成范围。

例如 98% 通过，但唯一失败是 P0 主流程，不能得出“质量良好”。

---

# 10. 对外结论使用正常中文

只使用类似：

- 测试完成，可进入下一阶段；
- 测试基本完成，但仍有风险；
- 不建议进入下一阶段；
- 测试未完成，当前无法形成完整质量结论。

不要输出 COMPLIANT、QUALITY GATE、CONDITIONAL READY。

---

# 11. 正式报告

```text
deliverables/05-test-report.md
```

建议：

```markdown
# 测试报告
## 1. 测试范围
## 2. 执行概况
## 3. 核心业务流程结果
## 4. 缺陷情况
## 5. 修复与回归情况
## 6. 未完成/受阻范围
## 7. 主要质量风险
## 8. 最终测试结论
```

---

# 12. Final Review 是真实产物

最终结构化复核结果必须通过：

```text
test-result-review/scripts/final_review.py
```

然后 Router 用该真实文件绑定 final review。

不能手写：

```text
final_review_status=passed
```

直接关闭 Run。

---

# 13. 最终清理

删除：

- 无价值 temp；
- scratch；
- 无价值 Trace；
- 重复截图；
- 调试 DOM；
- 缓存文件。

保留：

- 正式 UI/API/Data 脚本；
- Case 最终结果；
- 关键 Evidence；
- Bug Evidence；
- 必要日志；
- 下载文件；
- 最终报告；
- Dashboard 最终状态。

详细：

`references/result-review-model.md`

# 13. Final Review 必须重开真实执行资料

Final Review 不相信最终摘要里的 `PASS` 字样。

复核时必须重新读取当前 Run 中真实的：

- 已人工确认且 SHA 绑定仍有效的 `internal/execution/execution-plan.json`；
- 当前仍有效的已确认 `internal/design/test-cases.json`；
- 每个 Batch 的 Runtime State、Task、Worker Results；
- `case-results-ledger.json`；
- 原始 Evidence 文件；
- PASS_AFTER_FIX 对应的初始 FAIL 与 Regression Result。

并重新调用 Runtime Contract 做 Expected → Actual → Evidence 校验。Evidence 文件已经丢失、Case 集不一致、Batch 未完成或 Regression 不完整时，不能关闭 Run。

没有显式标记核心流程的简单项目，不会因为 `core_flow` 为空自动判定为“不建议进入下一阶段”；只有真实核心流程存在且失败时才影响该项判断。
