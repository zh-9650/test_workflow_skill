import importlib.util
from pathlib import Path
import pytest

_ctl_path = Path(__file__).resolve().parents[1] / "execution_control.py"
_ctl_spec = importlib.util.spec_from_file_location("execution_control", _ctl_path)
_ctl = importlib.util.module_from_spec(_ctl_spec)
_ctl_spec.loader.exec_module(_ctl)


def _base_plan_case(mode="required", target_type="api_semantic_judgment", max_cost=0.05):
    return {
        "case_id": "TC-API-001",
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
            "expected_ids": ["E1"]
        }
    }


def _dummy_hash(val="1"):
    return (val * 64)[:64]


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


def test_runtime_rejects_budget_exceeded():
    pc = _base_plan_case(mode="required", max_cost=0.01)
    result = {
        "case_id": "TC-API-001",
        "status": "PASS",
        "jev_invocations": [
            {
                "target_type": "api_semantic_judgment",
                "request_sha256": _dummy_hash("a"),
                "response_sha256": _dummy_hash("b"),
                "cost_usd": 0.02,
                "confidence": 0.95,
                "expected_id": "E1"
            }
        ]
    }
    with pytest.raises(AssertionError, match="exceeds planned max_cost_usd"):
        _ctl._validate_jev_execution(pc, result, evidence_root=None)


def test_runtime_rejects_confidence_out_of_range():
    pc = _base_plan_case(mode="required")
    result = {
        "case_id": "TC-API-001",
        "status": "PASS",
        "jev_invocations": [
            {
                "target_type": "api_semantic_judgment",
                "request_sha256": _dummy_hash("a"),
                "response_sha256": _dummy_hash("b"),
                "cost_usd": 0.005,
                "confidence": 1.2,
                "expected_id": "E1"
            }
        ]
    }
    with pytest.raises(AssertionError, match="confidence must be a number between 0.0 and 1.0"):
        _ctl._validate_jev_execution(pc, result, evidence_root=None)


def test_runtime_rejects_wrong_expected_id():
    pc = _base_plan_case(mode="required")
    result = {
        "case_id": "TC-API-001",
        "status": "PASS",
        "jev_invocations": [
            {
                "target_type": "api_semantic_judgment",
                "request_sha256": _dummy_hash("a"),
                "response_sha256": _dummy_hash("b"),
                "cost_usd": 0.005,
                "confidence": 0.9,
                "expected_id": "E999"
            }
        ]
    }
    with pytest.raises(AssertionError, match="must map to planned expected_ids"):
        _ctl._validate_jev_execution(pc, result, evidence_root=None)


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


def test_runtime_valid_invocations_passes():
    pc = _base_plan_case(mode="required")
    result = {
        "case_id": "TC-API-001",
        "status": "PASS",
        "jev_invocations": [
            {
                "target_type": "api_semantic_judgment",
                "request_sha256": _dummy_hash("a"),
                "response_sha256": _dummy_hash("b"),
                "cost_usd": 0.003,
                "confidence": 0.95,
                "expected_id": "E1"
            }
        ]
    }
    # Should not raise
    _ctl._validate_jev_execution(pc, result, evidence_root=None)
