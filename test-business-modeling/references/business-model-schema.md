# 业务模型数据结构（供 Agent 内部追踪）

`internal/business/business-model.json` 是业务理解的正式结构化输出。它主要供自动化校验、下游测试点设计、用例追踪和执行对账使用；测试人员与业务方主要阅读主业务理解报告 `deliverables/01-business-understanding.md` 和审查摘要 `01-business-understanding-review.md`。

---

## 1. 顶层结构

```json
{
  "schema_version": "3.1",
  "model_version": "BM-001",
  "scope": {
    "in_scope": ["standard-items", "archive-items"],
    "dependency_scope": ["auth-service", "deployment-service"],
    "out_of_scope": ["production-billing"]
  },
  "source_registry": [
    {
      "source_id": "SRC-001",
      "type": "prd",
      "title": "项目需求规格说明书 v1.0"
    }
  ],
  "capabilities": [],
  "modules": [],
  "business_objects": [],
  "state_machines": [],
  "relationships": [],
  "mechanism_link_exceptions": [],
  "events": [],
  "invariants": [],
  "rules": [],
  "cross_module_flows": [],
  "unknowns": [],
  "blocked_scopes": [],
  "requirements_completeness_review": {},
  "presentation_sync": {},
  "self_review": {}
}
```

> **注意**：以下所有具体字段示例中的业务规则仅用于说明 Schema 的承载规范；实际测试项目中所有规则必须由当前任务的有效资料支持，严禁将假设直接写入正式模型。

本文中的 JSON 片段用于解释各元素，不是可直接导入的完整模型；实际模型还须满足完整合同、来源、ID 和引用要求。保留已有字段和来源状态语义，不为展示强制迁移旧模型。任务、输入边界、配置语义、完成条件与保持项优先落在已有事件/规则/关系/流程及来源中；新字段须有实际消费目的，不能靠加字段证明分析完成。**3.1 新增的 `mechanism_links` 是实际被 Contract 消费的每事件状态/关系适用性决策，`mechanism_link_exceptions` 是未直接连接本期事件的机制的证据化例外，不是自评标签。**

---

## 2. 核心元素与内部能力映射

### 2.1 内部能力索引
主报告用中文任务和功能讲解业务；内部 `capabilities` 数组聚合关联机制，标识如 `CAP-xxx`。正式模型中每项至少引用一个实际事件、规则、不变量、流程或迁移，不能只挂模块。索引不能替代任务的角色、输入、条件、分支、结果及依赖分析，独立能力不强制填不存在的上下游或技术提供方。

这些标识服务于内部追踪，不要求直接展示在人工报告中。正文先用中文业务名称、图与讲解呈现用户任务及结果；完整映射放追踪附件或 HTML 的可展开区。人工呈现规范见 `human-readable-reporting.md`。

```json
{
  "capability_id": "CAP-001",
  "name": "批次条目激活与流转能力",
  "user_task": "条目管理与批量激活",
  "applies_to_refs": ["EV-001", "RULE-001", "FLOW-001"],
  "proof_boundary": {
    "substantive_facts": ["条目 state 持久化更新为 active 并可从单条与列表接口读回"],
    "superficial_traps": ["HTTP 200 返回 success 但未落库", "前端仅弹出 Toast 提示"]
  },
  "source_refs": ["SRC-001"]
}
```

在下游 `test-point-design` 读取时，通过这一映射关系直接索引到机制级定义，防止模型与清单脱节。

当前下游 `model_refs()` 不识别能力索引 ID；覆盖义务通过 `source_model_refs` 引用实际机制，测试点通过 `source_coverage_ids` 等现有字段承接。能力索引保留导航作用，不改下游合同来容纳一个展示编号。

### 2.2 业务对象 (Business Object)
```json
{
  "object_id": "OBJ-001",
  "module_id": "M01",
  "name": "批次条目 (Batch Item)",
  "business_purpose": "承载批次内标准或归档业务数据的执行单元",
  "stable_identity": "由服务生成的 item_id 作为唯一稳定标识，业务维度 namespace + external_key 保证唯一性",
  "key_fields": ["item_id", "namespace", "external_key", "name", "kind", "state"],
  "key_rules": ["RULE-001"],
  "state_machine_id": "SM-001",
  "source_refs": ["SRC-001"]
}
```

