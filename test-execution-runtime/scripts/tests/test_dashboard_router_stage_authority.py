import importlib.util
import json
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "dashboard_update.py"
SPEC = importlib.util.spec_from_file_location("dashboard_update_stage_authority", MODULE_PATH)
dashboard_update = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(dashboard_update)


def test_runtime_initialization_projects_but_never_changes_router_stage(tmp_path):
    state_path = tmp_path / "internal" / "state" / "run-status.json"
    dashboard_path = tmp_path / "dashboard" / "dashboard-data.json"
    state_path.parent.mkdir(parents=True)
    state_path.write_text(
        json.dumps({"current_stage": "execution-runtime", "run_id": "RUN-STAGE-AUTHORITY"}),
        encoding="utf-8",
    )

    initialized = dashboard_update.initialize_runtime_files(state_path, dashboard_path, {"cases": [], "batches": []})
    assert initialized["run_status"]["current_stage"] == "execution-runtime"
    assert initialized["dashboard"]["current_stage"] == "execution-runtime"
    assert json.loads(state_path.read_text(encoding="utf-8"))["current_stage"] == "execution-runtime"

    dashboard_update.apply_event_files(
        state_path,
        dashboard_path,
        {"type": "run_paused", "stage": "execution-runtime"},
    )
    persisted_state = json.loads(state_path.read_text(encoding="utf-8"))
    persisted_dashboard = json.loads(dashboard_path.read_text(encoding="utf-8"))
    assert persisted_state["current_stage"] == "execution-runtime"
    assert persisted_dashboard["current_stage"] == "execution-runtime"
    assert persisted_state["current_action"] == {"type": "run_paused"}
    assert persisted_dashboard["current_action"] == "run_paused"


def test_runtime_initialization_outside_runtime_refuses_without_changing_either_file(tmp_path):
    state_path = tmp_path / "internal" / "state" / "run-status.json"
    dashboard_path = tmp_path / "dashboard" / "dashboard-data.json"
    state_path.parent.mkdir(parents=True)
    dashboard_path.parent.mkdir(parents=True)
    original_state = {"current_stage": "data-readiness", "current_action": {"type": "prepare_data"}}
    original_dashboard = {"sentinel": "preserve this file"}
    state_path.write_text(json.dumps(original_state), encoding="utf-8")
    dashboard_path.write_text(json.dumps(original_dashboard), encoding="utf-8")

    try:
        dashboard_update.initialize_runtime_files(state_path, dashboard_path, {"cases": [], "batches": []})
    except AssertionError as exc:
        assert "only be initialized during execution-runtime" in str(exc)
    else:
        raise AssertionError("Runtime initialization outside Router Runtime stage should be rejected")

    assert json.loads(state_path.read_text(encoding="utf-8")) == original_state
    assert json.loads(dashboard_path.read_text(encoding="utf-8")) == original_dashboard


def test_dashboard_rejects_event_stage_mismatch_without_changing_router_stage(tmp_path):
    state_path = tmp_path / "internal" / "state" / "run-status.json"
    dashboard_path = tmp_path / "dashboard" / "dashboard-data.json"
    state_path.parent.mkdir(parents=True)
    dashboard_path.parent.mkdir(parents=True)
    state_path.write_text(json.dumps({"current_stage": "data-readiness"}), encoding="utf-8")
    dashboard_path.write_text(json.dumps({"current_stage": "stale", "recent": [], "cases": [], "batches": []}), encoding="utf-8")
    original_dashboard = json.loads(dashboard_path.read_text(encoding="utf-8"))
    original_state = json.loads(state_path.read_text(encoding="utf-8"))

    try:
        dashboard_update.apply_event_files(
            state_path,
            dashboard_path,
            {"type": "run_paused", "stage": "execution-runtime"},
        )
    except AssertionError as exc:
        assert "cannot change Router stage" in str(exc)
    else:
        raise AssertionError("stage-mismatched dashboard event should be rejected")
    assert json.loads(state_path.read_text(encoding="utf-8"))["current_stage"] == "data-readiness"
    assert json.loads(state_path.read_text(encoding="utf-8")) == original_state
    assert json.loads(dashboard_path.read_text(encoding="utf-8")) == original_dashboard
