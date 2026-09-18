# Coverage Types

推荐 Coverage Type：

- `event_behavior`：业务 Event 的基本允许/结果；
- `field_rule`：必填、唯一、格式、范围等输入业务规则；
- `state`：某状态下行为；
- `transition`：状态迁移；
- `relation`：关系建立/修改结果；
- `relation_lifecycle`：失效、恢复、解绑、删除保护；
- `authorization`：角色/权限/授权规则；
- `data_consistency`：主记录、关系、统计、历史等一致性；
- `downstream_effect`：上游变化后的下游影响；
- `invariant`：长期不变量；
- `negative_business_rule`：明确禁止的业务行为；
- `failure_atomicity`：失败后的最终事实；
- `recovery`：异常到恢复连续性；
- `concurrency`：并发竞争；
- `stale_state`：旧页面/旧状态提交；
- `scope_isolation`：租户、组织、数据域等隔离；
- `long_flow`：长链连续性；
- `cross_module`：跨模块传播。

不是每个系统都有全部类型。

只对 Business Model 实际存在的机制建立 Coverage。
