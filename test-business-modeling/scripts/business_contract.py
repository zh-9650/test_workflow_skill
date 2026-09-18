import argparse
import json
from pathlib import Path

SOURCE_STATUS = {"CONFIRMED", "DERIVED", "TEST_BASELINE", "PENDING", "IMPLEMENTATION_DETAIL"}
UNKNOWN_CATEGORIES = {"blocking_business", "non_blocking_business", "implementation", "ui", "external_dependency"}
UNKNOWN_STATUS = {"pending", "resolved", "out_of_scope"}
ISSUE_TYPES = {"missing_rule", "source_conflict", "scope", "ambiguous_behavior", "dependency", "implementation", "ui", "external_dependency"}
SELF_CHECKS = {
    "scope_checked", "objects_checked", "states_checked", "relationships_checked",
    "events_checked", "invariants_checked", "flows_checked", "source_status_checked",
    "unknowns_checked", "requirements_completeness_checked", "readability_checked",
    "presentation_sync_checked",
}
LIFECYCLE_FIELDS = {"create", "update", "invalidate", "recover", "remove"}
COMPLETENESS_DIMENSIONS = {
    "create_edit_delete",
    "state_transitions",
    "relationship_lifecycle",
    "failure_atomicity",
    "recovery",
    "history_current_fact",
    "authorization_scope",
    "async_retry_idempotency",
    "long_flow_branches",
    "cross_module_impact",
    "concurrency_stale_state",
    "uniqueness_reuse",
    "data_consistency",
}
COMPLETENESS_STATUS = {"covered", "question_raised", "not_applicable"}


def fail(path, msg):
    raise AssertionError(f"{path}: {msg}")


def text(v):
    return isinstance(v, str) and bool(v.strip())


def ids(items, key, path):
    out = []
    for i, item in enumerate(items):
        if not isinstance(item, dict):
            fail(f"{path}[{i}]", "object required")
        value = item.get(key)
        if not text(value):
            fail(f"{path}[{i}].{key}", "non-empty required")
        out.append(value)
    if len(out) != len(set(out)):
        fail(path, f"duplicate {key}")
    return set(out)


def require_source_refs(item, path, source_ids, required=True):
    refs = item.get("source_refs", [])
    if required and (not isinstance(refs, list) or not refs):
        fail(f"{path}.source_refs", "non-empty required")
    if not isinstance(refs, list):
        fail(f"{path}.source_refs", "list required")
    unknown = set(refs) - source_ids
    if unknown:
        fail(f"{path}.source_refs", f"unknown source refs {sorted(unknown)}")


def validate_source_status(item, path, source_ids, *, allow_implementation=True):
    status = item.get("source_status")
    allowed = set(SOURCE_STATUS)
    if not allow_implementation:
        allowed.discard("IMPLEMENTATION_DETAIL")
    if status not in allowed:
        fail(f"{path}.source_status", f"must be one of {sorted(allowed)}")
    require_source_refs(item, path, source_ids, required=status in {"CONFIRMED", "DERIVED"})
    if status == "DERIVED":
        derived = item.get("derived_from")
        if not isinstance(derived, list) or not derived:
            fail(f"{path}.derived_from", "DERIVED requires non-empty derived_from")
    if status == "PENDING":
        fail(path, "PENDING business facts must be represented as unknowns, not accepted facts")


def validate_scope(scope):
    if not isinstance(scope, dict):
        fail("scope", "object required")
    for key in ("in_scope", "dependency_scope", "out_of_scope"):
        if key not in scope or not isinstance(scope[key], list):
            fail(f"scope.{key}", "list required")
    if not scope["in_scope"]:
        fail("scope.in_scope", "at least one in-scope item required")


