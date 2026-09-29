# Project Bootstrap 方法

- 先确定真实项目根目录；不把 Skill 仓库或用户全局安装目录误当目标项目。
- `CLAUDE.md` 与 `AGENTS.md` 只管理 `<!-- TEST-WORKFLOW:START -->` 至 `<!-- TEST-WORKFLOW:END -->` 区块。标记缺一、重复或嵌套时停止；没有标记时追加；区块外内容必须原样保留。
- 项目索引列出资料和命令的入口、来源、缺陷平台默认能力映射与待确认项，不复制业务文档内容，不保存账号密码、Token 或连接密钥。
- `project-profile.json` 记录 `workflow_version`、各入口托管区块 SHA-256、索引 SHA-256、缺陷平台默认设置、来源 Hash 和更新时间。版本一致且来源未变时不重写文件。
- 写入前对所有受管目标（Agent 定义、TypeScript 骨架含 Jev adapter、测试索引和 Profile）做整体冲突检查。已有资产只有在内容等于当前资产，或哈希等于上一版 Profile 记录的受管哈希时才可继续更新；已有索引必须与 Profile 记录的索引哈希一致，已有 Profile 必须可识别；其他内容视为用户文件/本地定制，停止 Bootstrap 并报告路径。符号链接和非普通文件也拒绝替换。冲突检查必须先于任何文件写入，避免冲突造成部分初始化。
- `.claude/agents/test-execution-worker.md` 与 `test-result-reviewer.md` 是不同 Agent 定义。运行时主 Agent 必须用宿主 Agent/Task 工具真实创建新会话；文件和回执中的 session ID 不能替代工具调用记录。
- `work/test-automation/` 安装公共 TypeScript 框架（含 `jev-adapter.ts`、`api-client.ts`、`evidence.ts`、`playwright.ts`、`redaction.ts`）。具体 API/UI Case 脚本由对应 Execution Worker 在当前 Run 下创建，首次执行也如此。
- Bootstrap 是项目级动作，不是 Run 阶段，不更改 `current_stage`。用户未授权的真实业务项目不能拿来做本仓库开发验收。
