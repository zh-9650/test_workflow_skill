# Runtime Worker 方法

主 Agent 不直接长时间执行 Case，而是通过 Runtime Orchestrator 管理 Batch：Precheck → 构建 Worker Task → Worker 执行 → Worker 自审 → Reviewer。

Worker Task 必须带 Case 顺序、完整 Case、Execution Context、Data Manifest、Evidence Plan、允许/禁止调整项和输出目录。Worker 可以修 Locator/等待/脚本等实现问题，但不能修改 `primary_execution`、Expected、关键业务步骤或 Batch 范围。

Case 结果严格区分：
- PASS：每个 Expected 有具体 Actual、结果为 pass、Evidence 非空；规划明确豁免时需有豁免原因。
- FAIL：必须是 `reason_type=product_issue`，有 Expected/Actual/Evidence，且已复现或明确说明复现不适用。
- BLOCKED：必须是业务/环境/外部资源/上游 Case/人工等待/数据不可用/账号权限之一；脚本或 Locator 错误不能长期 BLOCKED。
- NEEDS_REVIEW：必须记录待审类型、原因和 `required_action`。
