---
name: test-execution-planning
description: Plan how the user-confirmed test cases will actually be executed for the current Run. 仅在测试用例已经 AI 自审并由用户确认后使用。决定每条 Case 的 UI/API/人工主执行方式、辅助验证、Batch、依赖、顺序、数据策略、并发资格和证据方案；AI 自审后由用户确认。Runtime 不得重新做这些决策。
---

# Test Execution Planning｜测试执行规划

定位：

> **在真正执行之前，把“怎么跑”一次规划清楚。**

Runtime 只执行已确认计划，不临场重新设计。

---

# 1. 入口

必须满足：

```text
测试用例已生成
+
AI 自审完成
+
用户已确认测试用例
```

输入：

- 已确认测试用例；
- 已确认业务理解；
- 当前测试范围。

按需读取：

- API 文档；
- 源码；
- 技术方案；
- 原型；
- 已有测试脚本；
- 项目环境配置；
- 当前对话已知信息。

---

# 2. 先建立执行上下文，不先问固定表单

先自己读取：

- 用户已经提供的信息；
- 项目配置；
- 环境文件；
- API 文档；
- 源码；
- 已有脚本。

只问无法自动得到的信息。

典型：

- Web 地址；
- API Base URL；
- 测试环境标识；
- 至少一个起始账号；
- 禅道项目/模块/开发负责人映射；
- 无法由 Agent 产生的外部资源。

用户已经给过的不要重复问。

敏感信息放 `.test-secrets.env` 或等价秘密引用，不写进正式用例、计划、报告、Bug、日志。

非敏感执行上下文：

```text
internal/execution/execution-context.yaml
```

---

# 3. 主执行方式和辅助验证方式分开

每条 Case 必须有一个主执行方式：

```text
UI
API
人工
```

表示真正完成被测业务动作的入口。

辅助验证可以是：

```text
UI
API
数据库只读
Network
日志
文件
其他系统
```

不要用模糊 `ui_api`。

---

# 4. 主执行方式按“测试目标”选择

## UI 主执行

测试目标包含：

- 页面控件；
- 前端校验；
- 用户交互；
- 页面联动；
- 按钮状态；
- 路由/刷新/返回；
- 完整用户业务流程；
- 页面反馈；
- 前端限制；
- 用户真实操作顺序。

必须 UI。

禁止为了方便用 API 代替被测 UI 动作。

## API 主执行

适合：

- 服务端规则；
- 参数组合；
- 非法参数；
- 鉴权；
- 幂等；
- 大量边界；
- 后端过滤；
- 纯接口能力。

## 人工

只用于确实不适合稳定自动化的外部/硬件能力。

“Agent 找不到元素”不是人工 Case。

---

# 5. 数据准备可以辅助，但不能替代被测动作

允许：

```text
API 快速准备一个合法“已审核项目”
→ UI 测试编辑/限制
```

不允许：

```text
API 直接完成 UI Case 的被测修改
→ 认为 UI 已测试
```

---

# 6. 按业务链划 Batch

禁止机械每 N 条一个 Batch。

考虑：

- 业务链；
- 数据生命周期；
- 状态依赖；
- 角色切换；
- 执行方式；
- 数据隔离；
- 破坏性操作；
- 上下文复杂度。

原则：

- 同一连续业务链尽量同 Batch；
- 同 Batch 内共享数据必须有真实业务连续性；
- 删除/停用/归档等破坏性 Case 通常放业务链最后；
- 明显独立的数据不要跨 Batch 复用。

---

# 7. Case 依赖与顺序

显式写：

```text
TC002 depends on TC001
```

默认优先：

```text
核心主流程
→ 状态/分支
→ 跨模块联动
→ 异常/边界
→ 破坏性操作
```

跨 Batch 依赖必须能由全局 Case 结果账本提供上游状态。

---

# 8. 并发资格

每个 Batch 明确 `parallel_safe`。

检查：

- 是否共享账号；
- 是否共享业务数据；
- 是否共享状态；
- 是否修改公共资源；
- 是否共用浏览器上下文；
- 是否有前后依赖。

默认：

```text
UI Batch：串行
共享账号/状态：串行
完全隔离 API Batch：可并行
```

---

# 9. 证据方案提前决定

Planning 对每条 Case 决定证据等级和逐项 Expected 关联。所有证据项必须使用对象形式，包含 `kind` 和 `expected_ids`，不能用自由文本代替绑定关系。

