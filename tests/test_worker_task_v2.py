from __future__ import annotations

from copy import deepcopy

import pytest

from conftest import load_script


def _plan() -> dict:
    return {
        "schema_version": 2,
        "batches": [
            {
                "id": "B01",
                "goal": "execute the API smoke case",
                "parallel_safe": True,
                "case_ids": ["TC-API-001"],
            }
        ],
        "cases": [
            {
                "case_id": "TC-API-001",
                "batch_id": "B01",
                "title": "read API resource",
                "steps": ["call the resource endpoint"],
                "expected_results": [
                    {"id": "E1", "expected": "resource is returned"}
                ],
                "primary_execution": "API",
                "automation": {
                    "required": True,
                    "language": "typescript",
                    "runner": "vitest",
                "driver": "node-native-fetch",
                "script_target": "scripts/api/B01/TC-API-001.test.ts",
                "script_strategy": "create_or_update",
                },
                "dependencies": [],
                "evidence_plan": {
                    "screenshots": [],
                    "recording": False,
                    "api": ["redacted request and response"],
                    "network": [],
                    "files": [],
                },
            }
        ],
    }


def _builder():
    return load_script(
        "test-execution-runtime/scripts/batch_task_builder.py",
        "phase0_batch_task_builder",
    )


def test_build_emits_v2_worker_task_versions() -> None:
    builder = _builder()

    task = builder.build(
        _plan(),
        "B01",
        "internal/execution/execution-context.json",
        "internal/data/B01-data-manifest.json",
    )

    assert task["schema_version"] == 2
    assert task["workflow_version"] == "2.0.0"
    assert builder.validate(task)["ok"] is True


def test_public_validator_rejects_legacy_worker_task() -> None:
    builder = _builder()
    current = builder.build(
        _plan(),
        "B01",
        "internal/execution/execution-context.json",
        "internal/data/B01-data-manifest.json",
    )
    legacy = deepcopy(current)
    legacy.pop("schema_version", None)
    legacy.pop("workflow_version", None)

    with pytest.raises(AssertionError, match="schema_version"):
        builder.validate(legacy)


def test_public_validator_rejects_wrong_workflow_version() -> None:
    builder = _builder()
    task = builder.build(
        _plan(),
        "B01",
        "internal/execution/execution-context.json",
        "internal/data/B01-data-manifest.json",
    )
    task["workflow_version"] = "legacy"

    with pytest.raises(AssertionError, match="workflow_version"):
        builder.validate(task)


@pytest.mark.parametrize("invalid_schema", ["2", 2.0, True])
def test_public_validator_rejects_non_integer_schema(invalid_schema) -> None:
    builder = _builder()
    task = builder.build(
        _plan(),
        "B01",
        "internal/execution/execution-context.json",
        "internal/data/B01-data-manifest.json",
    )
    task["schema_version"] = invalid_schema

    with pytest.raises(AssertionError, match="schema_version"):
        builder.validate(task)


def test_version_label_alone_does_not_make_a_worker_task_valid() -> None:
    builder = _builder()

    with pytest.raises(AssertionError, match="task_id|batch_id|case_order|cases"):
        builder.validate({"schema_version": 2, "workflow_version": "2.0.0"})
