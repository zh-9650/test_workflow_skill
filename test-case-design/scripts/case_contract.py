import argparse
import json
import re
from pathlib import Path

PRIORITIES = {"P0", "P1", "P2"}
CASE_TYPES = {
    "ordinary", "parameterized", "decision_table", "state_transition",
    "relation_lifecycle", "failure_atomicity", "recovery", "concurrency",
    "stale_state", "scope_isolation", "long_flow", "cross_module"
}
STRATEGIES = {
    "direct", "equivalence_partition", "boundary_value", "decision_table",
    "state_transition", "relationship_lifecycle", "failure_atomicity",
    "recovery", "concurrency", "stale_state", "scope_isolation",
    "long_flow", "combined"
}
CHECKPOINTS = {"step", "intermediate", "final"}
EVIDENCE_KINDS = {"screenshot", "request_response", "read_back", "network", "file", "runner_report"}
VAGUE_EXACT = {
    "正常", "正常展示", "正常返回", "结果正确", "符合预期", "符合规则",
    "按实际实现", "按最终口径", "无异常", "成功", "失败"
}
PROTECTED_MERGE_TYPES = {
    "failure_atomicity", "recovery", "concurrency", "stale_state", "scope_isolation"
}


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


def validate_expected(value, path):
    if not text(value):
        fail(path, "non-empty expected required")
    if value.strip() in VAGUE_EXACT:
        fail(path, f"vague expected forbidden: {value}")