def validate_lifecycle(rel, path):
    for key in LIFECYCLE_FIELDS:
        val = rel.get(key)
        if not isinstance(val, dict):
            fail(f"{path}.{key}", "object required with applicable + optional behavior")
        if not isinstance(val.get("applicable"), bool):
            fail(f"{path}.{key}.applicable", "boolean required")
        if val["applicable"] and not text(val.get("behavior")):
            fail(f"{path}.{key}.behavior", "required when applicable=true")
        if not val["applicable"] and val.get("behavior") not in (None, ""):
            fail(f"{path}.{key}.behavior", "must be empty when applicable=false")


def validate_presentation_sync(v):
    ps = v.get("presentation_sync")
    if not isinstance(ps, dict):
        fail("presentation_sync", "object required")
    if ps.get("status") != "passed":
        fail("presentation_sync.status", "must be passed")
    checks = ps.get("checks")
    required = {
        "main_document_updated",
        "review_document_updated",
        "pending_questions_reflected",
        "model_consistency_checked",
    }
    if not isinstance(checks, dict):
        fail("presentation_sync.checks", "object required")
    for key in required:
        if checks.get(key) is not True:
            fail(f"presentation_sync.checks.{key}", "must be true")


def validate(v, require_confirmed=True):
    """
    require_confirmed=False: validate a self-reviewed draft. Pending blocking decisions may remain,
    but they must be explicit and fully documented.

    require_confirmed=True: additionally require all business decisions that change expected behavior
    to be resolved before the artifact may be finally confirmed by the workflow controller.

    Human confirmation itself is NOT stored in this JSON. The workflow state is the single source of truth.
    """
    if not isinstance(v, dict):
        fail("business", "object required")
    if not text(v.get("schema_version")):
        fail("schema_version", "required")
    if not text(v.get("model_version")):
        fail("model_version", "required")

    validate_scope(v.get("scope"))

    sources = v.get("source_registry")
    if not isinstance(sources, list) or not sources:
        fail("source_registry", "non-empty list required")
    source_ids = ids(sources, "source_id", "source_registry")
    for i, src in enumerate(sources):
        p = f"source_registry[{i}]"
        if not text(src.get("type")):
            fail(f"{p}.type", "required")
        if not text(src.get("title")):
            fail(f"{p}.title", "required")

    modules = v.get("modules")
    if not isinstance(modules, list) or not modules:
        fail("modules", "non-empty list required")
    module_ids = ids(modules, "module_id", "modules")
    for i, mod in enumerate(modules):
        p = f"modules[{i}]"
        if not text(mod.get("name")):
            fail(f"{p}.name", "required")
        if not text(mod.get("purpose")):
            fail(f"{p}.purpose", "required")
        if not isinstance(mod.get("function_names"), list):
            fail(f"{p}.function_names", "list required")
        if not isinstance(mod.get("object_ids"), list):
            fail(f"{p}.object_ids", "list required")
        if not isinstance(mod.get("event_ids"), list):
            fail(f"{p}.event_ids", "list required")

    objects = v.get("business_objects")
    if not isinstance(objects, list) or not objects:
        fail("business_objects", "non-empty list required")
    object_ids = ids(objects, "object_id", "business_objects")
    for i, obj in enumerate(objects):
        p = f"business_objects[{i}]"
        if obj.get("module_id") not in module_ids:
            fail(f"{p}.module_id", "unknown module")
        for key in ("name", "business_purpose", "stable_identity"):
            if not text(obj.get(key)):
                fail(f"{p}.{key}", "required")
        for key in ("key_fields", "key_rules"):
            if not isinstance(obj.get(key), list):
                fail(f"{p}.{key}", "list required")
        require_source_refs(obj, p, source_ids, required=False)

    state_machines = v.get("state_machines", [])
    if not isinstance(state_machines, list):
        fail("state_machines", "list required")
    sm_ids = ids(state_machines, "state_machine_id", "state_machines") if state_machines else set()
    transition_ids = set()
    for i, sm in enumerate(state_machines):
        p = f"state_machines[{i}]"
        if sm.get("object_id") not in object_ids:
            fail(f"{p}.object_id", "unknown business object")
        states = sm.get("states")
        if not isinstance(states, list) or not states:
            fail(f"{p}.states", "non-empty list required")
        state_ids = ids(states, "state_id", f"{p}.states")
        for j, s in enumerate(states):
            if not text(s.get("name")):
                fail(f"{p}.states[{j}].name", "required")
        transitions = sm.get("transitions")
        if not isinstance(transitions, list):
            fail(f"{p}.transitions", "list required")
        local_tr_ids = ids(transitions, "transition_id", f"{p}.transitions") if transitions else set()
        if transition_ids & local_tr_ids:
            fail(f"{p}.transitions", "transition ids must be globally unique")
        transition_ids |= local_tr_ids
        for j, tr in enumerate(transitions):
            q = f"{p}.transitions[{j}]"
            if tr.get("from") not in state_ids or tr.get("to") not in state_ids:
                fail(q, "from/to must reference states in the same machine")
            if not text(tr.get("action")):
                fail(f"{q}.action", "required")
            if not isinstance(tr.get("effects", []), list):
                fail(f"{q}.effects", "list required")
            validate_source_status(tr, q, source_ids, allow_implementation=False)
        invalid = sm.get("invalid_or_blocked_transitions")
        if not isinstance(invalid, list):
            fail(f"{p}.invalid_or_blocked_transitions", "list required")
    for i, obj in enumerate(objects):
        smid = obj.get("state_machine_id")
        if smid is not None and smid not in sm_ids:
            fail(f"business_objects[{i}].state_machine_id", "unknown state machine")

    relationships = v.get("relationships", [])
    if not isinstance(relationships, list):
        fail("relationships", "list required")
    relationship_ids = ids(relationships, "relationship_id", "relationships") if relationships else set()
    for i, rel in enumerate(relationships):
        p = f"relationships[{i}]"
        if rel.get("from_object_id") not in object_ids or rel.get("to_object_id") not in object_ids:
            fail(p, "relationship endpoints must reference business objects")
        for key in ("name", "cardinality", "source_of_truth", "maintenance_owner"):
            if not text(rel.get(key)):
                fail(f"{p}.{key}", "required")
        validate_lifecycle(rel, p)
        validate_source_status(rel, p, source_ids, allow_implementation=False)

    events = v.get("events")
    if not isinstance(events, list) or not events:
        fail("events", "non-empty list required")
    event_ids = ids(events, "event_id", "events")
    event_list_fields = (
        "actors", "preconditions", "inputs", "outputs", "direct_changes", "state_changes",
        "relationship_changes", "downstream_impacts", "must_not_change",
        "failure_conditions", "failure_final_facts", "source_refs"
    )
    for i, ev in enumerate(events):
        p = f"events[{i}]"
        if ev.get("module_id") not in module_ids:
            fail(f"{p}.module_id", "unknown module")
        if not text(ev.get("name")):
            fail(f"{p}.name", "required")
        if not text(ev.get("trigger")):
            fail(f"{p}.trigger", "required")
        for key in event_list_fields:
            if key not in ev or not isinstance(ev[key], list):
                fail(f"{p}.{key}", "list required")
        if not ev["outputs"]:
            fail(f"{p}.outputs", "at least one business-observable output required")
        if ev["failure_conditions"] and not ev["failure_final_facts"]:
            fail(f"{p}.failure_final_facts", "required when failure_conditions exist")
        validate_source_status(ev, p, source_ids, allow_implementation=False)

    referenced_objects = set()
    referenced_events = set()
    for i, mod in enumerate(modules):
        p = f"modules[{i}]"
        unknown_obj = set(mod["object_ids"]) - object_ids
        unknown_ev = set(mod["event_ids"]) - event_ids
        if unknown_obj:
            fail(f"{p}.object_ids", f"unknown objects {sorted(unknown_obj)}")
        if unknown_ev:
            fail(f"{p}.event_ids", f"unknown events {sorted(unknown_ev)}")
        referenced_objects |= set(mod["object_ids"])
        referenced_events |= set(mod["event_ids"])
    if object_ids - referenced_objects:
        fail("modules.object_ids", f"objects not registered in module navigation: {sorted(object_ids - referenced_objects)}")
    if event_ids - referenced_events:
        fail("modules.event_ids", f"events not registered in module navigation: {sorted(event_ids - referenced_events)}")

    rules = v.get("rules", [])
    if not isinstance(rules, list):
        fail("rules", "list required")
    rule_ids = ids(rules, "rule_id", "rules") if rules else set()
    model_refs = module_ids | object_ids | sm_ids | transition_ids | relationship_ids | event_ids | rule_ids
    for i, rule in enumerate(rules):
        p = f"rules[{i}]"
        if not text(rule.get("description")):
            fail(f"{p}.description", "required")
        applies = rule.get("applies_to_refs", [])
        if not isinstance(applies, list):
            fail(f"{p}.applies_to_refs", "list required")
        unknown = set(applies) - model_refs
        if unknown:
            fail(f"{p}.applies_to_refs", f"unknown refs {sorted(unknown)}")
        validate_source_status(rule, p, source_ids)

    for i, obj in enumerate(objects):
        unknown_rules = set(obj.get("key_rules", [])) - rule_ids
        if unknown_rules:
            fail(f"business_objects[{i}].key_rules", f"unknown rule refs {sorted(unknown_rules)}")

    invariants = v.get("invariants", [])
    if not isinstance(invariants, list):
        fail("invariants", "list required")
    invariant_ids = ids(invariants, "invariant_id", "invariants") if invariants else set()
    all_refs = model_refs | invariant_ids
    for i, inv in enumerate(invariants):
        p = f"invariants[{i}]"
        if not text(inv.get("description")):
            fail(f"{p}.description", "required")
        applies = inv.get("applies_to_refs")
        if not isinstance(applies, list) or not applies:
            fail(f"{p}.applies_to_refs", "non-empty list required")
        unknown = set(applies) - all_refs
        if unknown:
            fail(f"{p}.applies_to_refs", f"unknown refs {sorted(unknown)}")
        validate_source_status(inv, p, source_ids)

    flows = v.get("cross_module_flows", [])
    if not isinstance(flows, list):
        fail("cross_module_flows", "list required")
    flow_ids = ids(flows, "flow_id", "cross_module_flows") if flows else set()
    for i, flow in enumerate(flows):
        p = f"cross_module_flows[{i}]"
        if not text(flow.get("name")):
            fail(f"{p}.name", "required")
        if flow.get("scope") not in {"module", "cross_module"}:
            fail(f"{p}.scope", "must be module or cross_module")
        steps = flow.get("steps")
        if not isinstance(steps, list) or len(steps) < 2:
            fail(f"{p}.steps", "at least two event ids required")
        unknown = set(steps) - event_ids
        if unknown:
            fail(f"{p}.steps", f"unknown event refs {sorted(unknown)}")
        for key in ("branches", "failure_paths", "recovery_paths"):
            if not isinstance(flow.get(key), list):
                fail(f"{p}.{key}", "list required")
        validate_source_status(flow, p, source_ids, allow_implementation=False)

    all_model_refs = all_refs | flow_ids

    unknowns = v.get("unknowns", [])
    if not isinstance(unknowns, list):
        fail("unknowns", "list required")
    unknown_ids = ids(unknowns, "unknown_id", "unknowns") if unknowns else set()
    blocked = set(v.get("blocked_scopes", []))
    pending_blocking_scopes = set()
    pending_blocking_ids = set()

    for i, q in enumerate(unknowns):
        p = f"unknowns[{i}]"
        if q.get("category") not in UNKNOWN_CATEGORIES:
            fail(f"{p}.category", f"unsupported category {q.get('category')}")
        if q.get("status") not in UNKNOWN_STATUS:
            fail(f"{p}.status", f"unsupported status {q.get('status')}")
        if not text(q.get("question")) or not text(q.get("why_needed")):
            fail(p, "question and why_needed required")
        if not isinstance(q.get("affects_expected"), bool):
            fail(f"{p}.affects_expected", "boolean required")
        scopes = q.get("affected_scopes", [])
        if not isinstance(scopes, list):
            fail(f"{p}.affected_scopes", "list required")
        require_source_refs(q, p, source_ids, required=False)

        if q.get("category") in {"blocking_business", "non_blocking_business"}:
            if q.get("issue_type") not in ISSUE_TYPES:
                fail(f"{p}.issue_type", f"must be one of {sorted(ISSUE_TYPES)}")
            evidence_checked = q.get("evidence_checked")
            if not isinstance(evidence_checked, list) or not evidence_checked:
                fail(f"{p}.evidence_checked", "non-empty list required for business questions")
            unknown_evidence = set(evidence_checked) - source_ids
            if unknown_evidence:
                fail(f"{p}.evidence_checked", f"unknown source refs {sorted(unknown_evidence)}")
            if q.get("issue_type") == "source_conflict" and len(set(evidence_checked)) < 2:
                fail(f"{p}.evidence_checked", "source_conflict must compare at least two evidence sources")
            depends_on = q.get("depends_on", [])
            if not isinstance(depends_on, list):
                fail(f"{p}.depends_on", "list required")
            if not text(q.get("impact_summary")):
                fail(f"{p}.impact_summary", "required for business questions")

            if q.get("status") == "pending":
                mode = q.get("answer_mode", "choice")
                if mode not in {"choice", "open"}:
                    fail(f"{p}.answer_mode", "must be choice or open")
                if not text(q.get("recommendation_reason")):
                    fail(f"{p}.recommendation_reason", "pending business question requires recommendation reason")
                if mode == "choice":
                    options = q.get("options")
                    if not isinstance(options, list) or len(options) < 2:
                        fail(f"{p}.options", "choice question requires at least two options")
                    option_ids = []
                    for j, opt in enumerate(options):
                        if not isinstance(opt, dict) or not text(opt.get("option_id")) or not text(opt.get("description")):
                            fail(f"{p}.options[{j}]", "option_id and description required")
                        if not text(opt.get("impact")):
                            fail(f"{p}.options[{j}].impact", "required")
                        option_ids.append(opt["option_id"])
                    if q.get("recommended_option") not in option_ids:
                        fail(f"{p}.recommended_option", "must reference one option")
                else:
                    if not text(q.get("recommended_answer")):
                        fail(f"{p}.recommended_answer", "open question requires recommended_answer")
            if q.get("status") == "resolved" and not text(q.get("answer")):
                fail(f"{p}.answer", "resolved business question requires answer")

        if q["status"] == "pending" and q["category"] == "blocking_business" and q["affects_expected"]:
            if not scopes:
                fail(f"{p}.affected_scopes", "blocking expected-affecting unknown needs affected scopes")
            pending_blocking_scopes.update(scopes)
            pending_blocking_ids.add(q["unknown_id"])

    for i, q in enumerate(unknowns):
        depends_on = q.get("depends_on", [])
        if depends_on:
            unknown = set(depends_on) - unknown_ids
            if unknown:
                fail(f"unknowns[{i}].depends_on", f"unknown dependencies {sorted(unknown)}")
            if q.get("unknown_id") in depends_on:
                fail(f"unknowns[{i}].depends_on", "cannot depend on itself")

    missing_blocked = pending_blocking_scopes - blocked
    if missing_blocked:
        fail("blocked_scopes", f"must include pending blocking scopes {sorted(missing_blocked)}")

    # Requirements completeness review: prove that the discovery tree was actually traversed.
    completeness = v.get("requirements_completeness_review")
    if not isinstance(completeness, dict) or completeness.get("status") != "passed":
        fail("requirements_completeness_review.status", "must be passed")
    dims = completeness.get("dimensions")
    if not isinstance(dims, list):
        fail("requirements_completeness_review.dimensions", "list required")
    dim_ids = ids(dims, "dimension", "requirements_completeness_review.dimensions") if dims else set()
    missing_dims = COMPLETENESS_DIMENSIONS - dim_ids
    extra_dims = dim_ids - COMPLETENESS_DIMENSIONS
    if missing_dims:
        fail("requirements_completeness_review.dimensions", f"missing dimensions {sorted(missing_dims)}")
    if extra_dims:
        fail("requirements_completeness_review.dimensions", f"unsupported dimensions {sorted(extra_dims)}")
    for i, item in enumerate(dims):
        p = f"requirements_completeness_review.dimensions[{i}]"
        if not isinstance(item.get("applicable"), bool):
            fail(f"{p}.applicable", "boolean required")
        if item.get("status") not in COMPLETENESS_STATUS:
            fail(f"{p}.status", f"must be one of {sorted(COMPLETENESS_STATUS)}")
        evidence_refs = item.get("evidence_refs", [])
        model_item_refs = item.get("model_refs", [])
        question_refs = item.get("question_ids", [])
        if not isinstance(evidence_refs, list) or not isinstance(model_item_refs, list) or not isinstance(question_refs, list):
            fail(p, "evidence_refs/model_refs/question_ids must be lists")
        unknown_src = set(evidence_refs) - source_ids
        unknown_model = set(model_item_refs) - all_model_refs
        unknown_q = set(question_refs) - unknown_ids
        if unknown_src:
            fail(f"{p}.evidence_refs", f"unknown source refs {sorted(unknown_src)}")
        if unknown_model:
            fail(f"{p}.model_refs", f"unknown model refs {sorted(unknown_model)}")
        if unknown_q:
            fail(f"{p}.question_ids", f"unknown question refs {sorted(unknown_q)}")

        # Every completeness judgment must show what it was checked against.
        # This prevents a model from marking whole branches as "not applicable" without
        # demonstrating that it actually inspected the current scope/evidence/model.
        if not (evidence_refs or model_item_refs):
            fail(p, "every completeness dimension needs evidence_refs or model_refs as its review basis")

        if item["applicable"]:
            if item["status"] == "not_applicable":
                fail(f"{p}.status", "applicable dimension cannot be not_applicable")
            if item["status"] == "question_raised" and not question_refs:
                fail(f"{p}.question_ids", "question_raised dimension needs question_ids")
        else:
            if item["status"] != "not_applicable":
                fail(f"{p}.status", "non-applicable dimension must be not_applicable")
            if not text(item.get("reason")):
                fail(f"{p}.reason", "required when applicable=false")

    review = v.get("self_review")
    if not isinstance(review, dict) or review.get("status") != "passed":
        fail("self_review.status", "must be passed before final confirmation")
    checks = review.get("checks", {})
    for key in SELF_CHECKS:
        if checks.get(key) is not True:
            fail(f"self_review.checks.{key}", "must be true")

    validate_presentation_sync(v)

    if require_confirmed and pending_blocking_ids:
        fail("unknowns", f"pending blocking business questions must be resolved before final confirmation: {sorted(pending_blocking_ids)}")

    return {
        "ok": True,
        "model_version": v["model_version"],
        "modules": len(modules),
        "objects": len(objects),
        "state_machines": len(state_machines),
        "relationships": len(relationships),
        "events": len(events),
        "invariants": len(invariants),
        "flows": len(flows),
        "unknowns": len(unknowns),
        "pending_blocking_questions": sorted(pending_blocking_ids),
        "blocked_scopes": sorted(blocked),
        "ready_for_confirmation": not pending_blocking_ids,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--allow-waiting-confirmation", action="store_true")
    args = parser.parse_args()
    data = json.loads(Path(args.input).read_text(encoding="utf-8"))
    print(json.dumps(validate(data, require_confirmed=not args.allow_waiting_confirmation), ensure_ascii=False, indent=2))
