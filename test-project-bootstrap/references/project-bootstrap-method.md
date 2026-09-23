# Project Bootstrap 方法

- 先确定真实项目根目录；不把 Skill 仓库或用户全局安装目录误当目标项目。
- `CLAUDE.md` 只管理 `<!-- TEST-WORKFLOW:START -->` 至 `<!-- TEST-WORKFLOW:END -->`。标记缺一、重复或嵌套时停止；没有标记时追加。
- 项目索引列出资料和命令的入口、来源与待确认项，不复制业务文档内容，不保存账号密码或 Token。
- `project-profile.json` 记录 `workflow_version`、托管区块 SHA-256、索引 SHA-256、来源 Hash 和更新时间。版本一致且来源未变时不重写文件。
- `.claude/agents/test-execution-worker.md` 与 `test-result-reviewer.md` 是不同 Agent 定义。运行时主 Agent 必须用宿主 Agent/Task 工具真实创建新会话；文件和回执中的 session ID 不能替代工具调用记录。
- `work/test-automation/` 仅安装公共 TypeScript 框架。具体 API/UI Case 脚本由对应 Execution Worker 在当前 Run 下创建，首次执行也如此。
- Bootstrap 是项目级动作，不是 Run 阶段，不更改 `current_stage`。用户未授权的真实业务项目不能拿来做本仓库开发验收。
