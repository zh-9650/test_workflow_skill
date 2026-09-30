import importlib.util
import hashlib
import json
from pathlib import Path
import pytest

_ctl_path = Path(__file__).resolve().parents[1] / "execution_control.py"
_ctl_spec = importlib.util.spec_from_file_location("execution_control", _ctl_path)
_ctl = importlib.util.module_from_spec(_ctl_spec)
_ctl_spec.loader.exec_module(_ctl)


def _base_plan_case(mode="required", target_type="api_semantic_judgment", max_cost=0.05):
    return {
        "case_id": "TC-API-001",
        "batch_id": "B01",
        "primary_execution": "API",
        "expected_results": [
            {"id": "E1", "expected": "HTTP 200 returned"}
        ],
        "jev_policy": {
            "mode": mode,
            "target_type": target_type,
            "purpose": "semantic evaluation of response excerpt",
            "trigger_condition": "response received",
            "bounded_options": ["valid", "invalid"],
            "failure_fallback": "mark_step_fail",
            "max_cost_usd": max_cost,
            "max_cost_per_call_usd": min(max_cost, 0.01),
            "max_calls": 1,
            "max_input_chars": 4096,
            "provider": "typesafe-official",
            "model": "jev-1.13.0",
            "model_version": "1.13.0",
            "required_evidence": ["request", "response", "source_response", "usage", "reviewer_independent_judgment"],
            "expected_ids": ["E1"]
        }
    }


def _dummy_hash(val="1"):
    return (val * 64)[:64]


