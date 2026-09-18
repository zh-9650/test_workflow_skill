# 需求完整性检查

这份检查只用于内部自审，不直接替代人工可读的业务理解文档。

目标：避免“需求文档写了一个动作，所以默认所有相关场景都已经定义”。

每次业务理解至少检查以下维度，并在 `business-model.json` 的 `requirements_completeness_review` 中记录结果：

- `create_edit_delete`：创建、编辑、删除及失败后的最终事实；
- `state_transitions`：合法迁移、非法迁移、重复操作、恢复；
- `relationship_lifecycle`：建立、修改、失效、恢复、解绑、删除保护；
- `failure_atomicity`：失败后是否存在部分写入、半状态、脏关系；
- `recovery`：异常修复后是否自动恢复、是否需要再次操作；
- `history_current_fact`：当前配置变化是否改写历史事实；
- `authorization_scope`：权限、作用域、目标失效及多规则关系；
- `async_retry_idempotency`：异步处理中断、重试、重复请求、幂等；
- `long_flow_branches`：长流程分支、中断、取消、回退、重入；
- `cross_module_impact`：上游变化后哪些下游变化、哪些必须保持不变；
- `concurrency_stale_state`：并发修改、旧页面提交、确认期间事实变化；
- `uniqueness_reuse`：唯一值、删除后复用、同名新建是否形成新实体；
- `data_consistency`：主记录、子记录、关系、统计、索引、历史是否一致。

每个维度必须是以下三种结果之一：

- `covered`：已从证据或当前模型中得到足够定义；
- `question_raised`：发现会影响业务结果的缺口，已经形成待确认问题；
- `not_applicable`：当前业务确实不适用，并说明原因。

不能用空列表或一句“已检查”代替。`covered` 必须能指向证据或业务模型，`question_raised` 必须能指向待确认问题。


## 检查依据

每一个维度，无论结论是“已定义”“已形成待确认问题”还是“当前不适用”，都必须记录本次判断实际核对过的资料或业务模型位置。

不能只写“当前不适用”而不说明根据什么判断。
