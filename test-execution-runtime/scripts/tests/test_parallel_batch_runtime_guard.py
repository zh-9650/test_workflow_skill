import importlib.util
import json
import sys
from pathlib import Path

import pytest


RUNTIME_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RUNTIME_DIR))
SPEC = importlib.util.spec_from_file_location(
    "runtime_orchestrator_parallel_test", RUNTIME_DIR / "runtime_orchestrator.py"
)
runtime = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(runtime)


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def test_runtime_rejects_overlapping_business_object_refs_for_parallel_batches(tmp_path):
    state_dir = tmp_path / "internal" / "execution" / "runtime-state"
    write_json(state_dir / "B01-state.json", {"batch_id": "B01", "status": "running"})
    bound_manifest = tmp_path / "internal" / "data" / "manifests" / "B01.json"
    write_json(bound_manifest, {"batch_id": "B01", "objects": [{"object_ref": "customer-17"}]})
    write_json(tmp_path / "internal" / "state" / "run-status.json", {
        "parallel_batch_ids": ["B01", "B02"],
        "batch_data_bindings": {"B01": {"manifest_path": str(bound_manifest)}},
    })
    plan = {
        "batches": [
            {"id": "B01", "parallel_safe": True},
            {"id": "B02", "parallel_safe": True},
        ],
        "cases": [
            {"case_id": "C01", "batch_id": "B01", "dependencies": []},
            {"case_id": "C02", "batch_id": "B02", "dependencies": []},
        ],
    }

    with pytest.raises(AssertionError, match="reuse business object references"):
        runtime._assert_parallel_batch_eligibility(
            tmp_path,
            plan,
            "B02",
            {"batch_id": "B02", "objects": [{"object_ref": "customer-17"}]},
        )


def test_runtime_accepts_isolated_refs_only_after_router_approval(tmp_path):
    state_dir = tmp_path / "internal" / "execution" / "runtime-state"
    write_json(state_dir / "B01-state.json", {"batch_id": "B01", "status": "running"})
    bound_manifest = tmp_path / "internal" / "data" / "manifests" / "B01.json"
    write_json(bound_manifest, {"batch_id": "B01", "objects": [{"object_ref": "customer-17"}]})
    state_path = tmp_path / "internal" / "state" / "run-status.json"
    write_json(state_path, {
        "parallel_batch_ids": ["B01", "B02"],
        "batch_data_bindings": {"B01": {"manifest_path": str(bound_manifest)}},
    })
    plan = {
        "batches": [
            {"id": "B01", "parallel_safe": True},
            {"id": "B02", "parallel_safe": True},
        ],
        "cases": [
            {"case_id": "C01", "batch_id": "B01", "dependencies": []},
            {"case_id": "C02", "batch_id": "B02", "dependencies": []},
        ],
    }
    isolated = {"batch_id": "B02", "objects": [{"object_ref": "customer-18"}]}
    runtime._assert_parallel_batch_eligibility(tmp_path, plan, "B02", isolated)

    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["parallel_batch_ids"] = ["B01"]
    write_json(state_path, state)
    with pytest.raises(AssertionError, match="Router-approved parallel_batch_ids"):
        runtime._assert_parallel_batch_eligibility(tmp_path, plan, "B02", isolated)
