# 全局 AI Agent 记忆与工程规范手册（跨设备恢复版）

> **用途说明**：本文档沉淀了从本机 Claude Code (`~/.claude/CLAUDE.md` & `projects/*/memory`)、Codex (`~/.codex/memories/memory_summary.md` & `memories_v2`) 以及 Antigravity 长期实战中提炼出的**个人工程偏好、测试方法论、Agent 协作红线与全局提示词模板**。  
> 已剔除所有公司内网地址、账号密码与敏感配置，可安全保存在个人 GitHub 仓库中。换新电脑或重装环境时，直接复制对应章节即可一键恢复各 Code Agent 的全局记忆。

---

## 一、新电脑快速恢复指南

| Agent 工具 | 全局规则文件路径 | 技能（Skills）安装路径 | 恢复方式 |
| :--- | :--- | :--- | :--- |
| **Claude Code** | `~/.claude/CLAUDE.md` | `~/.claude/skills/` | 复制下方「2.1 Claude Code 全局模板」至 `~/.claude/CLAUDE.md`；将本仓库技能目录同步至 `~/.claude/skills/` |
| **Codex CLI / Desktop** | `~/.codex/AGENTS.md`<br>`~/.codex/memories/memory_summary.md` | `~/.codex/skills/`<br>`~/.agents/skills/` | 复制下方「2.2 Codex 全局规则与记忆模板」；同步技能目录 |
| **Antigravity / Gemini** | `~/.gemini/GEMINI.md` | `~/.gemini/config/skills/` | 复制通用规则模板；将本仓库技能目录同步至 `~/.gemini/config/skills/` |

> **多 Agent 技能同步铁律**：
> 1. 仅同步包含正式 `SKILL.md` 的标准技能目录，不要把 `.zip` 归档包、临时测试产物（`deliverables/`、`internal/`、`scratch/`）考入全局技能目录。
> 2. 同步前先检查目标路径是否为 `ReparsePoint` / `Junction`（Windows 目录联接），保留合法的软链接结构，替换前留存可恢复备份。
> 3. 同步完成后必须做逐文件 `SHA-256` 校验，目录复制成功不等于内容一致。

---

## 二、可直接复制的全局规则模板

### 2.1 `~/.claude/CLAUDE.md` 模板

```markdown
中文回答我，说人话，结论先行，清晰直接。

## 1. 协作与修改边界（全局强制）
- **设计讨论默认只读**：当指令为“先看看”“分析一下”“先从设计开始”“怎么改造”时，只做代码/产物诊断与方案讨论；未经明确授权，严禁直接修改代码、严禁同步全局已安装 Skill、严禁自动 git commit / revert。
- **证据分级汇报**：严格区分「静态代码/文档事实」「本次真实运行证据」「历史缓存/快照」「待验证风险」。不得把单元测试通过、HTTP 200、页面提示成功或结构校验通过表述为真实业务闭环。
- **重构原则**：当明确要求“只考虑重构、不考虑兼容”时，直接重划数据源（Source of Truth）与职责边界，不要在旧入口上叠打补丁。

## 2. 软件测试与测试全流程 Skill 规范
- **独立可执行用例（Standalone Case）**：每条用例必须能够独立准备、独立执行、独立断言、独立留证（包含明确的前置条件、步骤、账号/数据、分层断言）；同一 Batch 可共享稳定环境资源，但严禁依赖其他用例临时创建的业务对象或 PASS 结果。
- **执行方式默认准则**：凡有 UI 入口的正常用户业务场景，默认以 **UI** 作为主执行路径；API 仅用于显式批准的单条豁免，或用于前置数据准备与后置回读校验（Setup / Read-back 与主执行分类严格分离）。
- **测试数据语义化**：拒绝无意义的随机编码和乱码字符串；测试数据必须贴近真实业务语义且关系自洽。Run/Batch/Case 追踪标识放在内部映射（Manifest）中，不要污染面向用户展示的业务名称。
- **共享环境数据隔离**：在共享测试租户中验证时，使用独立测试账号与唯一业务命名空间隔离，严禁删除或重建公共组织架构与主数据。

## 3. 禅道提 Bug 规范（全局强制）
调用 `zentao_create_bug` 提缺陷前，**必须先加载全局技能 `zentao-bug-filing`** 并按其规范执行，不得凭描述直接写入：
1. **标题层级式前缀**：`【大模块】`开头，有子模块继续 `【子模块】`，再接一句话现象（例：`【知识库管理】【检索测试】已保存的「最低相关度」阈值未生效`）。开头不得放【功能】【UI】等类型词；存量单前缀不改，只约束新单。
2. **steps 齐套**：环境/前置、复现步骤、实际结果、预期结果（必须带业务依据出处）、复现率；根因须追到文件:行号实锤；附修复建议。
3. **提交前 10 项自审全过才提交**：其中查重（`zentao_list_bugs` 按关键词搜）与敏感信息红线（token/密码/Cookie/内网密钥严禁入单）不可省略。
4. **截图随单上传**：有截图必须随 create 传 `images`（update 不支持补图）。
```

---

### 2.2 `~/.codex/AGENTS.md` 与 `memory_summary.md` 模板

