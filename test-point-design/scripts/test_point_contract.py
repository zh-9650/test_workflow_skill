import argparse
import json
from pathlib import Path

COVERAGE_TYPES = {
    "event_behavior", "field_rule", "state", "transition", "relation",
    "relation_lifecycle", "authorization", "data_consistency",
    "downstream_effect", "invariant", "negative_business_rule",
    "failure_atomicity", "recovery", "concurrency", "stale_state",
    "scope_isolation", "long_flow", "cross_module"
}
COVERAGE_STATUS = {"covered", "not_applicable", "out_of_scope", "pending_confirmation"}
GRANULARITY = {"atomic", "composite_flow"}
PRIORITIES = {"P0", "P1", "P2"}
SOURCE_STATUS = {"CONFIRMED", "DERIVED", "TEST_BASELINE"}
QUESTION_STATUS = {"pending", "resolved", "out_of_scope"}
QUESTION_TYPES = {"coverage_scope", "risk_priority", "granularity", "flow_coverage", "upstream_business_gap"}


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


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def model_refs(business):
    modules = {m["module_id"] for m in business.get("modules", [])}
    objects = {o["object_id"] for o in business.get("business_objects", [])}
    events = {e["event_id"] for e in business.get("events", [])}
    relations = {r["relationship_id"] for r in business.get("relationships", [])}
    invariants = {i["invariant_id"] for i in business.get("invariants", [])}
    rules = {r["rule_id"] for r in business.get("rules", [])}
    flows = {f["flow_id"] for f in business.get("cross_module_flows", [])}
    transitions = set()
    for sm in business.get("state_machines", []):
        transitions |= {t["transition_id"] for t in sm.get("transitions", [])}
    return {
        "modules": modules,
        "objects": objects,
        "events": events,
        "relations": relations,
        "invariants": invariants,
        "rules": rules,
        "flows": flows,
        "transitions": transitions,
        "all": modules | objects | events | relations | invariants | rules | flows | transitions,
    }


def validate_presentation_sync(v):
    ps = v.get("presentation_sync")
    if not isinstance(ps, dict) or ps.get("status") != "passed":
        fail("presentation_sync.status", "must be passed")
    checks = ps.get("checks")
    required = {"main_document_updated", "review_document_updated", "pending_questions_reflected", "model_consistency_checked"}
    if not isinstance(checks, dict):
        fail("presentation_sync.checks", "object required")
    for key in required:
        if checks.get(key) is not True:
            fail(f"presentation_sync.checks.{key}", "must be true")


def validate_question(q, path, valid_evidence_refs):
    if q.get("status") not in QUESTION_STATUS:
        fail(f"{path}.status", "invalid status")
    if q.get("question_type") not in QUESTION_TYPES:
        fail(f"{path}.question_type", f"must be one of {sorted(QUESTION_TYPES)}")
    if not text(q.get("question")) or not text(q.get("why_needed")):
        fail(path, "question and why_needed required")
    if not isinstance(q.get("affects_expected"), bool):
        fail(f"{path}.affects_expected", "boolean required")
    if not isinstance(q.get("blocking"), bool):
        fail(f"{path}.blocking", "boolean required")
    evidence = q.get("evidence_checked")
    if not isinstance(evidence, list) or not evidence:
        fail(f"{path}.evidence_checked", "non-empty list required")
    unknown_evidence = set(evidence) - valid_evidence_refs
    if unknown_evidence:
        fail(f"{path}.evidence_checked", f"unknown evidence refs {sorted(unknown_evidence)}")
    if not text(q.get("impact_summary")):
        fail(f"{path}.impact_summary", "required")

    if q["status"] == "pending":
        if not text(q.get("recommendation_reason")):
            fail(f"{path}.recommendation_reason", "required")
        mode = q.get("answer_mode", "choice")
        if mode not in {"choice", "open"}:
            fail(f"{path}.answer_mode", "must be choice or open")
        if mode == "choice":
            options = q.get("options")
            if not isinstance(options, list) or len(options) < 2:
                fail(f"{path}.options", "choice question needs at least two options")
            option_ids = []
            for i, opt in enumerate(options):
                if not isinstance(opt, dict) or not text(opt.get("option_id")) or not text(opt.get("description")):
                    fail(f"{path}.options[{i}]", "option_id and description required")
                if not text(opt.get("impact")):
                    fail(f"{path}.options[{i}].impact", "required")
                option_ids.append(opt["option_id"])
            if q.get("recommended_option") not in option_ids:
                fail(f"{path}.recommended_option", "must reference one option")
        else:
            if not text(q.get("recommended_answer")):
                fail(f"{path}.recommended_answer", "required for open question")

    if q["status"] == "resolved" and not text(q.get("answer")):
        fail(f"{path}.answer", "required when resolved")

    if q.get("affects_expected"):
        if q.get("return_to_business_understanding") is not True:
            fail(f"{path}.return_to_business_understanding", "expected-affecting question must return to business understanding")
        if q.get("question_type") != "upstream_business_gap":
            fail(f"{path}.question_type", "expected-affecting question must be upstream_business_gap")


