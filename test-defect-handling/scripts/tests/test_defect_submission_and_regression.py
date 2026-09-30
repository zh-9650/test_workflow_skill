import importlib.util
from pathlib import Path
import pytest
import json
import hashlib

_defect_path = Path(__file__).resolve().parents[1] / "defect_contract.py"
_defect_spec = importlib.util.spec_from_file_location("defect_contract", _defect_path)
_defect = importlib.util.module_from_spec(_defect_spec)
_defect_spec.loader.exec_module(_defect)


def _sample_defect_payload(sub_status="submitted", bug_ref="BUG-100"):
    return {
        "defect_id": "DEF-001",
        "source_cases": ["TC-001"],
        "source_batch": "B01",
        "reviewer_confirmed": True,
        "duplicate_check": {
            "performed": True,
            "result": "new"
        },
        "root_cause_group": "auth_token_expiration",
        "payload": {
            "title": "Auth token expires prematurely",
            "project": "PROJ-1",
            "module": "auth",
            "developer": "dev1",
            "severity": "major",
            "environment": "test",
            "preconditions": "Logged in",
            "steps": "Wait 5 minutes",
            "actual": "401 Unauthorized",
            "expected": "Session valid",
            "reproduction_rate": "100%",
            "evidence_refs": ["evidence/B01/TC-001/evidence.json"]
        },
        "self_review": {
            "status": "passed"
        },
        "submission": {
            "status": sub_status,
            "bug_ref": bug_ref
        }
    }


def test_validate_rejects_failed_submission_with_bug_ref():
    payload = _sample_defect_payload(sub_status="failed", bug_ref="BUG-FAKE")
    with pytest.raises(AssertionError, match="failed submission must not declare bug_ref"):
        _defect.validate(payload)


def test_validate_accepts_clean_failed_submission():
    payload = _sample_defect_payload(sub_status="failed", bug_ref=None)
    out = _defect.validate(payload)
    assert out["ok"] is True
    assert out["submission_status"] == "failed"
    assert out["bug_ref"] is None


def test_validate_rejects_submitted_without_bug_ref():
    payload = _sample_defect_payload(sub_status="submitted", bug_ref=None)
    with pytest.raises(AssertionError, match="required after submitted"):
        _defect.validate(payload)


def test_apply_defect_to_ledger_refuses_failed_submission(tmp_path):
    run_dir = tmp_path / "run"
    run_dir.mkdir(parents=True)
    payload = _sample_defect_payload(sub_status="failed", bug_ref=None)
    with pytest.raises(AssertionError, match="cannot apply defect"):
        _defect.apply_defect_to_ledger(run_dir, payload)


def test_validate_reg_rejects_mismatched_target_environment(tmp_path):
    baseline = {
        "target_environment": {"env_id": "staging"},
        "cases": [
            {"case_id": "TC-001", "primary_execution": "API"}
        ]
    }
    v = _complete_pending_regression(tmp_path)
    v["target_environment"] = "production"
    with pytest.raises(AssertionError, match="does not match planned env"):
        _defect.validate_reg(v, baseline, evidence_root=tmp_path)


def test_validate_reg_rejects_empty_deployment_version(tmp_path):
    baseline = {
        "target_environment": {"env_id": "staging"},
        "cases": [
            {"case_id": "TC-001", "primary_execution": "API"}
        ]
    }
    v = _complete_pending_regression(tmp_path)
    v["deployment_version"] = "  "
    with pytest.raises(AssertionError, match="non-empty deployment_version required"):
        _defect.validate_reg(v, baseline, evidence_root=tmp_path)


def test_validate_reg_rejects_invalid_impact_analysis(tmp_path):
    baseline = {
        "target_environment": {"env_id": "staging"},
        "cases": [
            {"case_id": "TC-001", "primary_execution": "API"}
        ]
    }
    v = _complete_pending_regression(tmp_path)
    v["impact_analysis"] = "not_an_object"
    with pytest.raises(AssertionError, match="impact_analysis must be an object"):
        _defect.validate_reg(v, baseline, evidence_root=tmp_path)


def _write_deployment_event(run_dir, impact=None):
    impact = impact or {
        "old_pass_retest_needed": False,
        "affected_pass_cases": [],
        "data_recheck_needed": True,
        "rationale": "Authentication fixtures changed with the fix",
    }
    rel = Path("internal/execution/deployments/deploy-001.json")
    path = run_dir / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    event = {
        "event_id": "deploy-001",
        "target_env": "staging",
        "deployment_version": "v1.0.1",
        "verified_at": "2026-09-29T00:00:00+00:00",
        "impact_decision": impact,
    }
    path.write_text(json.dumps(event), encoding="utf-8")
    return rel.as_posix(), hashlib.sha256(path.read_bytes()).hexdigest(), impact


def _complete_pending_regression(run_dir):
    event_ref, event_sha, impact = _write_deployment_event(run_dir)
    return {
        "regression_id": "REG-001",
        "bug_ref": "BUG-100",
        "original_case_ids": ["TC-001"],
        "impact_case_ids": [],
        "cases": [{"case_id": "TC-001", "primary_execution": "API"}],
        "status": "pending",
        "target_environment": "staging",
        "deployment_version": "v1.0.1",
        "deployment_event_ref": event_ref,
        "deployment_event_sha256": event_sha,
        "impact_analysis": impact,
    }


@pytest.mark.parametrize(
    "missing",
    [
        "target_environment",
        "deployment_version",
        "deployment_event_ref",
        "deployment_event_sha256",
        "impact_analysis",
    ],
)
def test_validate_reg_requires_verified_deployment_binding(tmp_path, missing):
    baseline = {
        "target_environment": {"env_id": "staging"},
        "cases": [{"case_id": "TC-001", "primary_execution": "API"}],
    }
    regression = _complete_pending_regression(tmp_path)
    regression.pop(missing)
    with pytest.raises(AssertionError, match=missing):
        _defect.validate_reg(regression, baseline, evidence_root=tmp_path)


def test_validate_reg_accepts_verified_deployment_binding(tmp_path):
    baseline = {
        "target_environment": {"env_id": "staging"},
        "cases": [{"case_id": "TC-001", "primary_execution": "API"}],
    }
    regression = _complete_pending_regression(tmp_path)
    out = _defect.validate_reg(regression, baseline, evidence_root=tmp_path)
    assert out["ok"] is True