API 自动化固定使用 TypeScript、Vitest 和 Node 原生 `fetch`；UI 自动化固定使用 TypeScript 和 Playwright Test。每条自动化 Case 必须规划独立、Run 内的脚本目标，且路径按 `scripts/api/<Batch>/<Case>*.test.ts` 或 `scripts/ui/<Batch>/<Case>*.spec.ts` 组织。第一次执行前必须先创建正式脚本，再由对应 runner 执行。

```json
{
  "automation": {
    "required": true,
    "language": "typescript",
    "runner": "vitest",
    "driver": "node-native-fetch",
    "script_target": "scripts/api/B01/TC-API-001.test.ts",
    "script_strategy": "create_or_update"
  },
  "evidence_plan": {
    "level": "standard",
    "screenshots": [],
    "recording": false,
    "api": [{"kind":"request_response","expected_ids":["E1"],"redacted":true}],
    "network": [],
    "files": [],
    "read_back_required": false
  }
}
```

API 的 `read_back_required` 必须明确为 true 或 false；为 true 时还要在 `api` 中规划 kind 为 `read_back` 的证据。请求和响应证据必须明确 `redacted: true`。UI Case 至少规划一张关键断言截图；`critical` UI Case 还必须按 Case 录屏，视频不能替代截图。录屏字段只能是布尔值，不存在 Batch 级录屏。

人工 Case 使用 `automation: {"required": false}`，并明确 `manual_execution.reason`、`steps` 和 `result_entry`。

Planning 对每条 Case 决定：

- 哪些关键结果截图；
- 是否录完整流程；
- 是否保存 API request/response；
- 是否保存 Network；
- 是否保留特定日志；
- 是否验证下载文件；
- 是否数据库只读验证。

Runtime 只执行。

## 录屏

适合：

- P0 核心 E2E；
- 跨模块；
- 跨角色；
- 连续状态流；
- 操作顺序本身重要；
- 复杂 UI。

不默认录：

- 普通字段边界；
- 大量 API 参数组合；
- 简单 CRUD。

录屏只按 Case 规划；关键结果仍用截图。

---

# 10. Planning 必须把执行所需的原信息带下去

每条计划 Case 至少保留：

- Case ID；
- 已确认 Case 的标题、前置条件和测试数据；
- **原步骤（必须与已确认 Case 完全一致）**；
- **Expected（必须与已确认 Case 完全一致）**；
- **真正被测动作 `target_action`（必须来自已确认 Case）**；
- 主执行方式；
- 辅助验证；
- Batch；
- dependency；
- 数据需求；
- evidence plan。

不要只传一个摘要标题给 Runtime。

---

# 11. 输出

用户可读：

```text
deliverables/04-execution-plan.md
```

展示：

- 执行总览；
- Batch；
- UI/API/人工统计；
- 数据策略；
- 核心执行顺序；
- 证据策略；
- 需要用户重点确认的特殊安排。

详细机器计划：

```text
internal/execution/execution-plan.json
```

---

# 12. AI 自审

必须检查：

- 所有 Case 是否分配；
- UI Case 是否错误规划 API；
- 是否存在不必要双执行；
- 长业务链是否被拆碎；
- 删除类是否过早；
- 是否大量重复造数；
- 是否不应共享的数据被共享；
- Case 依赖是否遗漏；
- Evidence 是否遗漏；
- Batch 是否过大；
- 并发资格是否合理。

有问题先修，再审。

然后才让用户确认执行方案。

详细方法：

`references/execution-planning-method.md`

# 13. Planning 的来源绑定

`internal/execution/execution-plan.json` 必须绑定已经人工确认的正式 Case 集合，而不是由 Planning 自己声明“全部已分配”。

内部计划必须保存：

- `confirmed_case_ids`：与已确认 Case 集合完全一致；
- `confirmed_cases_sha256`：当前已确认 `internal/design/test-cases.json` 的绑定版本。

Planning Contract 会直接读取真实已确认 Case 文件：不仅 Case ID 集合必须完全一致，`steps / expected_results / target_action / preconditions / test_data` 也不得被 Planning 改写。Planning 只能增加执行方式、Batch、依赖、数据需求和 Evidence 方案等执行层信息。

每个 `expected_results` 还必须携带稳定 `id` 与可观察的 `expected`，因为 Runtime 按 Expected ID 做逐项 Actual/Evidence 对账。
