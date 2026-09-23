from __future__ import annotations

from copy import deepcopy

import pytest

from conftest import load_script


def _confirmed_cases() -> dict:
    return {
        "cases": [
            {
                "case_id": "TC-API-001",
                "title": "read API resource",
                "steps": ["call the resource endpoint"],
                "expected_results": [
                    {"id": "E1", "expected": "resource is returned"}
                ],
                "target_action": "call resource endpoint",
                "test_point_ids": ["TP-001"],
                "preconditions": [],
                "test_data": {},
            }
        ]
    }


def _plan(schema_version=2) -> dict:
    confirmed = _confirmed_cases()["cases"][0]
    case = deepcopy(confirmed)
    case.update(
        {
            "batch_id": "B01",
            "primary_execution": "API",
            "supporting_observations": [],
            "dependencies": [],
            "data_required": False,
            "evidence_plan": {
                "screenshots": [],
                "recording": False,
                "api": ["redacted request and response"],
                "network": [],
                "files": [],
            },
        }
    )
    value = {
        "schema_version": schema_version,
        "confirmed_case_ids": ["TC-API-001"],
        "confirmed_cases_sha256": "confirmed-sha",
        "batches": [
            {"id": "B01", "parallel_safe": True, "case_ids": ["TC-API-001"]}
        ],
        "cases": [case],
        "self_review": {
            "status": "passed",
            "checks": {
                "all_cases_assigned": True,
                "execution_method_checked": True,
                "batch_logic_checked": True,
                "dependency_checked": True,
                "evidence_checked": True,
                "data_strategy_checked": True,
            },
        },
        "user_confirmation": {"status": "confirmed"},
    }
    if schema_version is None:
        value.pop("schema_version")
    return value


@pytest.mark.parametrize("legacy_version", [None, 1, 3, "2", 2.0])
def test_execution_plan_rejects_legacy_or_unknown_schema(legacy_version) -> None:
    contract = load_script(
        "test-execution-planning/scripts/execution_plan.py",
        f"phase0_execution_plan_{legacy_version}",
    )

    with pytest.raises(AssertionError, match="schema_version"):
        contract.validate(
            _plan(legacy_version),
            confirmed_cases=_confirmed_cases(),
            confirmed_cases_sha256="confirmed-sha",
        )


def test_execution_plan_accepts_v2_schema_at_version_gate() -> None:
    contract = load_script(
        "test-execution-planning/scripts/execution_plan.py",
        "phase0_execution_plan_v2",
    )

    result = contract.validate(
        _plan(2),
        confirmed_cases=_confirmed_cases(),
        confirmed_cases_sha256="confirmed-sha",
    )

    assert result["ok"] is True
