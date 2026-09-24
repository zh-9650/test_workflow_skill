from __future__ import annotations

import pytest
import hashlib
import json

from conftest import load_script


def _reviewer_result(schema_version=2) -> dict:
    value = {
        "schema_version": schema_version,
        "reviewer_task_id": "B01-review-001",
        "input_task_hash": "a" * 64,
        "input_results_sha256": "b" * 64,
        "agent_session_id": "reviewer-session",
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


def _reviewer_task() -> dict:
    return {
        "task_id": "B01-review-001",
        "task_hash": "a" * 64,
        "worker_session_id": "worker-session",
        "results_sha256": "b" * 64,
        "worker_self_review_sha256": "c" * 64,
        "case_order": ["TC-001"],
    }


@pytest.mark.parametrize("legacy_version", [None, 1, 3, "2", 2.0])
def test_reviewer_result_rejects_legacy_or_non_integer_schema(legacy_version) -> None:
    contract = load_script(
        "test-execution-runtime/scripts/reviewer_contract.py",
        f"phase0_reviewer_contract_{legacy_version}",
    )

    with pytest.raises(AssertionError, match="reviewer.schema_version"):
        contract.validate(
            _reviewer_result(legacy_version), ["TC-001"],
            reviewer_task=_reviewer_task(), worker_session_id="worker-session",
            reviewer_session_id="reviewer-session", results_sha256="b" * 64,
        )


def test_reviewer_result_accepts_v2_schema_at_version_gate() -> None:
    contract = load_script(
        "test-execution-runtime/scripts/reviewer_contract.py",
        "phase0_reviewer_contract_v2",
    )

    result = contract.validate(
        _reviewer_result(2), ["TC-001"], reviewer_task=_reviewer_task(),
        worker_session_id="worker-session", reviewer_session_id="reviewer-session",
        results_sha256="b" * 64,
    )

    assert result == {"ok": True, "status": "passed"}


def _case_contract_payload(tmp_path, schema_version=2) -> tuple[dict, dict]:
    evidence_ref = "evidence/B01/TC-001/expected.json"
    evidence_path = tmp_path / evidence_ref
    evidence_path.parent.mkdir(parents=True)
    evidence_path.write_text('{"observed": true}', encoding="utf-8")
    script_ref = "scripts/api/B01/TC-001.test.ts"
    script_path = tmp_path / script_ref
    script_path.parent.mkdir(parents=True, exist_ok=True)
    script_path.write_text("test('TC-001', () => {});\n", encoding="utf-8")
    script_hash = hashlib.sha256(script_path.read_bytes()).hexdigest()
    report_ref = "evidence/B01/TC-001/runner/report.json"
    report_path = tmp_path / report_ref
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps({
        "startTime": 1790146200000,
        "testResults": [{
            "name": f"C:/run/{script_ref}",
            "assertionResults": [{"status": "passed"}],
        }],
    }), encoding="utf-8")

    plan_case = {
        "case_id": "TC-001",
        "batch_id": "B01",
        "primary_execution": "API",
        "automation": {
            "required": True,
            "language": "typescript",
            "runner": "vitest",
            "driver": "node-native-fetch",
            "script_target": script_ref,
            "script_strategy": "create_or_update",
        },
        "expected_results": [{"id": "E1", "expected": "resource is returned"}],
        "evidence_plan": {"level":"standard","screenshots":[],"recording":False,"api":[],"network":[],"files":[],"read_back_required":False},
    }
    case_result = {
        "schema_version": schema_version,
        "case_id": "TC-001",
        "status": "PASS",
        "actual_execution": "API",
        "automation_run": {
            "script_ref": script_ref,
            "script_sha256": script_hash,
            "runner": "vitest",
            "driver": "node-native-fetch",
            "static_check": "passed",
            "debug_attempts": [],
            "official_run": {
                "run_id": "RUN-001",
                "started_at": "2026-09-23T06:49:59+00:00",
                "finished_at": "2026-09-23T06:51:00+00:00",
                "exit_code": 0,
                "report_ref": report_ref,
                "script_sha256": script_hash,
            },
        },
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


def test_required_runner_report_must_be_the_official_report_for_each_expected(tmp_path) -> None:
    contract = load_script(
        "test-execution-runtime/scripts/execution_control.py",
        "runner_report_expected_binding",
    )
    plan_case, case_result = _case_contract_payload(tmp_path)
    report_ref = case_result["automation_run"]["official_run"]["report_ref"]
    plan_case["evidence_plan"]["files"] = [
        {"kind": "runner_report", "expected_ids": ["E1"]}
    ]

    with pytest.raises(AssertionError, match="must attach the official Runner report"):
        contract.validate(plan_case, case_result, tmp_path)

    case_result["expected_results"][0]["evidence_refs"].append(report_ref)
    assert contract.validate(plan_case, case_result, tmp_path) == {
        "ok": True,
        "case_id": "TC-001",
        "status": "PASS",
    }


def test_request_response_redaction_does_not_apply_to_unmodified_official_runner_report(tmp_path) -> None:
    contract = load_script(
        "test-execution-runtime/scripts/execution_control.py",
        "request_response_runner_report_separation",
    )
    plan_case, case_result = _case_contract_payload(tmp_path)
    api_ref = "evidence/B01/TC-001/api/request-response.json"
    api_path = tmp_path / api_ref
    api_path.parent.mkdir(parents=True)
    api_path.write_text(json.dumps({"redacted": True, "request": {"method": "GET"}, "response": {"status": 200}}), encoding="utf-8")
    report_ref = case_result["automation_run"]["official_run"]["report_ref"]
    plan_case["evidence_plan"]["api"] = [
        {"kind": "request_response", "expected_ids": ["E1"], "redacted": True}
    ]
    plan_case["evidence_plan"]["files"] = [
        {"kind": "runner_report", "expected_ids": ["E1"]}
    ]
    case_result["expected_results"][0]["evidence_refs"] = [api_ref, report_ref]

    assert contract.validate(plan_case, case_result, tmp_path) == {
        "ok": True,
        "case_id": "TC-001",
        "status": "PASS",
    }

    case_result["expected_results"][0]["evidence_refs"] = [report_ref]
    with pytest.raises(AssertionError, match="needs JSON request_response evidence separate from the official Runner report"):
        contract.validate(plan_case, case_result, tmp_path)


def test_planned_screenshot_is_required_for_every_mapped_expected(tmp_path) -> None:
    contract = load_script(
        "test-execution-runtime/scripts/execution_control.py",
        "screenshot_expected_binding",
    )
    plan_case, case_result = _case_contract_payload(tmp_path)
    second_evidence_ref = "evidence/B01/TC-001/second-expected.json"
    second_evidence_path = tmp_path / second_evidence_ref
    second_evidence_path.write_text('{"observed": true}', encoding="utf-8")
    screenshot_ref = "evidence/B01/TC-001/checkpoint.png"
    (tmp_path / screenshot_ref).write_bytes(b"image-evidence")
    plan_case["expected_results"].append(
        {"id": "E2", "expected": "the second result is observed"}
    )
    plan_case["evidence_plan"]["screenshots"] = [
        {"kind": "screenshot", "expected_ids": ["E1", "E2"]}
    ]
    case_result["expected_results"].append(
        {
            "id": "E2",
            "actual": "the second result is observed",
            "result": "pass",
            "evidence_refs": [second_evidence_ref],
        }
    )

    with pytest.raises(AssertionError, match="screenshot for Expected E1"):
        contract.validate(plan_case, case_result, tmp_path)

    case_result["expected_results"][0]["evidence_refs"].append(screenshot_ref)
    with pytest.raises(AssertionError, match="screenshot for Expected E2"):
        contract.validate(plan_case, case_result, tmp_path)

    case_result["expected_results"][1]["evidence_refs"].append(screenshot_ref)
    assert contract.validate(plan_case, case_result, tmp_path) == {
        "ok": True,
        "case_id": "TC-001",
        "status": "PASS",
    }