def validate(v, confirmed_business, require_confirmed=True):
    """
    Human confirmation is owned by workflow_state.py, not duplicated inside test-points.json.

    require_confirmed=False: self-review mode; pending questions/coverage are allowed if explicitly modeled.
    require_confirmed=True: final-confirmation mode; all pending design questions and pending coverage must be resolved.
    """
    if not isinstance(v, dict):
        fail("test_point_design", "object required")
    if not text(v.get("schema_version")):
        fail("schema_version", "required")
    if not text(v.get("design_version")):
        fail("design_version", "required")
    if v.get("business_model_version") != confirmed_business.get("model_version"):
        fail("business_model_version", "must match confirmed business model version")

    refs = model_refs(confirmed_business)
    source_ids = {s.get("source_id") for s in confirmed_business.get("source_registry", []) if text(s.get("source_id"))}
    valid_evidence_refs = refs["all"] | source_ids

    questions = v.get("design_questions", [])
    if not isinstance(questions, list):
        fail("design_questions", "list required")
    question_ids = ids(questions, "question_id", "design_questions") if questions else set()
    pending_questions = set()
    return_to_business = set()
    for i, q in enumerate(questions):
        p = f"design_questions[{i}]"
        validate_question(q, p, valid_evidence_refs)
        if q["status"] == "pending":
            pending_questions.add(q["question_id"])
            if q.get("affects_expected"):
                return_to_business.add(q["question_id"])

    coverage = v.get("coverage_obligations")
    if not isinstance(coverage, list) or not coverage:
        fail("coverage_obligations", "non-empty list required")
    coverage_ids = ids(coverage, "coverage_id", "coverage_obligations")
    coverage_by_id = {c["coverage_id"]: c for c in coverage}
    pending_coverage = set()

    points = v.get("test_points")
    if not isinstance(points, list) or not points:
        fail("test_points", "non-empty list required")
    point_ids = ids(points, "tp_id", "test_points")

    for i, c in enumerate(coverage):
        p = f"coverage_obligations[{i}]"
        if c.get("type") not in COVERAGE_TYPES:
            fail(f"{p}.type", f"unsupported type {c.get('type')}")
        if c.get("status") not in COVERAGE_STATUS:
            fail(f"{p}.status", f"unsupported status {c.get('status')}")
        if not text(c.get("description")):
            fail(f"{p}.description", "required")
        source_refs = c.get("source_model_refs")
        if not isinstance(source_refs, list) or not source_refs:
            fail(f"{p}.source_model_refs", "non-empty required")
        unknown = set(source_refs) - refs["all"]
        if unknown:
            fail(f"{p}.source_model_refs", f"unknown refs {sorted(unknown)}")

        status = c["status"]
        if status == "covered":
            tpids = c.get("test_point_ids")
            if not isinstance(tpids, list) or not tpids:
                fail(f"{p}.test_point_ids", "covered item requires test points")
            unknown_tp = set(tpids) - point_ids
            if unknown_tp:
                fail(f"{p}.test_point_ids", f"unknown test points {sorted(unknown_tp)}")
        elif status in {"not_applicable", "out_of_scope"}:
            if not text(c.get("reason")):
                fail(f"{p}.reason", f"{status} requires reason")
        else:
            qid = c.get("question_id")
            if qid not in question_ids:
                fail(f"{p}.question_id", "pending coverage requires design question")
            pending_coverage.add(c["coverage_id"])

    def require_ref(ref_id, types, path):
        items = [c for c in coverage if ref_id in c.get("source_model_refs", [])]
        if not items:
            fail(path, "business model ref has no coverage obligation")
        if not any(c.get("type") in types for c in items):
            fail(path, f"requires at least one of coverage types {sorted(types)}")

    for ev in confirmed_business.get("events", []):
        eid = ev["event_id"]
        require_ref(eid, {"event_behavior"}, f"{eid}.coverage")
        if ev.get("downstream_impacts"):
            require_ref(eid, {"downstream_effect", "data_consistency"}, f"{eid}.downstream_coverage")
        if ev.get("failure_conditions"):
            require_ref(eid, {"failure_atomicity", "negative_business_rule"}, f"{eid}.failure_coverage")
        if ev.get("relationship_changes"):
            require_ref(eid, {"relation", "relation_lifecycle"}, f"{eid}.relation_coverage")

    for sm in confirmed_business.get("state_machines", []):
        for tr in sm.get("transitions", []):
            require_ref(tr["transition_id"], {"transition", "state"}, f"{tr['transition_id']}.coverage")

    for rel in confirmed_business.get("relationships", []):
        require_ref(rel["relationship_id"], {"relation_lifecycle", "relation"}, f"{rel['relationship_id']}.coverage")

    for inv in confirmed_business.get("invariants", []):
        require_ref(inv["invariant_id"], {"invariant", "data_consistency"}, f"{inv['invariant_id']}.coverage")

    for rule in confirmed_business.get("rules", []):
        require_ref(
            rule["rule_id"],
            {"field_rule", "negative_business_rule", "authorization", "event_behavior", "state", "relation", "data_consistency", "downstream_effect"},
            f"{rule['rule_id']}.coverage",
        )

    for flow in confirmed_business.get("cross_module_flows", []):
        required = {"cross_module", "long_flow"} if flow.get("scope") == "cross_module" else {"long_flow"}
        require_ref(flow["flow_id"], required, f"{flow['flow_id']}.coverage")
        if flow.get("recovery_paths"):
            require_ref(flow["flow_id"], {"recovery", "long_flow"}, f"{flow['flow_id']}.recovery_coverage")

    for i, tp in enumerate(points):
        p = f"test_points[{i}]"
        if tp.get("priority") not in PRIORITIES:
            fail(f"{p}.priority", "must be P0/P1/P2")
        if tp.get("granularity") not in GRANULARITY:
            fail(f"{p}.granularity", "must be atomic or composite_flow")
        if not text(tp.get("module_id")) or tp["module_id"] not in refs["modules"]:
            fail(f"{p}.module_id", "unknown module")
        for key in ("preconditions", "affected_facts", "must_not_change", "downstream_impacts", "business_object_ids", "business_event_ids", "source_coverage_ids", "source_refs"):
            if not isinstance(tp.get(key), list):
                fail(f"{p}.{key}", "list required")
        if not text(tp.get("mechanism")):
            fail(f"{p}.mechanism", "required")
        if not text(tp.get("core_expected")):
            fail(f"{p}.core_expected", "required")
        if tp.get("source_status") not in SOURCE_STATUS:
            fail(f"{p}.source_status", f"must be one of {sorted(SOURCE_STATUS)}")
        unknown_sources = set(tp["source_refs"]) - source_ids
        if unknown_sources:
            fail(f"{p}.source_refs", f"unknown sources {sorted(unknown_sources)}")
        if tp.get("source_status") == "DERIVED":
            derived_from = tp.get("derived_from")
            if not isinstance(derived_from, list) or not derived_from:
                fail(f"{p}.derived_from", "DERIVED test point requires non-empty derived_from")

        unknown_obj = set(tp["business_object_ids"]) - refs["objects"]
        unknown_ev = set(tp["business_event_ids"]) - refs["events"]
        unknown_cov = set(tp["source_coverage_ids"]) - coverage_ids
        if unknown_obj:
            fail(f"{p}.business_object_ids", f"unknown objects {sorted(unknown_obj)}")
        if unknown_ev:
            fail(f"{p}.business_event_ids", f"unknown events {sorted(unknown_ev)}")
        if unknown_cov:
            fail(f"{p}.source_coverage_ids", f"unknown coverage {sorted(unknown_cov)}")

        primary = tp.get("primary_coverage_id")
        if primary not in coverage_ids:
            fail(f"{p}.primary_coverage_id", "must reference a coverage obligation")
        if primary not in tp["source_coverage_ids"]:
            fail(f"{p}.primary_coverage_id", "must also appear in source_coverage_ids")
        if coverage_by_id[primary].get("status") != "covered":
            fail(f"{p}.primary_coverage_id", "primary coverage must be covered")
        if tp["tp_id"] not in coverage_by_id[primary].get("test_point_ids", []):
            fail(f"{p}.primary_coverage_id", "coverage item must reverse-link this test point")

        if tp["granularity"] == "atomic" and len(tp["source_coverage_ids"]) > 1:
            if not text(tp.get("cohesion_rationale")):
                fail(f"{p}.cohesion_rationale", "atomic TP spanning multiple coverage obligations must explain why they are one mechanism")

        if tp["granularity"] == "composite_flow":
            if coverage_by_id[primary].get("type") not in {"long_flow", "cross_module"}:
                fail(f"{p}.granularity", "composite_flow primary coverage must be long_flow or cross_module")
        else:
            if coverage_by_id[primary].get("type") in {"long_flow", "cross_module"} and len(tp["source_coverage_ids"]) > 1:
                fail(f"{p}.primary_coverage_id", "atomic test point primary mechanism cannot be a composite flow when other mechanism coverage exists")

    for i, tp in enumerate(points):
        p = f"test_points[{i}]"
        for cid in tp["source_coverage_ids"]:
            c = coverage_by_id[cid]
            if c.get("status") == "covered" and tp["tp_id"] not in c.get("test_point_ids", []):
                fail(f"{p}.source_coverage_ids", f"{cid} does not reverse-link {tp['tp_id']}")

    review = v.get("granularity_review")
    if not isinstance(review, dict) or review.get("status") != "passed":
        fail("granularity_review.status", "must be passed")
    if review.get("overbroad_point_ids") not in ([], None):
        fail("granularity_review.overbroad_point_ids", "must be empty before final confirmation")
    if review.get("data_instance_split_groups") not in ([], None):
        fail("granularity_review.data_instance_split_groups", "must be empty before final confirmation")

    self_review = v.get("test_points_self_review")
    if not isinstance(self_review, dict) or self_review.get("status") != "passed":
        fail("test_points_self_review.status", "must be passed")
    if self_review.get("coverage_accounted_for") is not True:
        fail("test_points_self_review.coverage_accounted_for", "must be true")

    validate_presentation_sync(v)

    ready = not pending_questions and not pending_coverage and not return_to_business
    if require_confirmed:
        if return_to_business:
            fail("design_questions", f"business expected is unresolved; return to business understanding: {sorted(return_to_business)}")
        if pending_questions:
            fail("design_questions", f"pending test-point questions must be resolved before final confirmation: {sorted(pending_questions)}")
        if pending_coverage:
            fail("coverage_obligations", f"pending coverage must be resolved before final confirmation: {sorted(pending_coverage)}")

    return {
        "ok": True,
        "design_version": v["design_version"],
        "business_model_version": v["business_model_version"],
        "coverage_obligations": len(coverage),
        "test_points": len(points),
        "coverage_types": sorted({c["type"] for c in coverage if c["status"] == "covered"}),
        "pending_questions": sorted(pending_questions),
        "pending_coverage": sorted(pending_coverage),
        "return_to_business_understanding": bool(return_to_business),
        "ready_for_confirmation": ready,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--business", required=True)
    parser.add_argument("--allow-waiting-confirmation", action="store_true")
    args = parser.parse_args()
    points = load(args.input)
    business = load(args.business)
    print(json.dumps(
        validate(points, business, require_confirmed=not args.allow_waiting_confirmation),
        ensure_ascii=False,
        indent=2,
    ))