def _write(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _valid_invocation(tmp_path, pc):
    root = tmp_path / "evidence/B01/TC-API-001/jev"
    policy_hash = hashlib.sha256(json.dumps(pc["jev_policy"], ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    refs = {}
    for name, payload in {
        "request": {"case_id": "TC-API-001", "expected_id": "E1", "target_type": "api_semantic_judgment", "policy_sha256":policy_hash},
        "response": {"model":"jev-1.13.0","answers":{"judgment":{"choice":"valid","confidence":0.95}}},
        "source_response": {"status": 200, "body_excerpt": "safe redacted excerpt"},
        "usage": {"cost_usd": 0.003, "prompt_tokens": 10, "completion_tokens": 2},
    }.items():
        path = root / f"{name}.json"
        digest = _write(path, payload)
        refs[f"{name}_ref"] = str(path.relative_to(tmp_path)).replace("\\", "/")
        refs[f"{name}_sha256"] = digest
    policy_hash = hashlib.sha256(json.dumps(pc["jev_policy"], ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return {
        "target_type": "api_semantic_judgment",
        "provider": "typesafe-official",
        "model": "jev-1.13.0",
        "model_version": "1.13.0",
        "policy_sha256": policy_hash,
        "cost_usd": 0.003,
        "confidence": 0.95,
        "expected_id": "E1",
        "selected_option": "valid",
        **refs,
    }


def test_runtime_rejects_none_mode_with_invocations():
    pc = _base_plan_case(mode="none")
    result = {
        "case_id": "TC-API-001",
        "status": "PASS",
        "jev_invocations": [{"cost_usd": 0.001}]
    }
    with pytest.raises(AssertionError, match="mode is none"):
        _ctl._validate_jev_execution(pc, result, evidence_root=None)


def test_runtime_rejects_required_without_invocations():
    pc = _base_plan_case(mode="required")
    result = {
        "case_id": "TC-API-001",
        "status": "PASS",
        "jev_invocations": []
    }
    with pytest.raises(AssertionError, match="PASS forbidden: planned required Jev invocation"):
        _ctl._validate_jev_execution(pc, result, evidence_root=None)


def test_runtime_rejects_budget_exceeded(tmp_path):
    pc = _base_plan_case(mode="required", max_cost=0.01)
    invocation = _valid_invocation(tmp_path, pc)
    invocation["cost_usd"] = 0.02
    result = {
        "case_id": "TC-API-001",
        "status": "PASS",
        "jev_invocations": [invocation]
    }
    with pytest.raises(AssertionError, match="exceeds planned max_cost_usd"):
        _ctl._validate_jev_execution(pc, result, evidence_root=tmp_path)


def test_runtime_rejects_confidence_out_of_range(tmp_path):
    pc = _base_plan_case(mode="required")
    invocation = _valid_invocation(tmp_path, pc)
    invocation["confidence"] = 1.2
    result = {
        "case_id": "TC-API-001",
        "status": "PASS",
        "jev_invocations": [invocation]
    }
    with pytest.raises(AssertionError, match="confidence must be a number between 0.0 and 1.0"):
        _ctl._validate_jev_execution(pc, result, evidence_root=tmp_path)


def test_runtime_rejects_wrong_expected_id(tmp_path):
    pc = _base_plan_case(mode="required")
    invocation = _valid_invocation(tmp_path, pc)
    invocation["expected_id"] = "E999"
    result = {
        "case_id": "TC-API-001",
        "status": "PASS",
        "jev_invocations": [invocation]
    }
    with pytest.raises(AssertionError, match="must map to planned expected_ids"):
        _ctl._validate_jev_execution(pc, result, evidence_root=tmp_path)


def test_runtime_conditional_skipped_requires_reason():
    pc = _base_plan_case(mode="conditional")
    result = {
        "case_id": "TC-API-001",
        "status": "PASS"
    }
    with pytest.raises(AssertionError, match="non-empty jev_skipped_reason required"):
        _ctl._validate_jev_execution(pc, result, evidence_root=None)


def test_runtime_conditional_skipped_with_reason_passes():
    pc = _base_plan_case(mode="conditional")
    result = {
        "case_id": "TC-API-001",
        "status": "PASS",
        "jev_skipped_reason": "Deterministic locator succeeded without fallback"
    }
    # Should not raise
    _ctl._validate_jev_execution(pc, result, evidence_root=None)


def test_runtime_rejects_legacy_singular_invocation(tmp_path):
    pc = _base_plan_case(mode="required")
    result = {"case_id": "TC-API-001", "status": "PASS", "jev_invocation": _valid_invocation(tmp_path, pc)}
    with pytest.raises(AssertionError, match="jev_invocations"):
        _ctl._validate_jev_execution(pc, result, evidence_root=tmp_path)


def test_runtime_rejects_self_reported_hashes_without_files(tmp_path):
    pc = _base_plan_case(mode="required")
    invocation = _valid_invocation(tmp_path, pc)
    invocation["response_ref"] = "evidence/B01/TC-API-001/jev/missing.json"
    result = {"case_id": "TC-API-001", "status": "PASS", "jev_invocations": [invocation]}
    with pytest.raises(AssertionError, match="file does not exist"):
        _ctl._validate_jev_execution(pc, result, evidence_root=tmp_path)


def test_runtime_valid_invocations_passes(tmp_path):
    pc = _base_plan_case(mode="required")
    result = {
        "case_id": "TC-API-001",
        "status": "PASS",
        "jev_invocations": [_valid_invocation(tmp_path, pc)]
    }
    _ctl._validate_jev_execution(pc, result, evidence_root=tmp_path)


def test_runtime_required_invocations_cover_every_expected(tmp_path):
    pc=_base_plan_case(); pc['jev_policy']['expected_ids']=['E1','E2']
    result={'case_id':'TC-API-001','status':'PASS','jev_invocations':[_valid_invocation(tmp_path,pc)]}
    with pytest.raises(AssertionError,match='every planned Expected ID'):
        _ctl._validate_jev_execution(pc,result,evidence_root=tmp_path)


def test_required_jev_is_not_fabricated_for_unexecuted_blocked():
    pc=_base_plan_case()
    result={'status':'BLOCKED','target_action_executed':False,'actual_execution':'NOT_EXECUTED','jev_skipped_reason':'Upstream failure prevented planned step'}
    _ctl._validate_jev_execution(pc,result,evidence_root=None)


def test_required_blocked_without_skip_reason_is_rejected():
    with pytest.raises(AssertionError,match='jev_skipped_reason'):
        _ctl._validate_jev_execution(_base_plan_case(),{'status':'BLOCKED','target_action_executed':False,'actual_execution':'NOT_EXECUTED'},evidence_root=None)
