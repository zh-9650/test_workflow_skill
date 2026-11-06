import importlib.util
import json
from pathlib import Path

import pytest


FINAL_REVIEW = Path(__file__).resolve().parents[1] / "final_review.py"
spec = importlib.util.spec_from_file_location("final_review_receipt_timestamps_test", FINAL_REVIEW)
final_review = importlib.util.module_from_spec(spec)
spec.loader.exec_module(final_review)


TASK = {"task_id": "T-001", "task_hash": "H-001"}


def _receipt(tmp_path, started_at, finished_at, accepted_at=None):
    """Build a completed receipt bound to one output file, as the validator expects."""
    output = tmp_path / "results.json"
    output.write_text(json.dumps({"ok": True}), encoding="utf-8")
    receipt = {
        "agent_role": "execution_worker",
        "receipt_status": "completed",
        "task_id": TASK["task_id"],
        "task_hash": TASK["task_hash"],
        "agent_session_id": "session-1",
        "dispatch_source": "claude_task_tool",
        "host_dispatch_ref": "ref-1",
        "started_at": started_at,
        "finished_at": finished_at,
        "result_status": {"overall": "PASS", "cases": {}},
        "outputs": {"results.json": final_review._sha256(output)},
    }
    if accepted_at is not None:
        receipt["accepted_at"] = accepted_at
    return receipt


def _validate(tmp_path, receipt):
    return final_review._validate_dispatch_receipt(
        tmp_path, receipt, "execution_worker", TASK,
        {"overall": "PASS", "cases": {}}, "batch[B01].worker_dispatch_receipt")


def test_orchestrator_stamps_before_completion_are_accepted(tmp_path):
    receipt = _receipt(
        tmp_path,
        "2026-11-05T05:33:29.678800+00:00",
        "2026-11-05T05:45:50.810866+00:00",
        "2026-11-05T05:33:36.722347+00:00",
    )

    assert _validate(tmp_path, receipt) == "session-1"


def test_finished_before_started_is_rejected(tmp_path):
    receipt = _receipt(
        tmp_path,
        "2026-11-05T06:40:00+00:00",
        "2026-11-05T05:45:50.810866+00:00",
        "2026-11-05T05:33:36.722347+00:00",
    )

    with pytest.raises(AssertionError, match="finished_at precedes started_at"):
        _validate(tmp_path, receipt)


def test_accepted_after_finished_is_rejected(tmp_path):
    receipt = _receipt(
        tmp_path,
        "2026-11-05T05:33:29.678800+00:00",
        "2026-11-05T05:45:50.810866+00:00",
        "2026-11-05T05:50:00+00:00",
    )

    with pytest.raises(AssertionError, match="accepted_at must not follow finished_at"):
        _validate(tmp_path, receipt)


def test_started_long_after_the_accepted_dispatch_is_rejected(tmp_path):
    """A started_at written as the local wall clock while the orchestrator stamped real UTC."""
    receipt = _receipt(
        tmp_path,
        "2026-11-05T13:33:29.678800+00:00",
        "2026-11-05T13:45:50.810866+00:00",
        "2026-11-05T05:33:36.722347+00:00",
    )

    with pytest.raises(AssertionError, match="started_at must not follow the orchestrator-accepted dispatch time"):
        _validate(tmp_path, receipt)


def test_receipt_without_accepted_at_still_checks_start_and_finish_order(tmp_path):
    receipt = _receipt(
        tmp_path,
        "2026-11-05T05:33:29.678800+00:00",
        "2026-11-05T05:45:50.810866+00:00",
    )

    assert _validate(tmp_path, receipt) == "session-1"

    receipt["started_at"] = "2026-11-05T05:50:00+00:00"
    with pytest.raises(AssertionError, match="finished_at precedes started_at"):
        _validate(tmp_path, receipt)


def test_invalid_timestamp_is_rejected(tmp_path):
    receipt = _receipt(tmp_path, "not-a-timestamp", "2026-11-05T05:45:50+00:00")

    with pytest.raises(AssertionError, match="valid dispatch timestamps required"):
        _validate(tmp_path, receipt)
