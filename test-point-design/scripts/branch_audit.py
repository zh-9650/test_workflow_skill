"""Business-meaning-preserving branch gate for test-point-design v1.1.

This checks declared traceability and some logical contradictions, NOT business truth.
The original test_point_contract.py remains authoritative for the legacy shape.
"""
import argparse
import json
from pathlib import Path


def required(condition, where, reason):
    if not condition:
        raise AssertionError(f"{where}: {reason}")


def nonempty(x):
    return isinstance(x, str) and bool(x.strip())


def unique(rows, key, where):
    required(isinstance(rows, list), where, "list required")
    values = []
    for i, row in enumerate(rows):
        required(isinstance(row, dict), f"{where}[{i}]", "object required")
        v = row.get(key)
        required(nonempty(v), f"{where}[{i}].{key}", "nonempty string required")
        values.append(v)
    required(len(set(values)) == len(values), where, f"duplicate {key}")
    return {row[key]: row for row in rows}


def refs_of(rows, key):
    return {r[key] for r in rows}


def validate(design, business, effect=None, *, strict=False):
    required(isinstance(design, dict) and isinstance(business, dict), "input", "objects required")
    required(str(design.get("schema_version")) == "1.1", "schema_version", "new run requires 1.1; legacy designs use legacy contract only")
    required(design.get("business_model_version") == business.get("model_version"), "business_model_version", "wrong business model")
    block = design.get("branch_design")
    required(isinstance(block, dict), "branch_design", "required for new runs")
    coverage = unique(design.get("coverage_obligations", []), "coverage_id", "coverage_obligations")
    points = unique(design.get("test_points", []), "tp_id", "test_points")
    questions = unique(design.get("design_questions", []), "question_id", "design_questions")
    branches = unique(block.get("branches", []), "branch_id", "branch_design.branches")
    required(branches, "branch_design.branches", "at least one concrete business branch required")
    plans = unique(block.get("coverage_plan", []), "coverage_id", "branch_design.coverage_plan")
    required(set(plans) == set(coverage), "branch_design.coverage_plan", "every coverage obligation requires exactly one plan")

    for cid, cov in coverage.items():
        p = f"coverage_plan[{cid}]"
        plan = plans[cid]
        mapped = plan.get("branch_ids", [])
        required(isinstance(mapped, list), p, "branch_ids must be list")
        required(set(mapped) <= set(branches), p, "unknown branch id")
        mode = plan.get("mode")
        if cov.get("status") == "covered":
            required(mode in {"single", "conditional"}, p, "covered requires single or conditional")
            required(mapped, p, "covered has no branches; label alone is not coverage")
            if mode == "conditional":
                required(len(set(mapped)) >= 2, p, "conditional mechanism must preserve at least two distinct outcomes")
        else:
            required(mode == "not_covered", p, "excluded or unresolved coverage cannot have an effective expectation")
            required(not mapped, p, "non-covered coverage must not reference active branches")

    plan_branches = {bid for p in plans.values() for bid in p.get("branch_ids", [])}
    required(set(branches) == plan_branches, "branch_design.branches", "orphan branch without any coverage obligation")
    high_risk = {"failure_atomicity", "recovery", "concurrency", "stale_state", "long_flow", "cross_module", "authorization", "data_consistency", "relation_lifecycle"}
    for bid, b in branches.items():
        p = f"branch[{bid}]"
        bc = b.get("coverage_ids")
        pt = b.get("test_point_ids")
        required(isinstance(bc, list) and bc, p, "coverage_ids required")
        required(isinstance(pt, list) and pt, p, "test_point_ids required")
        required(set(bc) <= set(coverage), p, "unknown coverage")
        required(set(pt) <= set(points), p, "unknown test point")
        required(all(coverage[c].get("status") == "covered" and bid in plans[c].get("branch_ids", []) for c in bc), p, "branch/coverage relation not reciprocal")
        required(all(any(cid in points[t].get("source_coverage_ids", []) for t in pt) for cid in bc), p, "some branch coverage is absent from all mapped test points")
        for cid in bc:
            required(any(t in coverage[cid].get("test_point_ids", []) for t in pt), p, "branch test point must be linked from covered obligation")
        for name in ("condition", "expected_result", "evidence_basis", "observable_fact"):
            required(nonempty(b.get(name)), p, f"{name} required; cannot use labels alone")
        required(b.get("certainty") in {"confirmed", "derived"}, p, "unknown expectation cannot be an executable branch")
        if b["certainty"] == "derived":
            required(nonempty(b.get("derivation")), p, "derived branch must justify inference")
        handoff = b.get("case_handoff")
        required(isinstance(handoff, dict), p, "case_handoff required")
        for name in ("variation_axis", "data_condition", "oracle"):
            required(nonempty(handoff.get(name)), p, f"case_handoff.{name} required for next stage")
        if any(coverage[c].get("type") in high_risk for c in bc):
            required(nonempty(b.get("false_success")), p, "high risk branch needs a discriminating false-success challenge")
        required(isinstance(b.get("claim_ids", []), list), p, "claim_ids must be list")

    # A point can cover different branch outcomes without exploding into one TP per data example.
    for tid, tp in points.items():
        mapped = {bid for bid, b in branches.items() if tid in b["test_point_ids"]}
        required(mapped, f"test_point[{tid}]", "point lacks preserved decision branches")
        for cid in tp.get("source_coverage_ids", []):
            if cid in coverage and coverage[cid].get("status") == "covered":
                required(mapped.intersection(plans[cid]["branch_ids"]), f"test_point[{tid}]", f"no branch for associated coverage {cid}")

    if effect is None:
        required(not strict, "effect-ledger", "strict v3.3 handoff requires effect-ledger.json")
        return {"ok": True, "limited": True, "reason": "effective source clauses not supplied; not eligible for official v3.3 handoff", "branches": len(branches)}

    required(effect.get("model_version") == business.get("model_version"), "effect.model_version", "version mismatch")
    clauses = unique(effect.get("clauses", []), "id", "effect.clauses")
    decisions = unique(block.get("claim_dispositions", []), "claim_id", "branch_design.claim_dispositions")
    required(set(clauses) == set(decisions), "branch_design.claim_dispositions", "every effective original clause must have a scope disposition")
    for claim_id, c in clauses.items():
        dp = decisions[claim_id];scope=c.get("scope")
        cp=f"claim[{claim_id}]"
        required(scope in {"active", "excluded", "superseded", "unresolved", "dependency"},cp,"unknown scope")
        linked = dp.get("coverage_ids", [])
        required(isinstance(linked, list) and set(linked) <= set(coverage), cp, "invalid coverage IDs")
        if scope == "active":
            required(dp.get("decision") in {"covered", "pending"}, cp, "active clause must have verified business outcome or explicit unresolved design question")
            if dp["decision"] == "covered":
                required(linked and all(coverage[cid].get("status") == "covered" for cid in linked), cp, "active claim linked to non-covered or no coverage")
                required(any(claim_id in b.get("claim_ids",[]) for b in branches.values() if set(b["coverage_ids"]) & set(linked)), cp, "a source ID in a table is insufficient; no concrete branch")
                model_refs = set(c.get("model_refs", []))
                if model_refs and not any(model_refs & set(coverage[cid].get("source_model_refs", [])) for cid in linked):
                    required(nonempty(dp.get("trace_explanation")), cp, "claim and chosen coverage lack direct business mechanism overlap; explain actual indirect lineage")
            else:
                q = dp.get("question_id")
                required(q in questions and questions[q].get("status") == "pending", cp, "pending active claim requires open design/upstream question")
                required(not linked or all(coverage[cid].get("status") == "pending_confirmation" for cid in linked),cp,"pending cannot point at definitive coverage")
        elif scope in {"excluded", "superseded"}:
            required(dp.get("decision") == "excluded", cp, "retired clause may not turn into current correct behavior")
            required(not linked, cp, "retired clause must not be mapped to current coverage")
            required(nonempty(dp.get("reason")), cp, "scope exclusion reason required")
            required(all(claim_id not in b.get("claim_ids",[]) for b in branches.values()),cp,"retired clause revived in executable branch")
        else:
            if scope == "unresolved":
                required(dp.get("decision") == "pending", cp, "unresolved business truth cannot be disguised as external dependency")
                required(dp.get("question_id") in questions and questions[dp["question_id"]].get("status") == "pending", cp, "unresolved claim requires a pending upstream question")
            else:
                required(dp.get("decision") in {"pending", "dependency"}, cp,"external claim may not become definitive product behavior")
            required(not linked or all(coverage[cid].get("status") == "pending_confirmation" for cid in linked),cp,"not confirmed but current coverage is definitive")

    for bid,b in branches.items():
        required(b.get("claim_ids"),f"branch[{bid}]","v3.3 branch must cite effective clause")
        required(set(b["claim_ids"]) <= set(clauses),f"branch[{bid}]","unknown claim ID")
        required(all(clauses[x].get("scope") == "active" for x in b["claim_ids"]),f"branch[{bid}]","non-active clause used as expected business truth")

    discr = unique(effect.get("discriminators", []), "id", "effect.discriminators")
    dreviews = unique(block.get("discriminator_reviews", []), "discriminator_id", "branch_design.discriminator_reviews")
    required(set(dreviews) == set(discr), "discriminator_reviews", "all inherited counterexamples must be accounted for")
    for did, d in discr.items():
        dr=dreviews[did]; p=f"discriminator[{did}]";status=dr.get("status")
        required(status in {"covered","pending","excluded"},p,"unsupported status")
        if status == "covered":
            required(d.get("confidence") in {"confirmed","derived"},p,"unconfirmed source example cannot become definitive test oracle")
            aids=dr.get("branch_ids",[])
            required(len(set(aids))>=2 and set(aids)<=set(branches),p,"both distinguishable outcomes require real branches")
            required(len(set(branches[x]["expected_result"] for x in aids))>=2,p,"two labels with identical outcomes do not discriminate")
            if d.get("clause_refs"):
                required(set(d["clause_refs"]) <= set(clauses),p,"discriminator cites unknown source clause")
                required(all(set(branches[x].get("claim_ids", [])) & set(d["clause_refs"]) for x in aids),p,"discriminator branch not linked to the original effective decision clause")
        elif status == "pending":
            required(dr.get("question_id") in questions and questions[dr["question_id"]].get("status")=="pending",p,"unknown discriminator needs real question")
        else:
            required(nonempty(dr.get("reason")),p,"exclusion needs source-supported reason")

    paths = unique(effect.get("critical_paths", []), "id", "effect.critical_paths")
    pre = unique(block.get("path_reviews", []), "path_id", "branch_design.path_reviews")
    required(set(pre)==set(paths), "path_reviews", "all 3.3 key paths must be accounted for")
    for fid,f in paths.items():
        pr=pre[fid]; p=f"path[{fid}]"
        required(pr.get("status") in {"covered","pending","excluded"},p,"status required")
        if pr["status"]=="covered":
            required(pr.get("terminal_branch_ids"),p,"no terminal outcome of user task")
            required(set(pr["terminal_branch_ids"])<=set(branches),p,"unknown terminal branch")
            if f.get("clause_refs"):
                required(set(f["clause_refs"]) <= set(clauses),p,"path has unknown source clause")
                required(any(set(branches[x].get("claim_ids", [])) & set(f["clause_refs"]) for x in pr["terminal_branch_ids"]),p,"path terminal branches not grounded in this user task")
            if f.get("interruptions"):
                required(pr.get("interruption_branch_ids") and set(pr["interruption_branch_ids"])<=set(branches),p,"interruption/final failure not followed")
            if f.get("interleavings"):
                required(pr.get("interleaving_branch_ids") and set(pr["interleaving_branch_ids"])<=set(branches),p,"cross timing fact not followed")
        elif pr["status"]=="pending":
            required(pr.get("question_id") in questions and questions[pr["question_id"]].get("status")=="pending",p,"pending requires question")
        else:
            required(nonempty(pr.get("reason")),p,"path exclusion reason required")

    # Retired terms are hints, not automatic truth judgments. A valid negative
    # constraint can mention a retired feature. Require explicit disposition.
    scope_flags=[]
    markers=unique(effect.get("retired_markers", []), "id", "effect.retired_markers")
    reviews=block.get("retired_marker_reviews", [])
    required(isinstance(reviews,list), "retired_marker_reviews", "list required")
    reviewed=set()
    for i,r in enumerate(reviews):
        key=(r.get("branch_id"),r.get("marker_id"))
        required(r.get("branch_id") in branches and r.get("marker_id") in markers,f"retired_marker_reviews[{i}]","invalid branch or marker")
        required(key not in reviewed,f"retired_marker_reviews[{i}]","duplicate")
        required(r.get("assessment") in {"negative_constraint","historical_context","unrelated_phrase"},f"retired_marker_reviews[{i}]","must explain why retired term is not positive product behavior")
        required(nonempty(r.get("evidence")),f"retired_marker_reviews[{i}]","source-based rationale required")
        reviewed.add(key)
    for bid,b in branches.items():
        positive=" ".join(str(b.get(k,"")) for k in ("condition","expected_result","observable_fact"))
        for mid,m in markers.items():
            word=m.get("text","")
            if nonempty(word) and word in positive:
                scope_flags.append((bid,mid))
                required((bid,mid) in reviewed, f"branch[{bid}]",f"retired marker {mid} mentioned in effective branch: inspect actual polarity and log retired_marker_reviews")
    required(reviewed <= set(scope_flags), "retired_marker_reviews", "review entry has no matching marked text")

    pending=[x for x in decisions.values() if x.get("decision")=="pending"]
    pending += [x for x in dreviews.values() if x.get("status")=="pending"]
    pending += [x for x in pre.values() if x.get("status")=="pending"]
    if strict:
        required(not pending,"branch_design","outstanding scope/expected ambiguities; can only deliver as candidate")
    return {"ok": True, "limited": False, "business_version":business["model_version"],"branches":len(branches),"claims":len(clauses),"discriminators":len(discr),"paths":len(paths),"pending_review_items":len(pending),"retired_marker_reviews":len(scope_flags),"ready_for_semantic_review":not pending}


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--business", required=True)
    ap.add_argument("--effect-ledger")
    ap.add_argument("--strict", action="store_true")
    a=ap.parse_args()
    read=lambda p: json.loads(Path(p).read_text(encoding="utf-8"))
    print(json.dumps(validate(read(a.input),read(a.business),read(a.effect_ledger) if a.effect_ledger else None,strict=a.strict),ensure_ascii=False,indent=2))


if __name__ == "__main__":
    main()
