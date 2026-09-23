from __future__ import annotations

import pytest

from conftest import load_script


def _reviewer_result(schema_version=2) -> dict:
    value = {
        "schema_version": schema_version,
        "status": "passed",
        "findings": [],
        "checked_case_ids": ["TC-001"],
        "retest_case_ids": [],
        "return_stage": None,
        "checks": {
            "completeness_checked": True,
            "method_consistency_checked": True,
            "judgement_checked": True,
            "evidence_checked": True,
            "abnormal_classification_checked": True,
        },
    }
    if schema_version is None:
        value.pop("schema_version")
    return value


@pytest.mark.parametrize("legacy_version", [None, 1, 3, "2", 2.0])
def test_reviewer_result_rejects_legacy_or_non_integer_schema(legacy_version) -> None:
    contract = load_script(
        "test-execution-runtime/scripts/reviewer_contract.py",
        f"phase0_reviewer_contract_{legacy_version}",
    )

    with pytest.raises(AssertionError, match="reviewer.schema_version"):
        contract.validate(_reviewer_result(legacy_version), ["TC-001"])


def test_reviewer_result_accepts_v2_schema_at_version_gate() -> None:
    contract = load_script(
        "test-execution-runtime/scripts/reviewer_contract.py",
        "phase0_reviewer_contract_v2",
    )

    result = contract.validate(_reviewer_result(2), ["TC-001"])

    assert result == {"ok": True, "status": "passed"}


def _case_contract_payload(tmp_path, schema_version=2) -> tuple[dict, dict]:
    evidence_ref = "evidence/B01/TC-001/expected.json"
    evidence_path = tmp_path / evidence_ref
    evidence_path.parent.mkdir(parents=True)
    evidence_path.write_text('{"observed": true}', encoding="utf-8")

    plan_case = {
        "case_id": "TC-001",
        "batch_id": "B01",
        "primary_execution": "API",
        "expected_results": [{"id": "E1", "expected": "resource is returned"}],
        "evidence_plan": {},
    }
    case_result = {
        "schema_version": schema_version,
        "case_id": "TC-001",
        "status": "PASS",
        "actual_execution": "API",
        "expected_results": [
            {
                "id": "E1",
                "actual": "resource returned",
                "result": "pass",
                "evidence_refs": [evidence_ref],
            }
        ],
    }
    if schema_version is None:
        case_result.pop("schema_version")
    return plan_case, case_result


@pytest.mark.parametrize("legacy_version", [None, 1, 3, "2", 2.0])
def test_case_result_rejects_legacy_or_non_integer_schema(
    tmp_path, legacy_version
) -> None:
    contract = load_script(
        "test-execution-runtime/scripts/execution_control.py",
        f"phase0_execution_control_{legacy_version}",
    )
    plan_case, case_result = _case_contract_payload(tmp_path, legacy_version)

    with pytest.raises(AssertionError, match="TC-001.schema_version"):
        contract.validate(plan_case, case_result, tmp_path)


def test_case_result_accepts_v2_schema_at_version_gate(tmp_path) -> None:
    contract = load_script(
        "test-execution-runtime/scripts/execution_control.py",
        "phase0_execution_control_v2",
    )
    plan_case, case_result = _case_contract_payload(tmp_path, 2)

    result = contract.validate(plan_case, case_result, tmp_path)

    assert result == {"ok": True, "case_id": "TC-001", "status": "PASS"}
