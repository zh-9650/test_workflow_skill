# Runtime Review Method｜Worker 自审与独立复核

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

## Reviewer

Reviewer 使用干净上下文，不相信 Worker 的“passed”文字。

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

## Retest

只重跑需要补测的 Case。

Retest 结果和第一次 Runtime 使用完全相同的 Expected/Actual/Evidence Contract。