### 2.3 状态机与跃迁 (State Machine & Transition)
```json
{
  "state_machine_id": "SM-001",
  "object_id": "OBJ-001",
  "states": [
    {"state_id": "S1", "name": "草稿 (draft)", "business_meaning": "条目创建完成待激活"},
    {"state_id": "S2", "name": "激活 (active)", "business_meaning": "已激活可参与发布"}
  ],
  "transitions": [
    {
      "transition_id": "TR-001",
      "from": "S1",
      "action": "执行激活操作",
      "to": "S2",
      "guard": "条目状态必须为 draft 且操作人具备 tester 权限",
      "effects": ["状态持久化更新为 active", "记录激活时间与操作版本"],
      "source_status": "CONFIRMED",
      "source_refs": ["SRC-001"],
      "derived_from": []
    }
  ],
  "invalid_or_blocked_transitions": [
    {
      "from": "S2",
      "action": "重复激活",
      "expected_block": "返回 409 冲突，状态保持 active 不变"
    }
  ]
}
```

### 2.4 关系生命周期 (Relationship Lifecycle)
```json
{
  "relationship_id": "REL-001",
  "name": "条目归属批次 (Item Belongs To Batch)",
  "from_object_id": "OBJ-001",
  "to_object_id": "OBJ-002",
  "cardinality": "N:1",
  "source_of_truth": "Item 对象的 batch_id 字段",
  "maintenance_owner": "批次管理模块",
  "create": {"applicable": true, "behavior": "条目创建时必须指定归属 batch_id"},
  "update": {"applicable": false, "behavior": ""},
  "invalidate": {"applicable": true, "behavior": "批次归档后，条目关联转为历史只读状态"},
  "recover": {"applicable": false, "behavior": ""},
  "remove": {"applicable": true, "behavior": "仅当批次处于草稿且无活跃条目时允许删除"},
  "source_status": "CONFIRMED",
  "source_refs": ["SRC-001"],
  "derived_from": []
}
```

### 2.5 业务事件与证明边界 (Business Event)
事件必须覆盖通用推导要素；若涉及复杂处理链或证明边界，可在契约允许的扩展字段中承载：

```json
{
  "event_id": "EV-001",
  "module_id": "M01",
  "name": "激活条目",
  "actors": ["fixture-tester"],
  "trigger": "用户在页面点击【激活】或调用 POST /api/items/:id/activate",
  "preconditions": ["登录会话有效", "条目当前状态为 draft"],
  "inputs": ["条目 ID"],
  "outputs": ["HTTP 200 及包含最新 active 状态的条目详情"],
  "direct_changes": ["条目 state 更新为 active", "更新 update_at 事实"],
  "state_changes": ["TR-001: 满足前置约束后 S1 -> S2"],
  "relationship_changes": [],
  "mechanism_links": {
    "state": {"impact": "change", "refs": ["TR-001"], "rationale": "有效激活使草稿转换为激活状态"},
    "relationship": {"impact": "not_applicable", "refs": [], "rationale": "激活不会建立、读取或修改其他对象的归属关系"}
  },
  "downstream_impacts": ["解除发布前置条件阻断，允许发布操作"],
  "must_not_change": ["同一命名空间下的其他条目", "条目的创建历史与原始 namespace"],
  "failure_conditions": ["非 draft 状态调用", "操作账号未授权", "条目 ID 不存在"],
  "failure_final_facts": ["状态保持不变，不产生半激活记录，返回 409 或 403 错误响应"],
  "source_status": "CONFIRMED",
  "source_refs": ["SRC-001"],
  "derived_from": [],
  "proof_boundary": {
    "required_facts": ["调用后通过单条及列表接口读回状态为 active", "页面刷新后读回为 active"],
    "insufficient_evidence": ["HTTP 200 返回 success 但未核实持久化状态", "界面仅弹出 Toast 提示"]
  }
}
```

### 2.5.1 事件—生命周期显式关联（3.1 必填）

每条事件的 `mechanism_links.state` 和 `.relationship` 都必须有 `impact`、`refs`、`rationale`：

- `change`：状态必须指向具体 `TR`；**对象首次创建直接建立初态**等不经状态机迁移的情形，可指向 `SM` 并解释 `transition_not_applicable_reason`。关系改变必须指向真实 `REL`。对应的 `state_changes` / `relationship_changes` 列表不能空。
- `read_or_guard`：只读取或检查现有状态/关系，不修改。引用真实 `SM/TR/REL` 并在对应变化说明列表中写“检查什么、禁止什么变化”；不能只写“按需校验”。
- `not_applicable`：refs 和对应变化数组为空，`rationale` 写出理由。只读事件如**确实**不涉及状态机或关系，不得强造关联。
- `pending`：refs 和变化数组为空，填写 `question_ids` 指向 `unknowns` 中 `pending` 问题；影响成功预期的范围必须按原有阻断规则处理。不能把“未知”记作不适用。

示例（第一次创建即进入初态，并无 `TR-000` 可引用）：

