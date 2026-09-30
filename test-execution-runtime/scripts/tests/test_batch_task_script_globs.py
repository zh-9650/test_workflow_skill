import importlib.util
import sys
from pathlib import Path

import pytest


RUNTIME_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RUNTIME_DIR))
SPEC = importlib.util.spec_from_file_location("batch_task_builder_under_test", RUNTIME_DIR / "batch_task_builder.py")
batch_task_builder = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(batch_task_builder)


def _plan(script_target):
    case_id = "TC-API-001"
    return {
        "target_environment": {"env_id": "local-test", "initial_deployment_version": "fixture-v1"},
        "batches": [{"id": "B01", "case_ids": [case_id]}],
        "cases": [
            {
                "case_id": case_id,
                "batch_id": "B01",
                "primary_execution": "API",
                "automation": {
                    "required": True,
                    "language": "typescript",
                    "runner": "vitest",
                    "driver": "node-native-fetch",
                    "script_strategy": "create_or_update",
                    "script_target": script_target,
                },
            }
        ],
    }


@pytest.mark.parametrize(
    "script_target",
    [
        "scripts/api/B01/TC-API-001[1].test.ts",
        "scripts/api/B01/TC-API-001?.test.ts",
    ],
)
def test_task_builder_rejects_glob_metacharacters_in_case_script_target(script_target):
    with pytest.raises(AssertionError, match="glob-safe"):
        batch_task_builder.build(_plan(script_target), "B01", "execution.json", "manifest.json")