```markdown
## User Profile
Chinese-speaking Windows/PowerShell engineer focused on rigorous software testing, business-contract modeling, RAG/knowledge-base evaluation, browser automation agents, and AI-agent workflow architecture. Values real business evidence, explicit workflow state, traceable artifacts, and a strict boundary between static review, planning, runtime execution, and verified closure. Prefers concise plain-Chinese conclusions ("说人话") with explicit basis and uncertainty boundaries.

## Core Engineering & Testing Preferences
1. **Read-Only Diagnosis vs. Authorized Edits**: Treat design reviews and audits as strictly read-only until the user explicitly authorizes code or file modifications. Never sync global skills or commit changes without confirmation.
2. **UI-Default Execution & Standalone Cases**:
   - Every test case must be self-contained (independently preparable, executable, decidable, and auditable).
   - Normal user-facing business flows must use UI as the primary execution path; API is restricted to explicit per-Case exceptions or setup/read-back verification.
3. **Meaningful Test Data & Tenant Safety**:
   - Use natural, business-meaningful names and coherent entity relationships instead of meaningless codes.
   - Keep Run/Batch/Case tracking IDs in internal manifests rather than polluting user-visible fields unless required for namespace isolation.
   - In shared environments, isolate via dedicated accounts and namespaces; never delete or rebuild shared master data.
4. **Evidence Hierarchy & Honest Closure**:
   - Never conflate static code checks, mock/unit test passes, HTTP 200 responses, or historical snapshots with current end-to-end runtime verification.
   - When referencing historical bugs or peer test cases, explicitly record snapshot freshness/watermarks and never transplant historical assertions blindly.
5. **RAG & Async Chain Verification**:
   - For knowledge-base / OCR / RAG flows, verify the full chain: Upload -> Parse/OCR -> Chunking -> Indexing -> Status -> Retrieval -> Workbench Consumption.
6. **Browser Agent & Non-Idempotent Writes**:
   - Keep deterministic code in charge of workflow orchestration and browser mechanics; bound AI to structured decision points behind an approval/evidence gateway.
   - If a non-idempotent UI write returns an unknown state, read back and reconcile the page state before retrying.
7. **Windows / PowerShell UTF-8 Discipline**:
   - Always run Python scripts and pytest with explicit UTF-8 (`PYTHONUTF8=1` or `python -X utf8`) on Windows paths containing Chinese characters.
```

---

## 三、核心方法论沉淀（随时查阅）

### 3.1 测试全流程 Skill 七阶段闭环核心不变量
1. **业务理解（`test-business-modeling`）**：
   - 正式 PRD 优先级高于不冲突的原型线索与历史口头解释。
   - 向用户提问前必须先排查 PRD 演示/验收场景；未决问题按「模块 → 场景 → 已知规则 → 剩余问题 → 受影响范围」收敛。
   - 结构化模型校验通过不代表业务问题已解决，必须经人工确认后才可冻结进入下一阶段。
2. **测试点设计（`test-point-design`）**：
   - 先盘点基础功能与正常导航主路径，再展开决定性条件、实质业务预期、防假成功边界（如接口返回成功但未落库/未生效）与保持项。
   - 必须闭合追溯链：`业务来源 → 覆盖项 → 场景族 → 校验义务 → 测试点`。
3. **测试用例设计（`test-case-design`）**：
   - 正式交付必须保证人工可读 Markdown 与结构化 JSON 同源一致。
   - 每条用例自包含，禁止交付“主项 + 执行实例拼接”的半成品。
4. **执行规划与数据准备（`test-execution-planning` / `test-data-readiness`）**：
   - 规划阶段锁定每条用例的 UI/API/人工主执行方式、同批依赖顺序、数据策略与证据方案，Runtime 阶段严禁擅自更改。
   - 数据准备优先走合法业务路径（API 优先、UI 兜底，严禁直接用 SQL 造业务数据），创建后必须回读（Read-back）验证状态、关联关系与账号可访问性。
5. **运行时执行与独立复核（`test-execution-runtime`）**：
   - 每个 Batch 由独立 Worker 会话串行执行（仅显式批准的 `parallel_safe` 且数据完全隔离的 Batch 可并行），执行完成后必须经过独立 Reviewer 会话复核。
   - 多轮重测（Retest）必须**逐轮累积合并**各 Case 的最新判定结果（保留中间轮次已确认的 `FAIL` 与 Findings，严禁退回初始轮次的 `PASS`，严禁遗留未决的 `NEEDS_REVIEW` 或脚本字节已过期的结果落账）。
6. **缺陷处理与终审对账（`test-defect-handling` / `test-result-review`）**：
   - 仅在排除脚本、Locator、测试数据与环境问题，并经独立 Reviewer 确认后才可转为产品缺陷。
   - 终审对账必须核对「正式用例 ↔ 执行计划 ↔ 最终账本结果 ↔ 缺陷单 ↔ BLOCKED 原因 ↔ 回归历史 ↔ 证据快照哈希」，不看虚假的单纯通过率。

### 3.2 面试与技术复盘叙事结构（Problem-Driven Story）
在准备测试架构、AI Agent 或自动化项目复盘时，拒绝“罗列技术名词清单”，始终采用**问题驱动叙事**：
1. **背景与痛点**：为什么原有的手工测试或单次 Prompt 生用例不可靠？（如：遗漏隐式状态流转、假成功断言、跨轮次上下文丢失、AI 自审自判作弊）
2. **架构演进与核心设计**：如何通过「契约化阶段门禁 + Markdown/JSON 同源双视图 + Worker/Reviewer 会话隔离 + 证据快照 SHA-256 冻结」解决上述痛点？
3. **真实落地与演进步骤**：经历了哪几次关键重构（如从主从拼接用例到独立自包含用例、从首末轮合并漏洞修复到逐轮状态累积与脚本字节防篡改校验）？
4. **客观边界**：清晰区分哪些是由确定性代码保证的、哪些是由 AI 判定的、哪些已完成单元测试/真实项目验证，坦诚交代边界，经得起深度追问。
