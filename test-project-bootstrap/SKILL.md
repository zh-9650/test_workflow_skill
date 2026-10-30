---
name: test-project-bootstrap
description: Initialize or refresh the testing workflow entrypoints (CLAUDE.md and AGENTS.md) for an explicitly selected project before a test Run. Preserve project-authored instructions while installing the managed testing blocks, project testing index, profile, agent definitions, defect platform default mapping, and TypeScript runtime skeleton including Jev adapter.
---

## 项目知识协作入口

处理具体项目工作前，读取 [项目知识读取与沉淀协议](../clarify-before-testing/references/project-knowledge-protocol.md)。该协议覆盖已有项目背景、非 Skill 材料接收、测试线选择和公共能力复用；本阶段职责仍由下文规定。


# Project Bootstrap｜项目测试入口初始化

仅在用户明确指定目标项目并开始接入测试流程，或 Router 检测到该项目 Bootstrap 缺失、版本漂移、托管区块失效时使用。当前仓库开发和临时验收可在临时项目运行；未经用户确认，不对真实业务项目执行。

1. 先读取目标项目已有 `CLAUDE.md`、`AGENTS.md`、项目资料和构建入口。保留两者托管区块以外的内容，也不要把密钥值写入索引。
2. 执行 `python test-project-bootstrap/scripts/bootstrap_project.py --project-root <项目根目录>`。脚本安全管理 `CLAUDE.md` 和 `AGENTS.md` 的 `TEST-WORKFLOW` 区块、`.test-workflow/` 共享索引与 Profile、两个项目级 Claude Agent 定义、缺陷平台默认映射以及 `work/test-automation/` 公共 TypeScript 骨架（含 Jev adapter）。
3. 读取生成的 `.test-workflow/PROJECT_TESTING_INDEX.md` 和 `project-profile.json`，人工核对项目资料入口、命令、环境标识、缺陷平台映射及缺失项。脚本的路径发现只是索引初稿，不能代替对项目资料的业务理解。
4. 同版本且来源不变时再次运行应不改文件；版本或索引来源漂移时，只刷新受管内容。写入前先检查所有受管文件目标（包括 Agent 定义、公共骨架、测试索引和 Profile）：首次接入遇到非本 Skill 文件，或升级时发现文件被项目修改，必须整体停止并报告冲突，不得覆盖。受管目标为符号链接或非普通文件时也停止。若存在重复/不完整托管标记，也停止并交由人核对。
5. Bootstrap 不写 `current_stage`，完成后交给 Router 发现或创建 Run。若宿主不能派独立 Worker 和 Reviewer，Runtime 应停在明确等待/阻塞状态。

具体方法和受管边界见 [project-bootstrap-method.md](references/project-bootstrap-method.md)。
