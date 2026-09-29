import json
import importlib.util
from pathlib import Path
import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
WORKFLOW = REPO_ROOT / "clarify-before-testing" / "scripts" / "workflow_state.py"


def load_workflow():
    spec = importlib.util.spec_from_file_location("workflow_state_closed_loop_test", WORKFLOW)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_record_waiting_state(tmp_path):
    workflow_state = load_workflow()
    run_dir = tmp_path / "work" / "test-runs" / "RUN-TEST-001"
    run_dir.mkdir(parents=True)
    state = workflow_state.init(run_dir, "RUN-TEST-001")
    state_file = run_dir / "internal/state/run-status.json"

    # Valid waiting state
    updated = workflow_state.record_waiting_state(
        state_file,
        "waiting_for_worker_slot",
        reason="Host subagent concurrency limit reached"
    )
    assert updated["next_action"]["type"] == "waiting_for_worker_slot"
    assert updated["next_action"]["reason"] == "Host subagent concurrency limit reached"

    # Another valid waiting state
    updated2 = workflow_state.record_waiting_state(
        state_file,
        "waiting_for_fix_deployment",
        reason="Bug #101 fixed on git, awaiting staging deployment"
    )
    assert updated2["next_action"]["type"] == "waiting_for_fix_deployment"

    # Invalid waiting state rejected
    with pytest.raises(AssertionError, match="unsupported waiting type"):
        workflow_state.record_waiting_state(state_file, "invalid_waiting_state")


def test_create_stage_snapshot(tmp_path):
    workflow_state = load_workflow()
    run_dir = tmp_path / "work" / "test-runs" / "RUN-SNAPSHOT-001"
    run_dir.mkdir(parents=True)
    state = workflow_state.init(run_dir, "RUN-SNAPSHOT-001")
    state_file = run_dir / "internal/state/run-status.json"

    # Add mock execution plan
    plan_path = run_dir / "internal/execution/execution-plan.json"
    plan_path.parent.mkdir(parents=True, exist_ok=True)
    plan_path.write_text(json.dumps({
        "schema_version": 2,
        "cases": [
            {"case_id": "TC-001", "batch_id": "B01", "primary_execution": "API"},
            {"case_id": "TC-002", "batch_id": "B01", "primary_execution": "UI"}
        ]
    }), encoding="utf-8")

    # Add mock ledger with reviewer-confirmed cases
    ledger_path = run_dir / "internal/execution/results/case-results-ledger.json"
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    ledger_path.write_text(json.dumps({
        "cases": {
            "TC-001": {"status": "PASS", "final_result": "PASS", "reviewer_confirmed": True},
            "TC-002": {"status": "BLOCKED", "final_result": "BLOCKED", "reviewer_confirmed": True, "blocked_reason": "Waiting on prerequisite data"}
        }
    }), encoding="utf-8")

    snapshot = workflow_state.create_stage_snapshot(state_file)
    assert snapshot["run_id"] == "RUN-SNAPSHOT-001"
    assert snapshot["is_final_review"] is False
    assert snapshot["cases_summary"]["TC-001"] == "PASS"
    assert snapshot["cases_summary"]["TC-002"] == "BLOCKED"

    # Check state file updated
    s = json.loads(state_file.read_text(encoding="utf-8"))
    assert len(s.get("stage_snapshots", [])) == 1
    assert s.get("final_review_status") is None  # Snapshot MUST NOT pass final review

    # Negative test 1: Fails when case is unreviewed
    ledger_path.write_text(json.dumps({
        "cases": {
            "TC-001": {"status": "PASS", "final_result": "PASS", "reviewer_confirmed": False},
            "TC-002": {"status": "BLOCKED", "final_result": "BLOCKED", "reviewer_confirmed": True, "blocked_reason": "Waiting"}
        }
    }), encoding="utf-8")
    with pytest.raises(AssertionError, match="unreviewed_case"):
        workflow_state.create_stage_snapshot(state_file)

    # Negative test 2: Fails when output escapes deliverables
    ledger_path.write_text(json.dumps({
        "cases": {
            "TC-001": {"status": "PASS", "final_result": "PASS", "reviewer_confirmed": True},
            "TC-002": {"status": "BLOCKED", "final_result": "BLOCKED", "reviewer_confirmed": True, "blocked_reason": "Waiting"}
        }
    }), encoding="utf-8")
    with pytest.raises(AssertionError, match="output_path"):
        workflow_state.create_stage_snapshot(state_file, output_path=str(tmp_path / "escaped.json"))