def validate(v, confirmed_points, confirmed_business, require_confirmed=True):
    if not isinstance(v, dict):
        fail("test_case_design", "object required")
    if v.get("schema_version") != "2.0.0":
        fail("schema_version", "test case design requires schema_version=2.0.0")
    if not text(v.get("case_design_version")):
        fail("case_design_version", "required")

    # Human confirmation is owned by workflow_state.py. This contract validates only
    # structural correctness and upstream version consistency.
    if v.get("test_point_version") != confirmed_points.get("design_version"):
        fail("test_point_version", "must match confirmed test-point design version")
    if v.get("business_model_version") != confirmed_business.get("model_version"):
        fail("business_model_version", "must match confirmed business model version")
    if confirmed_points.get("business_model_version") != confirmed_business.get("model_version"):
        fail("confirmed_points.business_model_version", "confirmed test points are stale against business model")

    points = confirmed_points.get("test_points", [])
    point_ids = {p.get("tp_id") for p in points if text(p.get("tp_id"))}
    point_priority = {p.get("tp_id"): p.get("priority") for p in points if text(p.get("tp_id"))}
    priority_rank = {"P0": 0, "P1": 1, "P2": 2}
    point_by_id = {p.get("tp_id"): p for p in points if text(p.get("tp_id"))}
    coverage_by_id = {c.get("coverage_id"): c for c in confirmed_points.get("coverage_obligations", []) if text(c.get("coverage_id"))}
    if not point_ids:
        fail("confirmed_points.test_points", "non-empty test points required")

    review_questions = v.get("review_questions", [])
    if not isinstance(review_questions, list):
        fail("review_questions", "list required")
    pending_blocking_questions = set()
    pending_nonblocking_questions = set()
    return_to_business = set()
    return_to_test_points = set()
    seen_review_qids = set()
    valid_evidence_refs = set(point_ids) | set(coverage_by_id)
    valid_evidence_refs |= {s.get("source_id") for s in confirmed_business.get("source_registry", []) if text(s.get("source_id"))}
    for group in ("modules", "business_objects", "events", "relationships", "invariants", "rules", "cross_module_flows"):
        key = {
            "modules":"module_id", "business_objects":"object_id", "events":"event_id",
            "relationships":"relationship_id", "invariants":"invariant_id",
            "rules":"rule_id", "cross_module_flows":"flow_id"
        }[group]
        valid_evidence_refs |= {x.get(key) for x in confirmed_business.get(group, []) if text(x.get(key))}
    for sm in confirmed_business.get("state_machines", []):
        valid_evidence_refs |= {t.get("transition_id") for t in sm.get("transitions", []) if text(t.get("transition_id"))}

    for i, q in enumerate(review_questions):
        p = f"review_questions[{i}]"
        qid = q.get("question_id")
        if not text(qid) or qid in seen_review_qids:
            fail(f"{p}.question_id", "unique non-empty required")
        seen_review_qids.add(qid)
        if q.get("status") not in {"pending", "resolved", "out_of_scope"}:
            fail(f"{p}.status", "invalid status")
        if q.get("category") not in {"case_design", "execution_dependency", "upstream_business", "upstream_test_point"}:
            fail(f"{p}.category", "invalid category")
        if not text(q.get("question")) or not text(q.get("why_needed")):
            fail(p, "question and why_needed required")
        if not isinstance(q.get("blocking"), bool):
            fail(f"{p}.blocking", "boolean required")
        if not isinstance(q.get("affects_expected"), bool):
            fail(f"{p}.affects_expected", "boolean required")
        evidence = q.get("evidence_checked")
        if not isinstance(evidence, list) or not evidence:
            fail(f"{p}.evidence_checked", "non-empty list required")
        unknown_evidence = set(evidence) - valid_evidence_refs
        if unknown_evidence:
            fail(f"{p}.evidence_checked", f"unknown evidence refs {sorted(unknown_evidence)}")
        if not text(q.get("impact_summary")):
            fail(f"{p}.impact_summary", "required")

        if q.get("affects_expected"):
            if q.get("category") != "upstream_business" or q.get("return_to_stage") != "business-understanding":
                fail(p, "expected-affecting question must return to business understanding")
        if q.get("missing_test_point") is True:
            if q.get("category") != "upstream_test_point" or q.get("return_to_stage") != "test-point-design":
                fail(p, "missing mechanism must return to test-point design")

        if q.get("status") == "pending":
            if not text(q.get("recommendation_reason")):
                fail(f"{p}.recommendation_reason", "required")
            mode = q.get("answer_mode", "choice")
            if mode not in {"choice", "open"}:
                fail(f"{p}.answer_mode", "must be choice or open")
            if mode == "choice":
                options = q.get("options")
                if not isinstance(options, list) or len(options) < 2:
                    fail(f"{p}.options", "choice question needs at least two options")
                option_ids=[]
                for j,opt in enumerate(options):
                    if not isinstance(opt,dict) or not text(opt.get("option_id")) or not text(opt.get("description")):
                        fail(f"{p}.options[{j}]", "option_id and description required")
                    if not text(opt.get("impact")):
                        fail(f"{p}.options[{j}].impact", "required")
                    option_ids.append(opt["option_id"])
                if q.get("recommended_option") not in option_ids:
                    fail(f"{p}.recommended_option", "must reference one option")
            else:
                if not text(q.get("recommended_answer")):
                    fail(f"{p}.recommended_answer", "required for open question")

            if q.get("affects_expected"):
                return_to_business.add(qid)
            if q.get("missing_test_point") is True:
                return_to_test_points.add(qid)
            if q.get("blocking") is True:
                pending_blocking_questions.add(qid)
            else:
                pending_nonblocking_questions.add(qid)

        if q.get("status") == "resolved" and not text(q.get("answer")):
            fail(f"{p}.answer", "required when resolved")

    expansions = v.get("expansion_records")
    if not isinstance(expansions, list) or not expansions:
        fail("expansion_records", "non-empty list required")
    expansion_tp_ids = ids(expansions, "tp_id", "expansion_records")
    unknown_expansion = expansion_tp_ids - point_ids
    if unknown_expansion:
        fail("expansion_records", f"unknown TP refs {sorted(unknown_expansion)}")
    missing_expansion = point_ids - expansion_tp_ids
    if missing_expansion:
        fail("expansion_records", f"test points without expansion {sorted(missing_expansion)}")

    templates = v.get("case_templates")
    if not isinstance(templates, list) or not templates:
        fail("case_templates", "non-empty list required")
    case_ids = ids(templates, "case_id", "case_templates")

    instances = v.get("execution_instances")
    if not isinstance(instances, list) or not instances:
        fail("execution_instances", "non-empty list required")
    instance_ids = ids(instances, "instance_id", "execution_instances")

    template_by_id = {c["case_id"]: c for c in templates}
    instance_by_id = {x["instance_id"]: x for x in instances}

    strategy_by_coverage = {
        "field_rule": {"equivalence_partition", "boundary_value", "decision_table", "combined"},
        "transition": {"state_transition", "combined"},
        "relation_lifecycle": {"relationship_lifecycle", "combined"},
        "failure_atomicity": {"failure_atomicity", "combined"},
        "recovery": {"recovery", "combined"},
        "concurrency": {"concurrency", "combined"},
        "stale_state": {"stale_state", "combined"},
        "scope_isolation": {"scope_isolation", "combined"},
        "long_flow": {"long_flow", "combined"},
        "cross_module": {"long_flow", "combined"},
    }

    # Expansion records -> instances.
    for i, exp in enumerate(expansions):
        p = f"expansion_records[{i}]"
        if exp.get("strategy") not in STRATEGIES:
            fail(f"{p}.strategy", f"unsupported strategy {exp.get('strategy')}")
        if not text(exp.get("rationale")):
            fail(f"{p}.rationale", "required")
        refs = exp.get("execution_instance_ids")
        if not isinstance(refs, list) or not refs:
            fail(f"{p}.execution_instance_ids", "non-empty required")
        unknown = set(refs) - instance_ids
        if unknown:
            fail(f"{p}.execution_instance_ids", f"unknown instances {sorted(unknown)}")
        tp = point_by_id[exp["tp_id"]]
        primary_cov = coverage_by_id.get(tp.get("primary_coverage_id"), {})
        cov_type = primary_cov.get("type")
        allowed = strategy_by_coverage.get(cov_type)
        if allowed is not None and exp.get("strategy") not in allowed:
            fail(f"{p}.strategy", f"{cov_type} should expand with one of {sorted(allowed)}, not {exp.get('strategy')}")
        if exp.get("strategy") == "boundary_value" and len(refs) < 3:
            fail(f"{p}.execution_instance_ids", "boundary_value expansion requires at least 3 independent instances")
        if exp.get("strategy") in {"equivalence_partition", "decision_table"} and len(refs) < 2:
            fail(f"{p}.execution_instance_ids", f"{exp.get('strategy')} expansion requires at least 2 independent instances")
        for iid in refs:
            if exp["tp_id"] not in instance_by_id[iid].get("test_point_ids", []):
                fail(f"{p}.execution_instance_ids", f"{iid} does not cover {exp['tp_id']}")

    all_assertion_ids = set()
    assertion_to_tp = {}
    case_to_assertions = {}

    for i, case in enumerate(templates):
        p = f"case_templates[{i}]"
        ctype = case.get("case_type")
        case_id = case.get("case_id")
        if not isinstance(case_id, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,95}", case_id):
            fail(f"{p}.case_id", "safe stable identifier required")
        if ctype not in CASE_TYPES:
            fail(f"{p}.case_type", f"unsupported case type {ctype}")
        if case.get("priority") not in PRIORITIES:
            fail(f"{p}.priority", "must be P0/P1/P2")
        if not text(case.get("title")):
            fail(f"{p}.title", "required")
        if not text(case.get("target_action")):
            fail(f"{p}.target_action", "explicit tested action required for Execution Planning")

        tpids = case.get("test_point_ids")
        if not isinstance(tpids, list) or not tpids:
            fail(f"{p}.test_point_ids", "non-empty required")
        unknown = set(tpids) - point_ids
        if unknown:
            fail(f"{p}.test_point_ids", f"unknown test points {sorted(unknown)}")
        highest_rank = min(priority_rank[point_priority[x]] for x in tpids)
        if priority_rank[case["priority"]] > highest_rank:
            fail(f"{p}.priority", "case priority cannot be lower than the highest-priority covered test point")

        if case.get("preconditions_applicable") is False:
            if case.get("preconditions") not in (None, [], {}):
                fail(f"{p}.preconditions", "must be empty when not applicable")
        else:
            if not isinstance(case.get("preconditions"), list) or not case.get("preconditions"):
                fail(f"{p}.preconditions", "non-empty list required unless not applicable")

        steps = case.get("steps")
        if not isinstance(steps, list) or not steps:
            fail(f"{p}.steps", "non-empty required")
        step_ids = set()
        for j, step in enumerate(steps):
            q = f"{p}.steps[{j}]"
            if not isinstance(step, dict) or not text(step.get("action")):
                fail(q, "step object with non-empty action required")
            if not text(step.get("step_id")):
                fail(f"{q}.step_id", "required")
            if step["step_id"] in step_ids:
                fail(f"{q}.step_id", "must be unique within the Case")
            step_ids.add(step["step_id"])

        assertions = case.get("assertions")
        if not isinstance(assertions, list) or not assertions:
            fail(f"{p}.assertions", "non-empty required")
        local_ids = set()
        covered_by_assertions = set()
        for j, a in enumerate(assertions):
            q = f"{p}.assertions[{j}]"
            aid = a.get("assertion_id")
            if not text(aid):
                fail(f"{q}.assertion_id", "required")
            if aid in all_assertion_ids or aid in local_ids:
                fail(f"{q}.assertion_id", "assertion ids must be globally unique")
            local_ids.add(aid)
            if a.get("checkpoint") not in CHECKPOINTS:
                fail(f"{q}.checkpoint", f"must be one of {sorted(CHECKPOINTS)}")
            if a["checkpoint"] in {"step", "intermediate"} and a.get("step_id") not in step_ids:
                fail(f"{q}.step_id", "step/intermediate checkpoint must reference an existing step")
            validate_expected(a.get("expected"), f"{q}.expected")
            atps = a.get("test_point_ids")
            if not isinstance(atps, list) or not atps:
                fail(f"{q}.test_point_ids", "non-empty required")
            unknown_tp = set(atps) - set(tpids)
            if unknown_tp:
                fail(f"{q}.test_point_ids", f"assertion TP refs must be within template refs: {sorted(unknown_tp)}")
            covered_by_assertions |= set(atps)
            assertion_to_tp[aid] = set(atps)

        all_assertion_ids |= local_ids
        case_to_assertions[case["case_id"]] = local_ids

        missing_assert = set(tpids) - covered_by_assertions
        if missing_assert:
            fail(f"{p}.assertions", f"test points without assertion mapping {sorted(missing_assert)}")

        policy = case.get("evidence_policy")
        if not isinstance(policy, dict) or policy.get("level") not in {"standard", "critical"}:
            fail(f"{p}.evidence_policy", "machine-readable level=standard|critical is required")
        if type(policy.get("recording_required")) is not bool:
            fail(f"{p}.evidence_policy.recording_required", "boolean required")
        required_evidence = policy.get("required")
        if not isinstance(required_evidence, list):
            fail(f"{p}.evidence_policy.required", "list required")
        for k, item in enumerate(required_evidence):
            ep = f"{p}.evidence_policy.required[{k}]"
            if not isinstance(item, dict) or not text(item.get("kind")):
                fail(ep, "evidence kind required")
            if item["kind"] not in EVIDENCE_KINDS:
                fail(f"{ep}.kind", f"unsupported evidence kind {item['kind']}")
            assertion_ids = item.get("assertion_ids")
            if not isinstance(assertion_ids, list) or not assertion_ids or len(assertion_ids) != len(set(assertion_ids)):
                fail(f"{ep}.assertion_ids", "non-empty unique assertion ids required")
            if not set(assertion_ids) <= local_ids:
                fail(f"{ep}.assertion_ids", "must reference assertions in this Case")
            if item["kind"] == "request_response" and item.get("redacted") is not True:
                fail(f"{ep}.redacted", "request_response evidence must require redaction")
        if policy["level"] == "critical" and policy["recording_required"] is not True:
            fail(f"{p}.evidence_policy.recording_required", "critical evidence policy requires recording")

        if len(tpids) > 1:
            if not text(case.get("merge_rationale")):
                fail(f"{p}.merge_rationale", "required for multi-TP template")
            if case.get("failure_masking_review") != "passed":
                fail(f"{p}.failure_masking_review", "must be passed for multi-TP template")
            if ctype in PROTECTED_MERGE_TYPES and not text(case.get("merge_exception_reason")):
                fail(f"{p}.merge_exception_reason", f"required when merging multiple TPs in protected case type {ctype}")

        verification = case.get("verification_dimensions", [])
        if not isinstance(verification, list):
            fail(f"{p}.verification_dimensions", "list required")
        if ctype == "failure_atomicity":
            if "operation_result" not in verification:
                fail(f"{p}.verification_dimensions", "failure_atomicity requires operation_result")
            if not set(verification) & {"state", "data", "relationship", "downstream"}:
                fail(f"{p}.verification_dimensions", "failure_atomicity requires at least one final-fact dimension")
        if ctype == "recovery":
            phases = case.get("workflow_phases")
            required = {"failure", "repair", "reentry", "recovery_assertion", "continuity_assertion"}
            if not isinstance(phases, list) or not required <= set(phases):
                fail(f"{p}.workflow_phases", f"recovery requires phases {sorted(required)}")
        if ctype == "concurrency":
            cm = case.get("concurrency_model")
            if not isinstance(cm, dict):
                fail(f"{p}.concurrency_model", "required")
            actors = cm.get("actors")
            if not isinstance(actors, list) or len(actors) < 2:
                fail(f"{p}.concurrency_model.actors", "at least two actors required")
            for key in ("sync_point", "submission_order", "final_fact"):
                if not text(cm.get(key)):
                    fail(f"{p}.concurrency_model.{key}", "required")
        if ctype in {"long_flow", "cross_module"}:
            intermediate = [a for a in assertions if a.get("checkpoint") == "intermediate"]
            if len(intermediate) < 2:
                fail(f"{p}.assertions", "long_flow/cross_module requires at least two intermediate assertions")

    # Instances.
    instances_by_case = {cid: [] for cid in case_ids}
    point_instance_coverage = {pid: set() for pid in point_ids}
    point_assertion_coverage = {pid: set() for pid in point_ids}
    for aid, tps in assertion_to_tp.items():
        for pid in tps:
            point_assertion_coverage[pid].add(aid)

    for i, inst in enumerate(instances):
        p = f"execution_instances[{i}]"
        cid = inst.get("case_id")
        if cid not in case_ids:
            fail(f"{p}.case_id", "unknown test case item")
        instances_by_case[cid].append(inst["instance_id"])

        tpids = inst.get("test_point_ids")
        if not isinstance(tpids, list) or not tpids:
            fail(f"{p}.test_point_ids", "non-empty required")
        template_tpids = set(template_by_id[cid].get("test_point_ids", []))
        unknown = set(tpids) - template_tpids
        if unknown:
            fail(f"{p}.test_point_ids", f"instance TP refs not covered by template {sorted(unknown)}")
        for pid in tpids:
            point_instance_coverage[pid].add(inst["instance_id"])

        if not text(inst.get("variation")):
            fail(f"{p}.variation", "required")
        if not isinstance(inst.get("test_data"), (dict, list)):
            fail(f"{p}.test_data", "dict or list required")
        eids = inst.get("expected_assertion_ids")
        if not isinstance(eids, list) or not eids:
            fail(f"{p}.expected_assertion_ids", "non-empty required")
        if len(eids) != len(set(eids)):
            fail(f"{p}.expected_assertion_ids", "duplicate assertion id")
        instance_id = inst.get("instance_id")
        if not isinstance(instance_id, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,95}", instance_id):
            fail(f"{p}.instance_id", "safe stable identifier required")
        unknown_a = set(eids) - case_to_assertions[cid]
        if unknown_a:
            fail(f"{p}.expected_assertion_ids", f"unknown assertions for case {sorted(unknown_a)}")
        if inst.get("result_tracking", {}).get("independent") is not True:
            fail(f"{p}.result_tracking.independent", "must be true")

        # Every instance must actually assert its declared TPs.
        asserted_tps = set()
        for aid in eids:
            asserted_tps |= assertion_to_tp[aid]
        if asserted_tps != set(tpids):
            missing = sorted(set(tpids) - asserted_tps)
            extra = sorted(asserted_tps - set(tpids))
            fail(f"{p}.expected_assertion_ids", f"assertion TP coverage must exactly match instance TPs; missing={missing}, extra={extra}")

    policy_assertion_ids = {
        assertion_id
        for case in templates
        for item in case["evidence_policy"]["required"]
        for assertion_id in item["assertion_ids"]
    }
    included_assertion_ids = {
        assertion_id for instance in instances for assertion_id in instance["expected_assertion_ids"]
    }
    missing_policy_assertions = policy_assertion_ids - included_assertion_ids
    if missing_policy_assertions:
        fail("evidence_policy", f"required evidence assertions are not assigned to any execution instance: {sorted(missing_policy_assertions)}")

    # Every template must have an instance; parameterized means 2+.
    for i, case in enumerate(templates):
        cid = case["case_id"]
        count = len(instances_by_case.get(cid, []))
        if count == 0:
            fail(f"case_templates[{i}]", "test case item has no executable scenario")
        if case["case_type"] == "parameterized" and count < 2:
            fail(f"case_templates[{i}]", "parameterized test case requires at least two independently executable data groups")

    missing_instance = sorted(pid for pid, refs in point_instance_coverage.items() if not refs)
    if missing_instance:
        fail("instance_coverage", f"test points without executable scenarios {missing_instance}")
    missing_assert = sorted(pid for pid, refs in point_assertion_coverage.items() if not refs)
    if missing_assert:
        fail("assertion_coverage", f"test points without assertions {missing_assert}")

    review = v.get("test_cases_self_review")
    if not isinstance(review, dict) or review.get("status") != "passed":
        fail("test_cases_self_review.status", "must be passed")
    required_checks = {
        "point_coverage_complete",
        "instance_coverage_complete",
        "assertion_mapping_complete",
        "failure_masking_checked",
        "parameterization_checked",
        "complex_cases_checked",
        "no_unresolved_expected",
    }
    for key in required_checks:
        if review.get(key) is not True:
            fail(f"test_cases_self_review.{key}", "must be true")

    presentation = v.get("presentation_sync")
    if not isinstance(presentation, dict) or presentation.get("status") != "passed":
        fail("presentation_sync.status", "must be passed")
    checks = presentation.get("checks")
    if not isinstance(checks, dict):
        fail("presentation_sync.checks", "object required")
    for key in ("main_document_updated", "review_document_updated", "pending_questions_reflected", "model_consistency_checked"):
        if checks.get(key) is not True:
            fail(f"presentation_sync.checks.{key}", "must be true")

    ready = not pending_blocking_questions and not return_to_business and not return_to_test_points
    if require_confirmed:
        if return_to_business:
            fail("review_questions", f"business expected is unresolved; return to business understanding: {sorted(return_to_business)}")
        if return_to_test_points:
            fail("review_questions", f"test mechanism is missing; return to test-point design: {sorted(return_to_test_points)}")
        if pending_blocking_questions:
            fail("review_questions", f"pending blocking review questions: {sorted(pending_blocking_questions)}")

    return {
        "ok": True,
        "case_design_version": v["case_design_version"],
        "business_model_version": v["business_model_version"],
        "test_point_version": v["test_point_version"],
        "test_points": len(point_ids),
        "case_templates": len(templates),
        "execution_instances": len(instances),
        "multi_tp_templates": sum(1 for c in templates if len(c.get("test_point_ids", [])) > 1),
        "parameterized_templates": sum(1 for c in templates if c.get("case_type") == "parameterized"),
        "tp_instance_coverage": f"{len(point_ids)}/{len(point_ids)}",
        "pending_blocking_questions": sorted(pending_blocking_questions),
        "pending_nonblocking_questions": sorted(pending_nonblocking_questions),
        "return_to_business_understanding": bool(return_to_business),
        "return_to_test_point_design": bool(return_to_test_points),
        "ready_for_confirmation": ready,
    }


