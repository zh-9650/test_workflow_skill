# 独立业务分支、测试点粒度与用例可展开性（强制方法）

## 1. 四层不可偷换

`有效业务子承诺 → 验证义务（Coverage Obligation）→ 决定性条件/业务结果分支（Decision Branch）→ 测试点（TP）→ 用例（TC）`

- **义务**描述需要证明的正确性，例如“重试必须使用本次尝试的独立协议”。
- **分支**描述何种关键条件对应何种正确结果。可以是“允许”与“拒绝”，也可以是成功变化/失败不改变/在途版本保持/新请求版本变化，**必须说得出结果差异**；多个同义值或单纯数据样本不强拆。
- **测试点**是对一项可独立失效的业务机制的验证目标；允许收纳多个分支。拆分/合并时每个分支依然在 `branch_design` 中，并指向实际 TP。
- **用例**才确定测试数据、具体操作步骤、观察手段和断言。禁止 `一条TP只能转一条TC` 的机械想法。

## 2. 先判断“什么值得独立失败”，再谈拆合

按顺序问：

1. **业务责任是否不同**：例如协议是否完整、字段枚举是否合法、跨字段是否自洽，属于可能分别失效的三个机制。即使它们最终都返回技术失败，也不能一概合成“协议错误”。
2. **决定结果的条件是否不同**：同一校验对 5 个协议块的缺失，若错误表现/检测位置可不同，可保留一个“完整性机制”TP，但要在分支或 `case_handoff.required_variations` 中逐块保留；不能只写“任意一块”。
3. **业务副作用能否分别错**：一次编辑可能同时影响内容、状态、引用、下游可见性、历史审计；如果它们具有独立判别价值，应分别建立义务/测试点，不用一个“编辑成功”掩盖。
4. **是否真是数据例子而非新机制**：同一必填规则的 `空字符串/纯空格` 是数据条件变种；如果正规化流程有不同业务效果，则单独保留分支；不是默认按每个字符值拆 TP。
5. **跨模块长链是否引入独立错误**：原子 TP 不能代替多跳配置生效、状态传播、权限撤回、失败恢复等连续性；额外使用 `composite_flow`，但不能替代中间原子点。

输出拆合理由不是“粒度适中”，而是：分开会发现什么独立错误；合并时如何保证所有结果分支及将来 TC 变体仍被测试到。

## 3. 四条发现路径与质量守恒

- A **业务事实/状态/关系/不变量**：从 3.3 模型与有效子句得到正确性义务。
- B **功能与入口**：从真实原型、PRD、控件变化得到独立操作和基础路径；没有证据不得虚构功能。
- C **用户长链**：从 `critical_paths` 和真实任务推演起点、相邻步骤、最终成功/失败/停止/再次进入、旧/新版本并存、依赖变化。
- D **错误行为挑战**：针对高风险机制思考“哪一种看似成功但业务错误的实现会逃过这些 TP”；若仍逃过，补查来源并追加分支/观察证据。假设错误不是已复现 Bug。

先形成**候选义务集合**再去重；去重时保留产生它的所有来源和责任，尤其不得将“应改变”与“必须保持”合并成一个含糊的“正常”。

## 4. 分支完整性审查顺序

1. 上游有效子句逐个定位当前正确性义务；排除项不得重生。
2. 上游已确认正反条件逐个定位**两侧**具体业务分支；仅写两个名称、都预期“正常”不算通过。
3. 上游高风险关键路径逐个定位用户终态；有停止/重试/失败应保存对应终态，有版本/授权交错应保存交错效果。
4. 每个已有 TP 必须能至少定位一个有效分支；每项覆盖义务都要有分支或明确待确认/排除去向。
5. 当 TP 合并若干义务，按 **分支 ID → TP ID → TC 准备/断言轴** 复查，尤其检查单个弱用例是否遮蔽其他结果。
6. 历史测试点回归：旧版独有的重要 TP 逐条登记为“等价保留/合理合并且变体保留/正式排除/重复数据项/新增待澄清/真实遗漏”。不可按 273 vs 128 直接判胜负。

## 5. `branch_design` 结构说明

在**原有** `internal/design/test-points.json` 增加 `branch_design`，不改变既有 `coverage_obligations`、`test_points` 和 `design_questions`；这不是另建一个互相矛盾的“事实源”。新正式设计 `schema_version: "1.1"`。

- `coverage_plan`: 每个覆盖义务一条：`coverage_id`, `mode: single|conditional|not_covered`, `branch_ids`。有两类互相影响正确结果时用 `conditional` 并保留至少两分支；简单承诺用 `single`。`not_covered` 只给已排除、未决或不适用义务，不得伪称 covered。
- `branches`: 每项 `branch_id`, `coverage_ids`, `test_point_ids`, `claim_ids`, `condition`, `expected_result`, `evidence_basis`, `observable_fact`, `certainty: confirmed|derived`, 必要时 `derivation`, 高风险 `false_success`, `case_handoff: {variation_axis,data_condition,oracle,required_variations?}`。`claim_ids` 必须指向 3.3 有效子句；未知结果不生成确定可执行分支。
- `claim_dispositions`: 每项 3.3 `clauses` 逐条 `claim_id,decision: covered|pending|excluded|dependency,coverage_ids,question_id?,reason?`。现时效力由 3.3 来源决定，不能修改成另一套“测试侧生效状态”。
- `discriminator_reviews`: 逐项记 3.3 正反辨别题，`status: covered|pending|excluded,branch_ids,question_id?,reason?`。确定题至少两条结果有区别的分支。
- `path_reviews`: 逐项记 3.3 关键路径，`status: covered|pending|excluded,terminal_branch_ids,interruption_branch_ids,interleaving_branch_ids,question_id?,reason?`。只有上游存在相应中断/交织时才强制对应字段。
- `retired_marker_reviews`（有命中时）：`branch_id,marker_id,assessment: negative_constraint|historical_context|unrelated_phrase,evidence`。匹配已取消词语仅触发**人工核实**，不自动当缺陷，也不自动删除“不得发生已取消操作”这样的正确负向约束。

`branch_audit.py` 对 ID、双向关系、基础字段、来源效力、至少两侧的确证正反例、关键链终态及一部分已取消术语进行**有限、可重复的**检查；不能检验中文业务推理真假、证明未知分支为零或替代独立 Reviewer。

## 6. 用例可展开性抽查，不要伪造下游执行

至少从实际项目中抽取不同类型：基础 CRUD、数值/文本边界、权限、状态迁移、跨模块链路、异步中断或重试、版本并存、AI 业务结果/来源绑定。对每项试写 `所需数据条件、需要的分支变体、主要行动、关键断言、观察不足`。若不能形成不同于“点开—成功”的可判别断言，回到 TP 补齐；如发现业务事实本身未知则回 3.3。这个抽查仍不是完整 TC Skill 正式交付。

## 7. 新增的防“来源挂错”检查

如果 3.3 的 `clauses[].model_refs` 与对应覆盖义务的 `source_model_refs` 没有直接机制交集，`claim_dispositions` 必须提供 `trace_explanation`，说明可复查的间接承接（如原始事件结果由另一个规则/关系来验证），不能只把一个来源 ID 挂到不相关的 TP。上游 `discriminators[].clause_refs` 与关键任务 `critical_paths[].clause_refs` 若实际提供，审查其承接的分支来自同一有效子句；不同版本、角色、作用域的类似措辞不能冒名顶替。
