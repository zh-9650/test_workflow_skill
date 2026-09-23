from __future__ import annotations

from conftest import load_script


def test_execution_contract_v2_is_separate_from_run_state_schema() -> None:
    versions = load_script(
        "clarify-before-testing/scripts/workflow_versions.py",
        "phase0_workflow_versions",
    )

    assert versions.EXECUTION_SCHEMA_VERSION == 2
    assert versions.WORKFLOW_VERSION == "2.0.0"
    assert versions.RUN_STATE_SCHEMA_VERSION == 3


def test_new_run_records_workflow_version_without_downgrading_state_schema(
    tmp_path,
) -> None:
    workflow_state = load_script(
        "clarify-before-testing/scripts/workflow_state.py",
        "phase0_workflow_state",
    )

    state = workflow_state.init(tmp_path / "RUN-PHASE0", "RUN-PHASE0")

    assert state["schema_version"] == 3
    assert state["workflow_version"] == "2.0.0"