def project_execution_cases(v):
    """Compile the confirmed design model into deterministic, instance-level Runtime Cases.

    Call only after validate() succeeds. The source Case Design remains the single
    authority; this projection is recomputed by each downstream consumer.
    """
    templates = {case["case_id"]: case for case in v["case_templates"]}
    instances_by_case = {case_id: [] for case_id in templates}
    for instance in v["execution_instances"]:
        instances_by_case[instance["case_id"]].append(instance)

    result = []
    for template_id, template in templates.items():
        instances = instances_by_case[template_id]
        for instance in instances:
            case_id = template_id if len(instances) == 1 else f"{template_id}--{instance['instance_id']}"
            assertion_by_id = {item["assertion_id"]: item for item in template["assertions"]}
            expected_results = [
                {
                    "id": assertion_id,
                    "expected": assertion_by_id[assertion_id]["expected"],
                    "checkpoint": assertion_by_id[assertion_id]["checkpoint"],
                    **({"step_id": assertion_by_id[assertion_id]["step_id"]} if assertion_by_id[assertion_id]["checkpoint"] in {"step", "intermediate"} else {}),
                }
                for assertion_id in instance["expected_assertion_ids"]
            ]
            result.append({
                "case_id": case_id,
                "title": template["title"],
                "steps": template["steps"],
                "expected_results": expected_results,
                "target_action": template["target_action"],
                "test_point_ids": instance["test_point_ids"],
                "preconditions": template.get("preconditions", []),
                "test_data": instance["test_data"],
                "template_case_id": template_id,
                "execution_instance_id": instance["instance_id"],
                "evidence_policy": {
                    **template["evidence_policy"],
                    "required": [
                        {**item, "assertion_ids": [aid for aid in item["assertion_ids"] if aid in set(instance["expected_assertion_ids"])]}
                        for item in template["evidence_policy"]["required"]
                        if set(item["assertion_ids"]) & set(instance["expected_assertion_ids"])
                    ],
                },
            })
    ids_out = [case["case_id"] for case in result]
    if len(ids_out) != len(set(ids_out)):
        fail("execution_case_projection", "projected Runtime Case IDs must be unique")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--points", required=True)
    parser.add_argument("--business", required=True)
    parser.add_argument("--allow-waiting-confirmation", action="store_true")
    args = parser.parse_args()
    cases = load(args.input)
    points = load(args.points)
    business = load(args.business)
    print(json.dumps(
        validate(cases, points, business, require_confirmed=not args.allow_waiting_confirmation),
        ensure_ascii=False,
        indent=2,
    ))
