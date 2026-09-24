# Fresh acceptance fixture

This line must survive project bootstrap.

<!-- TEST-WORKFLOW:START -->
## AI 测试流程入口

- 开始或恢复测试前，必须先读 `.test-workflow/PROJECT_TESTING_INDEX.md`。
- 再读取当前 Run 的 `internal/state/run-status.json` 和 Router 给出的 `next_action`。
- 正式 Runtime 必须由主 Agent 派独立 `test-execution-worker`；Worker 完成并自审后再派新的 `test-result-reviewer`。
- 自动化 UI/API Case 必须先写 TypeScript 脚本，再运行最终脚本；临时交互不能代替正式执行。
- API 使用 Vitest + Node 原生 fetch；UI 使用 Playwright Test。
- 无法使用独立子 Agent 时停止并报告，不由主 Agent 自演 Worker/Reviewer。
<!-- TEST-WORKFLOW:END -->
