# 业务理解 3.3 + 测试点 1.1 到测试用例：唯一有效事实交接

## A. 输入有效性（先审，不得预设都已确认）

必须先定位同版本 `business-model.json`、`effect-ledger.json`、`test-points.json`、业务理解与测试点的审查结论、原始 PRD/原型/最后有效人工裁定。对不上时标记候选受限；若上游有影响业务预期的阻断问题，相关用例只可列候选/返回上游，其他确定性用例可以独立推进。

优先级：授权的最新人工裁定 > 现行正式 PRD/验收规则 > 可靠原型行为线索；历史 AI 产物、源码观察和旧 PRD 不得改变现行产品规则。`effect-ledger.clauses[].scope` 为 `active|excluded|superseded|unresolved|dependency`，只为 active/有界 dependency 的已确定结果设计正式预期。原型脚本的模拟返回不等于后端真实成功。

3.3 `critical_paths` 定义完整用户任务、停止/失败/交织和终态；`discriminators` 定义来源已支持的条件—不同结果；测试点 1.1 `branch_design` 是对应的义务、分支与要求的变体，不得被 `1 TP→1 Case` 取代。

## B. 每条分支怎样落地

读取 `branch_design.branches[]`：
- `branch_id`、所属 TP/有效子条款、`condition`、`expected_result`、`observable_fact` 和 `certainty`。
- `case_handoff.variation_axis`、`data_condition`、`oracle`、`required_variations`。
- `discriminator_reviews` 的正/反两侧必须都出现，并有可区分的实例和判定。
- `path_reviews` 的终态、中断、交织必须分别有可追溯实例；完整链另需连续操作场景，不能只用几个互不相关的单点用例代替。

阶段产物映射 `分支 → instance_id → assertion_id → oracle 证据`。同一模板允许复用但不同互斥条件不能共用一次实例来冒充两种结果；同一分支允许多个实例覆盖必要位置/数据组，但不能用一个分支的断言挂上另一个分支 ID 造成假覆盖。

上游 `required_variations` 有时是宽泛的维度词；需要对照上游原文细化该维度内的**实际有差异的代表取值/位置**，并在 `variation_reviews` 登记。不是要求每个“维度标签”自动多生一条用例，更不能静默丢掉它。

## C. 上游缺失、错误、变化的处置

- 当前业务规则不清：回业务理解 3.3，写出具体决定条件、两种可能后果、查过的原始来源、受影响用例；不选一个自认为合理的预期。
- 缺一个能独立出错的测试机制：回测试点 1.1，建立验证义务/分支；不偷偷往 Case 中新增一条独立机制。
- 仅具体值、状态组合、重试次数、入口操作需要展开：在用例阶段推导具体实例。
- 旧功能取消/替代：不得因为旧用例、旧原型存在就复活；可以设计“不再进入旧流程”的负向约束，但必须有现行裁定依据。
- 变更发生：按子条款/分支 ID 使依赖的 Case 和 Oracle 失效，局部回归；禁止沿用旧签核结果。

## D. 门禁不是人类业务裁定

旧 `case_contract.py` 检查主项/实例/TP/断言/版本等结构；新 `branch_case_audit.py` 检查 1.1 的确定性分支、变体、正反辨别、关键链、数据与 Oracle 是否有承接，校验来源标识是否落到正确范围。它们都**不能**证明样本是否符合某法规、文本预期是否业务正确或真实系统是否通过；必须在实际来源反查/样例盲审/数据准备与真实执行中验证。