```json
"mechanism_links": {
  "state": {
    "impact": "change", "refs": ["SM-001"],
    "rationale": "新条目第一次建立时取得 draft 初态",
    "transition_not_applicable_reason": "对象创建前不存在旧状态，因此没有从旧状态触发的迁移"
  },
  "relationship": {
    "impact": "not_applicable", "refs": [],
    "rationale": "本事件没有跨对象关联"
  }
}
```

正式模型 `schema_version: "3.1"`；3.0 只可通过 `--allow-legacy-schema` 检查旧结构，返回不可确认状态。字段齐全及引用正确**不能单独证明**业务推导正确。

为避免状态机、迁移或关系在重构中变成“孤岛”，被模型定义却未被任一事件链接的 `SM/TR/REL`，必须在顶层 `mechanism_link_exceptions` 登记并引用来源：

```json
"mechanism_link_exceptions": [
  {"ref": "TR-002", "reason": "该迁移由已确认的上层服务独立完成，本功能仅引用其完成后的结果", "source_refs": ["SRC-001"]}
]
```

此类例外由审查者核对业务效力，不得为了让结构校验通过而虚构理由。`SM` 被某事件引用其 `TR` 时视为已连接；但其他未连接的 `TR` 仍需逐条解释。参见 [业务机制完整性门禁](mechanism-integrity-gate.md)。

### 2.6 业务规则与配置生效闭环 (Rule)
每条规则必须包含 `description`、`applies_to_refs` 和来源信息。若有控制策略生效闭环分析，在 `policy_actuation` 扩展字段中说明：

```json
{
  "rule_id": "RULE-001",
  "description": "条目激活规则：仅处于 draft 状态的条目允许执行激活，成功后状态持久化为 active",
  "applies_to_refs": ["OBJ-001", "EV-001", "SM-001"],
  "source_status": "CONFIRMED",
  "source_refs": ["SRC-001"],
  "derived_from": [],
  "policy_actuation": {
    "scope_type": "all_subsequent_executions",
    "effective_point": "即时持久化，当前请求生效",
    "invariant_guarantee": "旧有条目历史不变"
  }
}
```

### 2.7 跨模块流程 (Cross Module Flow)
```json
{
  "flow_id": "FLOW-001",
  "name": "条目全生命周期流 (Item Complete Lifecycle Flow)",
  "scope": "cross_module",
  "steps": ["EV-001", "EV-002"],
  "branches": [
    {
      "branch_id": "BR-01",
      "condition": "条目创建时 kind 为 archive",
      "divergence_step": "EV-001",
      "path_description": "走归档特殊处理流"
    }
  ],
  "failure_paths": [
    {
      "step": "EV-001",
      "failure_scenario": "创建返回 422",
      "final_state": "条目未生成，事务干净回滚"
    }
  ],
  "recovery_paths": [
    {
      "trigger": "修复部署后",
      "recovery_action": "重新发起合法创建请求并读回"
    }
  ],
  "source_status": "CONFIRMED",
  "source_refs": ["SRC-001"],
  "derived_from": []
}
```

### 2.8 待确认问题
支持旧有格式，并支持显式表示暂不推荐的 `recommendation_status: "not_recommended"`。当资料不足以定界方案空间时，应先澄清系统能力承诺，支持开放式提问，避免强行设置二选一伪选择题：

结构化问题继续保留稳定标识及来源引用；给人看的问题须补齐场景、已知规则及相关原文/摘要、具体缺口、决定后果和明确问法。来源展开为文档名称、章节与定位，不能把 JSON 直接排版成问题。写法见 `human-readable-reporting.md`，不为展示需求强制迁移旧合同字段。

```json
{
  "unknown_id": "U-001",
  "category": "blocking_business",
  "issue_type": "missing_rule",
  "question": "系统承诺支持哪些 PDF 内容形态？默认解析与扩展配置是否支持纯图片扫描件的 OCR 识别？",
  "why_needed": "PRD 仅笼统提及支持 PDF 格式，需先澄清基础能力承诺，方能确定文件上传与解析事件的合法输入边界与断言预期",
  "evidence_checked": ["SRC-001"],
  "answer_mode": "open",
  "recommendation_status": "not_recommended",
  "recommendation_reason": "当前原始资料无任何扫描件及 OCR 相关的规格或工程实现依据，需产品先定界能力承诺，暂不预设选项限制决策空间",
  "impact_summary": "决定是否需要为纯图片扫描件设计独立支持链路、降级提示还是报错拦截用例",
  "depends_on": [],
  "status": "pending",
  "affects_expected": true,
  "affected_scopes": ["standard-items"],
  "source_refs": []
}
```

---

## 3. 需求完整性检查、同步检查与自审

这些结构标记沿用现有合同。字段合法和 `passed` 不证明独立审查真实发生、规则已全部确定、图文同源或系统已实测。实际来源、内容审查、处置和复核依据见主报告及审查摘要。

