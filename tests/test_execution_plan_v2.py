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
            "automation": {
                "required": True,
                "language": "typescript",
                "runner": "vitest",
                "driver": "node-native-fetch",
                "script_target": "scripts/api/B01/TC-API-001.test.ts",
                "script_strategy": "create_or_update",
            },
            "supporting_observations": [],
            "dependencies": [],
            "data_required": False,
            "evidence_plan": {
                "level": "standard",
                "screenshots": [],
                "recording": False,
                "api": [{"kind": "request_response", "expected_ids": ["E1"], "redacted": True}],
                "network": [],
                "files": [],
                "read_back_required": False,
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


def _validate(plan):
    contract = load_script(
        "test-execution-planning/scripts/execution_plan.py",
        "phase2_execution_plan_behavior",
    )
    return contract.validate(
        plan,
        confirmed_cases=_confirmed_cases(),
        confirmed_cases_sha256="confirmed-sha",
    )


def test_api_plan_requires_native_fetch_vitest_and_expected_bound_evidence() -> None:
    plan = _plan()
    _validate(plan)
    plan["cases"][0]["automation"]["driver"] = "playwright-api-request-context"
    with pytest.raises(AssertionError, match="driver"):
        _validate(plan)
    plan = _plan()
    plan["cases"][0]["automation"]["required"] = 1
    with pytest.raises(AssertionError, match="boolean"):
        _validate(plan)


def test_automated_case_requires_run_local_unique_script_target() -> None:
    plan = _plan()
    plan["cases"][0]["automation"].pop("script_target")
    with pytest.raises(AssertionError, match="script_target"):
        _validate(plan)
    plan = _plan()
    plan["cases"][0]["automation"]["script_target"] = "scripts/api/B02/TC-API-001.test.ts"
    with pytest.raises(AssertionError, match="script_target"):
        _validate(plan)


def test_api_evidence_must_be_redacted_and_read_back_decision_explicit() -> None:
    plan = _plan()
    plan["cases"][0]["evidence_plan"]["api"][0]["redacted"] = False
    with pytest.raises(AssertionError, match="redacted"):
        _validate(plan)
    plan = _plan()
    plan["cases"][0]["evidence_plan"]["read_back_required"] = True
    with pytest.raises(AssertionError, match="read_back"):
        _validate(plan)


def test_old_batch_recording_and_waiver_contract_are_rejected() -> None:
    plan = _plan()
    plan["cases"][0]["evidence_plan"]["recording"] = {"required": True, "scope": "batch"}
    with pytest.raises(AssertionError, match="recording"):
        _validate(plan)
    plan = _plan()
    plan["cases"][0]["evidence_plan"]["waiver_reason"] = "skip"
    with pytest.raises(AssertionError, match="waiver"):
        _validate(plan)


def _ui_plan(level="standard", recording=False, screenshots=None):
    confirmed = _confirmed_cases()
    source = confirmed["cases"][0]
    source["case_id"] = "TC-UI-001"
    source["title"] = "submit through the page"
    source["steps"] = ["fill and submit the page"]
    source["target_action"] = "submit the page"
    case = deepcopy(source)
    case.update({
        "batch_id": "B01",
        "primary_execution": "UI",
        "automation": {
            "required": True,
            "language": "typescript",
            "runner": "playwright-test",
            "driver": "playwright-page",
            "script_target": "scripts/ui/B01/TC-UI-001.spec.ts",
            "script_strategy": "create_or_update",
        },
        "supporting_observations": [],
        "dependencies": [],
        "data_required": False,
        "evidence_plan": {
            "level": level,
            "screenshots": screenshots if screenshots is not None else [{"kind": "screenshot", "expected_ids": ["E1"]}],
            "recording": recording,
            "api": [], "network": [], "files": [],
        },
    })
    plan = _plan()
    plan["confirmed_case_ids"] = ["TC-UI-001"]
    plan["cases"] = [case]
    plan["batches"][0]["case_ids"] = ["TC-UI-001"]
    return plan, confirmed


def test_critical_ui_requires_recording_and_expected_bound_screenshot() -> None:
    contract = load_script(
        "test-execution-planning/scripts/execution_plan.py",
        "phase2_critical_ui_evidence",
    )
    plan, confirmed = _ui_plan(level="critical")
    with pytest.raises(AssertionError, match="recording"):
        contract.validate(plan, confirmed_cases=confirmed)
    plan, confirmed = _ui_plan(level="critical", recording=True, screenshots=[])
    with pytest.raises(AssertionError, match="screenshots"):
        contract.validate(plan, confirmed_cases=confirmed)
    plan, confirmed = _ui_plan(level="critical", recording=True)
    assert contract.validate(plan, confirmed_cases=confirmed)["ok"] is True
    plan, confirmed = _ui_plan(level="standard", screenshots=[])
    with pytest.raises(AssertionError, match="screenshots"):
        contract.validate(plan, confirmed_cases=confirmed)


def test_manual_case_requires_explicit_human_steps_and_result_entry() -> None:
    contract = load_script(
        "test-execution-planning/scripts/execution_plan.py",
        "phase2_manual_case_contract",
    )
    plan = _plan()
    case = plan["cases"][0]
    case["primary_execution"] = "人工"
    case["automation"] = {"required": False}
    case["manual_execution"] = {
        "reason": "external approval is required",
        "steps": ["request approval", "record the decision"],
        "result_entry": "enter Actual and evidence in the Run result ledger",
    }
    assert contract.validate(plan, confirmed_cases=_confirmed_cases())["ok"] is True
    case["manual_execution"].pop("result_entry")
    with pytest.raises(AssertionError, match="result_entry"):
        contract.validate(plan, confirmed_cases=_confirmed_cases())
