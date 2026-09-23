# 执行规划方法

## 1. 目标驱动，不以“哪个更容易自动化”驱动

Case 测的是前端交互，就算 API 更容易也不能换成 API。

Case 测的是服务端组合规则，大量 UI 点击没有价值时可以 API 主执行。

## 2. Batch 是业务和数据边界

好的 Batch 通常满足：

- 同一业务目标；
- 数据生命周期连续；
- 角色切换可理解；
- 不需要频繁重建上下文；
- 证据可以一起组织。

拆分：

- 数据互相污染；
- 破坏性操作；
- 权限负向测试；
- 执行模式差异很大；
- 可以独立并行。

## 3. 数据需求只规划，不在这里造数

Planning 写清：

- 要什么对象；
- 目标状态；
- 是否新建；
- 是否可以复用基础账号/角色/租户；
- 对应 Case。

真正创建在 Data Readiness。

## 4. 证据按 Expected 规划

先问：

> 这个 Expected 最可信的观察点是什么？

UI 截图不一定能证明数据库业务事实；API 200 也不一定能证明最终异步成功。

辅助验证只在有价值时使用，不为了“证据多”堆东西。

## 5. 核心业务链

完整业务流程最好：

- 同一 Batch；
- 一个 Worker；
- 串行；
- 每个 critical UI Case 单独录屏；
- 关键节点截图；
- 必要的 API/Network read-back。

自动化栈是固定契约：API 使用 TypeScript + Vitest + Node 原生 fetch；UI 使用 TypeScript + Playwright Test。每条自动化 Case 在首次执行前必须先写入其唯一 `script_target`，随后使用指定 runner 正式运行。证据项用 `kind` 和 `expected_ids` 绑定到具体 Expected；API 请求/响应必须脱敏，并显式决定是否需要 read-back。

## 6. 人工 Case

只有真实外部依赖：扫码、硬件、人工审批、主观视觉。

规划时写清：

- 人需要做什么；
- Agent 等什么结果；
- 如何回填 Actual/Evidence；
- 后续如何继续。