### 3.1 需求完整性检查 (`requirements_completeness_review`)
必须包含全部 13 个原生检查维度，且每项给出明确依据（详见 `references/requirements-completeness-review.md`）：
```json
{
  "status": "passed",
  "dimensions": [
    {
      "dimension": "relationship_lifecycle",
      "applicable": true,
      "status": "covered",
      "evidence_refs": ["SRC-001"],
      "model_refs": ["REL-001"],
      "question_ids": [],
      "reason": ""
    }
  ]
}
```

### 3.2 人工文档与内部数据同步 (`presentation_sync`)
```json
{
  "status": "passed",
  "checks": {
    "main_document_updated": true,
    "review_document_updated": true,
    "pending_questions_reflected": true,
    "model_consistency_checked": true
  }
}
```

### 3.3 强制自审标记 (`self_review`)
```json
{
  "status": "passed",
  "checks": {
    "scope_checked": true,
    "objects_checked": true,
    "states_checked": true,
    "relationships_checked": true,
    "events_checked": true,
    "invariants_checked": true,
    "flows_checked": true,
    "source_status_checked": true,
    "unknowns_checked": true,
    "requirements_completeness_checked": true,
    "readability_checked": true,
    "presentation_sync_checked": true
  }
}
```

---

## 4. 交付与下游承接对照表

| 业务内容 | JSON 承载位置 | 主报告展示位置 | 下游（如 `test-point-design`）怎样读取 |
|---|---|---|---|
| **核心能力及任务（内部索引）** | `capabilities[].applies_to_refs` 引用具体事件、规则、不变量或流程 | 以中文任务名、总览图与讲解呈现；完整映射按需展开 | 按索引读取实际机制，正式测试点引用具体机制 ID |
| **输入支持边界** | `events[].inputs`、`events[].failure_conditions` | 对应任务的输入条件、分支及限制讲解 | 针对不同输入变体与边界提取测试点 |
| **配置控制与生效闭环** | `rules[].policy_actuation`、关联事件 | 配置控制策略与生效闭环小节 | 覆盖配置保存 vs 运行时生效、存量 vs 增量断言 |
| **真实完成与证明边界** | `events[].proof_boundary`、`events[].outputs` | 对应任务的图解与判断依据说明；复杂比较才用表 | 制定实证检查点与排除虚假成功判定 |
| **未知项与冲突** | `unknowns` 集合 | 正文标注与文末待确认问题 | 识别未决范围，避免擅自为未决问题编写假想用例 |
| **审查与修订历史** | `01-business-understanding-review.md` | 审查摘要文档中的修订记录与复核清单 | 追溯受影响范围与变更影响 |

### 业务分析内容怎样落到现有结构

- 业务背景、使用环境、相关方、风险排序和分析例子：在主报告对应任务处说明，审查摘要保留依据与未决；不为这些说明强造对象或状态机。
- 条款中的具体承诺、禁止项、交互和质量要求：进入 `rules[].description` 及其 `applies_to_refs`，或实际对应事件/状态/关系；同一来源的多个要求分别保留含义，不强制一条来源一个事件。
- 条件组合和分支：可在已有规则描述、事件的条件/变化/失败字段内明确写成“条件→结果”，多项之间有清楚对应；复杂时拆成关联规则。不能把条件和结果写成无法对应的两个无序集合。决策表放正文/审查区时，规则含义仍同步进模型。
- 来源要求的承接：在现有工作记录或审查摘要中定位“来源及具体要求→模型中的实际含义/未决/排除依据”。此核对没有新的机器字段，不由脚本证明。
- 启发式风险不冒充 `CONFIRMED`；只有查证或有效裁定产生的事实进入正式规则。业务未知继续进入 `unknowns`，技术观察入口待定按实际影响记录。

本次不增加强制 JSON 字段，不改变下游 `model_refs()`；测试点仍引用已有事件、规则、迁移等机制。新增分析不能只留在叙述附件而未传递实际业务规则。

### 证明字段的校验范围

能力索引的示例证明字段使用 `substantive_facts` / `superficial_traps`，现有脚本在该对象存在时检查列表和字符串；事件示例的 `required_facts` / `insufficient_evidence` 是扩展说明，目前没有相同的自动校验。不要把两个位置或字段名称混用，也不声称所有证明内容已被脚本验证。语义审查应检查重要结果在关联机制中的实际承接，不要求每层重复同一份证明。

旧模型可以没有新增扩展字段；新增严格规则前须明确适用条件、调用方和向后兼容。阶段①的工作记录无独立机器合同，不引入强制意图标签。人工确认继续由 Router 绑定三份正式文件及版本；上游变更后的重审和下游失效沿用现有机制，不在模型新增第二套确认布尔值。
