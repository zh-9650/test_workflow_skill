import importlib.util
from pathlib import Path
import pytest

FINAL_REVIEW = Path(__file__).resolve().parents[1] / "final_review.py"
spec = importlib.util.spec_from_file_location("final_review_test", FINAL_REVIEW)
final_review = importlib.util.module_from_spec(spec)
spec.loader.exec_module(final_review)


def test_derive_assessment_all_pass():
    rows = [
        {"case_id": "TC-001", "status": "PASS"},
        {"case_id": "TC-002", "status": "PASS"},
    ]
    plan_by = {
        "TC-001": {"case_id": "TC-001", "core_flow": True},
        "TC-002": {"case_id": "TC-002", "core_flow": False},
    }
    assessment = final_review.derive_assessment(rows, plan_by)
    assert assessment["conclusion"] == "ready"
    assert assessment["coverage_complete"] is True
    assert assessment["core_flow_passed"] is True
    assert assessment["regression_complete"] is True
    assert assessment["unresolved_critical_defects"] == 0


def test_derive_assessment_pass_after_fix():
    rows = [
        {"case_id": "TC-001", "status": "PASS_AFTER_FIX"},
        {"case_id": "TC-002", "status": "PASS"},
    ]
    plan_by = {
        "TC-001": {"case_id": "TC-001", "core_flow": True},
        "TC-002": {"case_id": "TC-002", "core_flow": False},
    }
    assessment = final_review.derive_assessment(rows, plan_by)
    assert assessment["conclusion"] == "ready"
    assert assessment["coverage_complete"] is True
    assert assessment["core_flow_passed"] is True
    assert assessment["regression_complete"] is True


def test_derive_assessment_with_legitimate_blocked():
    rows = [
        {"case_id": "TC-001", "status": "PASS"},
        {"case_id": "TC-002", "status": "BLOCKED"},
    ]
    plan_by = {
        "TC-001": {"case_id": "TC-001"},
        "TC-002": {"case_id": "TC-002"},
    }
    assessment = final_review.derive_assessment(rows, plan_by)
    assert assessment["conclusion"] == "ready_with_risk"
    assert assessment["coverage_complete"] is False
    assert assessment["blocked_scope"] == ["TC-002"]


def test_derive_assessment_with_unresolved_fail():
    rows = [
        {"case_id": "TC-001", "status": "FAIL", "severity": "minor"},
        {"case_id": "TC-002", "status": "PASS"},
    ]
    plan_by = {
        "TC-001": {"case_id": "TC-001"},
        "TC-002": {"case_id": "TC-002"},
    }
    assessment = final_review.derive_assessment(rows, plan_by)
    assert assessment["conclusion"] == "ready_with_risk"
    assert assessment["regression_complete"] is False


def test_derive_assessment_with_critical_defect():
    rows = [
        {"case_id": "TC-001", "status": "FAIL", "severity": "critical"},
        {"case_id": "TC-002", "status": "PASS"},
    ]
    plan_by = {
        "TC-001": {"case_id": "TC-001"},
        "TC-002": {"case_id": "TC-002"},
    }
    assessment = final_review.derive_assessment(rows, plan_by)
    assert assessment["conclusion"] == "not_recommended"
    assert assessment["regression_complete"] is False
    assert assessment["unresolved_critical_defects"] == 1


def test_validate_final_jev_audit_rejects_none_with_invocations():
    pc = {"case_id": "TC-001", "jev_policy": {"mode": "none"}}
    item = {"runtime_result": {"jev_invocations": [{"cost_usd": 0.01}]}}
    with pytest.raises(AssertionError, match="jev mode is none"):
        final_review._validate_final_jev_audit("TC-001", pc, item, {})


def test_validate_final_jev_audit_rejects_required_without_invocations():
    pc = {"case_id": "TC-001", "jev_policy": {"mode": "required"}}
    item = {"runtime_result": {}}
    with pytest.raises(AssertionError, match="required Jev invocation missing"):
        final_review._validate_final_jev_audit("TC-001", pc, item, {})


def test_validate_final_jev_audit_rejects_conditional_without_reason():
    pc = {"case_id": "TC-001", "jev_policy": {"mode": "conditional"}}
    item = {"runtime_result": {}}
    with pytest.raises(AssertionError, match="conditional Jev invocation was skipped"):
        final_review._validate_final_jev_audit("TC-001", pc, item, {})


def test_validate_final_jev_audit_rejects_budget_exceeded():
    pc = {"case_id": "TC-001", "jev_policy": {"mode": "required", "max_cost_usd": 0.02}}
    item = {
        "runtime_result": {
            "jev_invocations": [
                {"cost_usd": 0.015, "confidence": 0.95},
                {"cost_usd": 0.010, "confidence": 0.90},
            ]
        }
    }
    with pytest.raises(AssertionError, match="exceeds planned max_cost_usd"):
        final_review._validate_final_jev_audit("TC-001", pc, item, {})


def test_validate_final_jev_audit_rejects_invalid_confidence():
    pc = {"case_id": "TC-001", "jev_policy": {"mode": "required"}}
    item = {
        "runtime_result": {
            "jev_invocations": [
                {"cost_usd": 0.005, "confidence": 1.5},
            ]
        }
    }
    with pytest.raises(AssertionError, match="confidence must be between 0.0 and 1.0"):
        final_review._validate_final_jev_audit("TC-001", pc, item, {})


def test_validate_final_jev_audit_passes_valid_invocations():
    pc = {"case_id": "TC-001", "jev_policy": {"mode": "required", "max_cost_usd": 0.05}}
    item = {
        "runtime_result": {
            "jev_invocations": [
                {"cost_usd": 0.005, "confidence": 0.98},
            ]
        }
    }
    # Should not raise
    final_review._validate_final_jev_audit("TC-001", pc, item, {})
