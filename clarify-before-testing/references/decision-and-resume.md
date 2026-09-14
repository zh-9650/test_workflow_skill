# 决策与恢复

只记录会改变预期结果、覆盖范围、执行方式或测试结论的人工决策。恢复依据 `internal/state/run-status.json` 和正式产物，不依赖聊天记忆。执行中断时，从 `current_case` 开头重新执行；不保存步骤级 Resume Pack。
