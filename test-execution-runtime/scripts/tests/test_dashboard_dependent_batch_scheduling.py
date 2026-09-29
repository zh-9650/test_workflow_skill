import importlib.util
import json
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "dashboard_update.py"
SPEC = importlib.util.spec_from_file_location("dashboard_update_dependency_scheduling", MODULE_PATH)
dashboard_update = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(dashboard_update)


def _state(upstream_status):
    return {
        "batch_order": ["B01", "B02", "B03"],
        "batch_status": {"B01": "completed", "B02": "completed", "B03": "pending"},
        "batch_dependency_cases": {"B01": [], "B02": [], "B03": ["TC-UPSTREAM"]},
        "case_status": {"TC-UPSTREAM": upstream_status},
        "open_defects": ["BUG-SYNTH"],
    }


def test_dependent_batch_is_scheduled_after_reviewer_confirmed_upstream_fail():
    assert dashboard_update._select_runnable_batch(_state("FAIL")) == "B03"


def test_dependent_batch_is_scheduled_after_upstream_blocked_for_runtime_gate():
    assert dashboard_update._select_runnable_batch(_state("BLOCKED")) == "B03"


def test_dependent_batch_waits_while_upstream_is_not_terminal():
    assert dashboard_update._select_runnable_batch(_state("PENDING")) is None
    assert dashboard_update._select_runnable_batch(_state("RUNNING")) is None


def test_passed_upstream_still_schedules_dependent_batch_normally():
    assert dashboard_update._select_runnable_batch(_state("PASS")) == "B03"
    assert dashboard_update._select_runnable_batch(_state("PASS_AFTER_FIX")) == "B03"


def test_refresh_routing_selects_dependent_batch_without_changing_router_stage(tmp_path):
    run = tmp_path / "run"
    state_path = run / "internal" / "state" / "run-status.json"
    dashboard_path = run / "dashboard" / "dashboard-data.json"
    state_path.parent.mkdir(parents=True)
    dashboard_path.parent.mkdir(parents=True)
    state = _state("FAIL") | {
        "current_stage": "execution-runtime",
        "current_worker": None,
        "current_reviewer": None,
        "pending_resume_batches": [],
    }
    state_path.write_text(json.dumps(state), encoding="utf-8")
    dashboard_path.write_text(json.dumps({"batches": [], "cases": []}), encoding="utf-8")

    result = dashboard_update.refresh_next_action(state_path, dashboard_path)

    persisted = json.loads(state_path.read_text(encoding="utf-8"))
    assert result["current_stage"] == "execution-runtime"
    assert result["next_action"] == {"type": "prepare_batch_data", "batch_id": "B03"}
    assert persisted["current_stage"] == "execution-runtime"
    assert persisted["last_event"]["type"] == "routing_reconciled"


def test_refresh_routing_refuses_to_run_while_worker_is_active(tmp_path):
    run = tmp_path / "run"
    state_path = run / "internal" / "state" / "run-status.json"
    dashboard_path = run / "dashboard" / "dashboard-data.json"
    state_path.parent.mkdir(parents=True)
    dashboard_path.parent.mkdir(parents=True)
    state = _state("FAIL") | {"current_stage": "execution-runtime", "current_worker": "worker-1"}
    state_path.write_text(json.dumps(state), encoding="utf-8")
    dashboard_path.write_text(json.dumps({"batches": [], "cases": []}), encoding="utf-8")

    try:
        dashboard_update.refresh_next_action(state_path, dashboard_path)
    except AssertionError as exc:
        assert "while a Worker or Reviewer is active" in str(exc)
    else:
        raise AssertionError("routing refresh must reject active execution")
