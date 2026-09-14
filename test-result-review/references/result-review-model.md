# Result Review Model

逐 Case 对账：planned primary execution vs actual execution；planned evidence vs actual evidence；FAIL 的 Bug 闭环；BLOCKED 原因；PASS_AFTER_FIX 的 FAIL→Bug→Regression 历史。逐 Batch 再核对 Worker Self Review / Reviewer mandatory checks 与 completed 状态。

`FAIL` 始终代表 unresolved；`fixed=true` 等过程标记不能改变最终判断。真正修复并回归通过必须转成 `PASS_AFTER_FIX` 并带完整回归历史。

内部输出：

```yaml
final_assessment:
  coverage_complete:
  core_flow_passed:
  unresolved_critical_defects:
  blocked_scope:
  regression_complete:
  conclusion: ready | ready_with_risk | not_recommended | incomplete
```

正式报告只能根据 `final_assessment.conclusion` 映射中文结论。
