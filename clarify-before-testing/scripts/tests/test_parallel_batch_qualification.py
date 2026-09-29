import hashlib
import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
WORKFLOW = ROOT / "clarify-before-testing" / "scripts" / "workflow_state.py"


def load_workflow():
    spec = importlib.util.spec_from_file_location("workflow_state_parallel_test", WORKFLOW)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_router_requires_two_independently_bound_parallel_safe_batches(tmp_path, monkeypatch):
    workflow = load_workflow()
    run_dir = tmp_path / "work" / "test-runs" / "RUN-PARALLEL"
    state_path = run_dir / "internal" / "state" / "run-status.json"
    plan_path = run_dir / "internal" / "execution" / "execution-plan.json"
    manifest_dir = run_dir / "internal" / "data" / "manifests"
    manifest_dir.mkdir(parents=True)
    plan_path.parent.mkdir(parents=True)
    plan = {
        "batches": [
            {"id": "B01", "parallel_safe": True, "case_ids": ["C01"]},
            {"id": "B02", "parallel_safe": True, "case_ids": ["C02"]},
            {"id": "B03", "parallel_safe": False, "case_ids": ["C03"]},
        ],
        "cases": [
            {"case_id": "C01", "batch_id": "B01", "dependencies": [], "data_required": False},
            {"case_id": "C02", "batch_id": "B02", "dependencies": [], "data_required": False},
            {"case_id": "C03", "batch_id": "B03", "dependencies": ["C01"], "data_required": False},
        ],
    }
    plan_path.write_text(json.dumps(plan), encoding="utf-8")
    state = {
        "current_stage": "data-readiness",
        "confirmation_bindings": {
            "execution-plan": {
                "contract_path": str(plan_path),
                "contract_sha256": hashlib.sha256(plan_path.read_bytes()).hexdigest(),
            }
        },
    }
    state_path.parent.mkdir(parents=True)
    state_path.write_text(json.dumps(state), encoding="utf-8")

    manifests = {}
    for batch_id in ("B01", "B02"):
        manifest_path = manifest_dir / f"{batch_id}.json"
        manifest_path.write_text(
            json.dumps({"batch_id": batch_id, "data_required": False,
                        "reason": f"{batch_id} has no pre-execution data requirement",
                        "objects": [], "builders": []}),
            encoding="utf-8",
        )
        manifests[batch_id] = manifest_path

    first = workflow.set_batch_data_ready(state_path, "B01", manifests["B01"])
    assert first["parallel_batch_ids"] == []
    assert first["next_action"] == {"type": "execute_batch", "batch_id": "B01"}

    second = workflow.set_batch_data_ready(state_path, "B02", manifests["B02"])
    assert second["batch_data_status"] == {"B01": "ready", "B02": "ready"}
    assert second["batch_data_bindings"]["B01"]["manifest_path"] != second["batch_data_bindings"]["B02"]["manifest_path"]
    assert second["parallel_batch_ids"] == ["B01", "B02"]
    assert second["current_batch"] is None
    assert second["current_batch_data_ready"] is False
    assert second["next_action"] == {"type": "execute_parallel_batches", "batch_ids": ["B01", "B02"]}


def test_router_does_not_add_unsafe_or_cross_batch_dependent_batch(tmp_path, monkeypatch):
    workflow = load_workflow()
    run_dir = tmp_path / "work" / "test-runs" / "RUN-PARALLEL-GATE"
    state_path = run_dir / "internal" / "state" / "run-status.json"
    plan_path = run_dir / "internal" / "execution" / "execution-plan.json"
    manifest_dir = run_dir / "internal" / "data" / "manifests"
    manifest_dir.mkdir(parents=True)
    plan_path.parent.mkdir(parents=True)
    plan = {
        "batches": [
            {"id": "B01", "parallel_safe": True, "case_ids": ["C01"]},
            {"id": "B02", "parallel_safe": True, "case_ids": ["C02"]},
            {"id": "B03", "parallel_safe": False, "case_ids": ["C03"]},
        ],
        "cases": [
            {"case_id": "C01", "batch_id": "B01", "dependencies": [], "data_required": False},
            {"case_id": "C02", "batch_id": "B02", "dependencies": ["C01"], "data_required": False},
            {"case_id": "C03", "batch_id": "B03", "dependencies": [], "data_required": False},
        ],
    }
    plan_path.write_text(json.dumps(plan), encoding="utf-8")
    state_path.parent.mkdir(parents=True)
    state_path.write_text(json.dumps({
        "current_stage": "data-readiness",
        "confirmation_bindings": {"execution-plan": {
            "contract_path": str(plan_path),
            "contract_sha256": hashlib.sha256(plan_path.read_bytes()).hexdigest(),
        }},
    }), encoding="utf-8")

    results = []
    for batch_id in ("B01", "B02", "B03"):
        manifest_path = manifest_dir / f"{batch_id}.json"
        manifest_path.write_text(json.dumps({
            "batch_id": batch_id, "data_required": False,
            "reason": f"{batch_id} has no pre-execution data requirement",
            "objects": [], "builders": [],
        }), encoding="utf-8")
        results.append(workflow.set_batch_data_ready(state_path, batch_id, manifest_path))

    assert results[-1]["parallel_batch_ids"] == []
    assert results[-1]["next_action"] == {"type": "execute_batch", "batch_id": "B03"}
