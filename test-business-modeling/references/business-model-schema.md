# Business Model Schema

`internal/business/business-model.json` 是测试点设计的正式结构化输入。它主要给 Skill、结构校验与关联追踪使用；测试人员主要阅读 `deliverables/01-business-understanding.md` 和审查摘要。

推荐结构：

```json
{
  "schema_version": "3.0",
  "model_version": "BM-001",
  "scope": {
    "in_scope": [],
    "dependency_scope": [],
    "out_of_scope": []
  },
  "source_registry": [],
  "modules": [],
  "business_objects": [],
  "state_machines": [],
  "relationships": [],
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

## 业务事实来源

重要规则、状态迁移、关系、业务事件、流程和不变量需要标记：

```text
CONFIRMED
DERIVED
TEST_BASELINE
IMPLEMENTATION_DETAIL
```

真正未确定、且不同答案会改变业务结果的内容不要先写成事实。人工文档中列为“待确认问题”，内部结构化数据记录在 `unknowns`。

`DERIVED` 必须写 `derived_from`，说明由哪些已知事实推导。

## State Transition

```json
{
  "transition_id": "TR-001",
  "from": "S1",
  "action": "...",
  "to": "S2",
  "guard": "...",
  "effects": [],
  "source_status": "CONFIRMED",
  "source_refs": ["SRC-001"],
  "derived_from": []
}
```

## Relationship

```json
{
  "relationship_id": "REL-001",
  "name": "...",
  "from_object_id": "OBJ-001",
  "to_object_id": "OBJ-002",
  "cardinality": "1:1 | 1:N | N:M | derived",
  "source_of_truth": "...",
  "maintenance_owner": "...",
  "create": {"applicable": true, "behavior": "..."},
  "update": {"applicable": true, "behavior": "..."},
  "invalidate": {"applicable": true, "behavior": "..."},
  "recover": {"applicable": true, "behavior": "..."},
  "remove": {"applicable": true, "behavior": "..."},
  "source_status": "CONFIRMED",
  "source_refs": ["SRC-001"],
  "derived_from": []
}
```

## Business Event

```json
{
  "event_id": "EV-001",
  "module_id": "M01",
  "name": "...",
  "actors": [],
  "trigger": "...",
  "preconditions": [],
  "inputs": [],
  "outputs": [],
  "direct_changes": [],
  "state_changes": [],
  "relationship_changes": [],
  "downstream_impacts": [],
  "must_not_change": [],
  "failure_conditions": [],
  "failure_final_facts": [],
  "source_status": "CONFIRMED",
  "source_refs": ["SRC-001"],
  "derived_from": []
}
```

## Flow

```json
{
  "flow_id": "FLOW-001",
  "name": "...",
  "scope": "module | cross_module",
  "steps": ["EV-001", "EV-002"],
  "branches": [],
  "failure_paths": [],
  "recovery_paths": [],
  "source_status": "CONFIRMED",
  "source_refs": ["SRC-001"],
  "derived_from": []
}
```

## 待确认问题

```json
{
  "unknown_id": "U-001",
  "category": "blocking_business | non_blocking_business | implementation | ui | external_dependency",
  "issue_type": "missing_rule | source_conflict | scope | ambiguous_behavior | dependency | implementation | ui | external_dependency",
  "question": "...",
  "why_needed": "...",
  "evidence_checked": ["SRC-001"],
  "answer_mode": "choice | open",
  "options": [
    {"option_id": "A", "description": "...", "impact": "..."},
    {"option_id": "B", "description": "...", "impact": "..."}
  ],
  "recommended_option": "B",
  "recommended_answer": "...",
  "recommendation_reason": "...",
  "impact_summary": "不同答案会影响哪些状态、关系、流程或范围",
  "depends_on": [],
  "status": "pending | resolved | out_of_scope",
  "affects_expected": true,
  "affected_scopes": ["M01"],
  "source_refs": [],
  "answer": "..."
}
```

要求：
- 业务类问题先查证再提问，`evidence_checked` 不能为空；
- `source_conflict` 至少比较两份证据；
- 选择题每个选项都写清业务影响；
- 推荐方案只是建议，不会自动变成正式规则；
- 用户批量回复后，更新 `answer/status`，并同步回写受影响的状态、关系、事件、规则或流程。

## 需求完整性检查

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

具体维度见 `references/requirements-completeness-review.md`。

## 人工文档同步检查

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

它表示本轮修改已经同步到人工主文档、审查摘要和内部模型。人工确认状态不写在这里，由流程状态统一记录，避免两套确认结果互相冲突。

## Self Review

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
