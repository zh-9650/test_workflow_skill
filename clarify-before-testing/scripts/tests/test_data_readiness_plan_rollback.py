import json
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
CLI = ROOT / "clarify-before-testing" / "scripts" / "workflow_state.py"


def make_state(tmp_path):
    run_dir = tmp_path / "work" / "test-runs" / "RUN-ROLLBACK"
    state_path = run_dir / "internal" / "state" / "run-status.json"
    state_path.parent.mkdir(parents=True)
    state = {
        "schema_version": "test",
        "workflow_version": "test",
        "run_id": "RUN-ROLLBACK",
        "current_stage": "data-readiness",
        "return_reason": "stale prior return reason",
        "current_batch": "B02",
        "current_case": "TC-02",
        "current_worker": "stale-worker",
        "current_reviewer": "stale-reviewer",
        "current_action": {"type": "prepare_batch_data", "batch_id": "B02"},
        "next_action": {"type": "execute_batch", "batch_id": "B02"},
        "current_batch_data_ready": True,
        "batch_data_status": {"B01": "ready", "B02": "ready", "B03": "preparing"},
        "batch_data_bindings": {
            "B01": {"manifest_path": "old-B01.json"},
            "B02": {"manifest_path": "old-B02.json"},
        },
        "pending_resume": {"batch_id": "B02", "case_ids": ["TC-02"], "bug_ref": "BUG-1"},
        "parallel_batch_ids": ["B01", "B02"],
    }
    state_path.write_text(json.dumps(state), encoding="utf-8")
    return state_path, state


def transition(state_path, *args):
    return subprocess.run(
        [sys.executable, str(CLI), "transition", "--state", str(state_path), *args],
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )


def test_data_readiness_can_return_to_plan_only_with_reason_and_clears_all_data_state(tmp_path):
    state_path, _ = make_state(tmp_path)

    missing_reason = transition(
        state_path, "--stage", "execution-planning", "--next", "revise_execution_plan"
    )
    assert missing_reason.returncode != 0
    assert "return_reason" in missing_reason.stderr
    # Rejected transition must leave Router state untouched.
    unchanged = json.loads(state_path.read_text(encoding="utf-8"))
    assert unchanged["current_stage"] == "data-readiness"
    assert unchanged["batch_data_bindings"]

    whitespace_reason = transition(
        state_path,
        "--stage",
        "execution-planning",
        "--next",
        "revise_execution_plan",
        "--return-reason",
        "   ",
    )
    assert whitespace_reason.returncode != 0
    assert "return_reason" in whitespace_reason.stderr
    unchanged = json.loads(state_path.read_text(encoding="utf-8"))
    assert unchanged["current_stage"] == "data-readiness"
    assert unchanged["return_reason"] == "stale prior return reason"

    accepted = transition(
        state_path,
        "--stage",
        "execution-planning",
        "--next",
        "revise_execution_plan",
        "--return-reason",
        "  Batch data assumptions need to be reflected in the plan  ",
    )
    assert accepted.returncode == 0, accepted.stderr
    result = json.loads(state_path.read_text(encoding="utf-8"))
    assert result["current_stage"] == "execution-planning"
    assert result["next_action"] == {"type": "revise_execution_plan"}
    assert result["last_event"]["from"] == "data-readiness"
    assert result["last_event"]["to"] == "execution-planning"
    assert result["transition_history"] == [result["last_event"]]
    assert result["return_reason"] == "Batch data assumptions need to be reflected in the plan"
    assert result["current_batch"] is None
    assert result["current_case"] is None
    assert result["current_worker"] is None
    assert result["current_reviewer"] is None
    assert result["batch_data_bindings"] == {}
    assert result["batch_data_status"] == {}
    assert result["current_batch_data_ready"] is False
    assert result["pending_resume"] is None
    assert result["parallel_batch_ids"] == []


def test_data_readiness_plan_rollback_requires_reason_even_when_no_data_is_bound(tmp_path):
    state_path, state = make_state(tmp_path)
    state["batch_data_bindings"] = {}
    state["batch_data_status"] = {}
    state["current_batch_data_ready"] = False
    state["pending_resume"] = None
    state_path.write_text(json.dumps(state), encoding="utf-8")

    rejected = transition(
        state_path, "--stage", "execution-planning", "--next", "revise_execution_plan"
    )
    assert rejected.returncode != 0
    assert "return_reason" in rejected.stderr
    unchanged = json.loads(state_path.read_text(encoding="utf-8"))
    assert unchanged["current_stage"] == "data-readiness"
    assert unchanged["batch_data_status"] == {}


def test_successful_transition_clears_previous_return_reason(tmp_path):
    state_path, state = make_state(tmp_path)
    state["current_stage"] = "defect-handling"
    state["return_reason"] = "old upstream return reason"
    prior_transition = {
        "type": "stage_transition",
        "from": "execution-runtime",
        "to": "defect-handling",
        "at": "2026-09-25T00:00:00+00:00",
    }
    state["transition_history"] = [prior_transition]
    state_path.write_text(json.dumps(state), encoding="utf-8")

    result = transition(state_path, "--stage", "result-review", "--next", "review_run")
    assert result.returncode == 0, result.stderr
    updated = json.loads(state_path.read_text(encoding="utf-8"))
    assert updated["current_stage"] == "result-review"
    assert "return_reason" not in updated
    assert updated["transition_history"][0] == prior_transition
    assert len(updated["transition_history"]) == 2
    event = updated["transition_history"][1]
    assert event["from"] == "defect-handling"
    assert event["to"] == "result-review"
    assert event["next_action"] == {"type": "review_run"}
    assert updated["last_event"] == event


def test_transition_rejects_malformed_history_without_mutating_state(tmp_path):
    state_path, state = make_state(tmp_path)
    state["current_stage"] = "defect-handling"
    state["transition_history"] = None
    state_path.write_text(json.dumps(state), encoding="utf-8")

    rejected = transition(state_path, "--stage", "result-review", "--next", "review_run")

    assert rejected.returncode != 0
    assert "transition_history" in rejected.stderr
    unchanged = json.loads(state_path.read_text(encoding="utf-8"))
    assert unchanged["current_stage"] == "defect-handling"
    assert unchanged["transition_history"] is None
