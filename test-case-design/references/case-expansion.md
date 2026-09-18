# Case Expansion

## 1. 原则

先决定“需要哪些独立执行证据”，再写 Case。

## 2. Field Rule

优先：
- 有效等价类；
- 无效等价类；
- 边界前；
- 边界；
- 边界后；
- 必要的特殊值。

不要求无意义全排列。

## 3. Decision Rule

多条件共同决定输出时：
- 形成规则表；
- 合并业务结果完全相同且无独立风险的规则；
- 高风险组合保留独立 Instance。

## 4. State

至少：
- 允许迁移；
- 关键阻断迁移；
- 状态内关键动作；
- 迁移后下游。

## 5. Relation Lifecycle

按业务适用性：
- create；
- update；
- invalidate；
- recover；
- remove；
- delete protection。

## 6. Failure

失败不是“报错场景”，而是一个最终事实验证。

## 7. Recovery

恢复必须验证连续性，而不是只验证“再次成功”。

## 8. Long Flow

长链 Case 负责证明多个机制在真实业务链中能连续工作。
专项 Case 仍负责隔离高风险缺陷。
