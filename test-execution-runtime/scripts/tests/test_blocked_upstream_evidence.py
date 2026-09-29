"""Public-contract tests for upstream-dependent BLOCKED API Cases."""

import hashlib
import importlib.util
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest


CONTRACT_PATH = Path(__file__).resolve().parents[1] / "execution_control.py"
SPEC = importlib.util.spec_from_file_location("execution_control", CONTRACT_PATH)
execution_control = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(execution_control)
RUNTIME_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RUNTIME_DIR))
RUNTIME_SPEC = importlib.util.spec_from_file_location("runtime_orchestrator_under_test", RUNTIME_DIR / "runtime_orchestrator.py")
runtime_orchestrator = importlib.util.module_from_spec(RUNTIME_SPEC)
assert RUNTIME_SPEC.loader is not None
RUNTIME_SPEC.loader.exec_module(runtime_orchestrator)


CASE_ID = "TC-API-CREATE-RECOVER"
BATCH_ID = "B03"
SCRIPT_REF = f"scripts/api/{BATCH_ID}/{CASE_ID}.test.ts"
GATE_REF = f"evidence/{BATCH_ID}/{CASE_ID}/blocked-dependency.json"
REPORT_REF = f"evidence/{BATCH_ID}/{CASE_ID}/vitest-report.json"


def _write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def _blocked_fixture(tmp_path: Path):
    run_root = tmp_path / "run"
    case_root = run_root / "evidence" / BATCH_ID / CASE_ID
    case_root.mkdir(parents=True)
    script_path = run_root / SCRIPT_REF
    script_path.parent.mkdir(parents=True)
    script_path.write_text("it('blocks while upstream is unresolved', () => expect(true).toBe(true));\n", encoding="utf-8")

    now = datetime.now(timezone.utc)
    start_ms = int(now.timestamp() * 1000)
    started = now - timedelta(seconds=1)
    finished = now + timedelta(seconds=1)
    _write_json(
        run_root / REPORT_REF,
        {
            "startTime": start_ms,
            "testResults": [
                {
                    "name": f"C:/fixture/{SCRIPT_REF}",
                    "assertionResults": [{"status": "passed"}],
                }
            ],
        },
    )
    gate = {
        "evidence_type": "blocked_dependency",
        "case_id": CASE_ID,
        "blocked_reason_type": "upstream_case",
        "dependency_results": [
            {
                "case_id": "TC-API-CREATE-VALID",
                "status": "FAIL",
                "reviewer_confirmed": True,
            }
        ],
        "affected_by": "TC-API-CREATE-VALID",
        "target_action_executed": False,
        "request_made": False,
    }
    _write_json(run_root / GATE_REF, gate)

    plan = {
        "case_id": CASE_ID,
        "batch_id": BATCH_ID,
        "primary_execution": "API",
        "dependencies": ["TC-API-CREATE-VALID"],
        "expected_results": [{"id": "EXP-1", "expected": "依赖未通过时不发起目标请求"}],
        "automation": {
            "required": True,
            "runner": "vitest",
            "driver": "node-native-fetch",
            "script_target": SCRIPT_REF,
        },
        "evidence_plan": {
            "api": [{"kind": "request_response", "expected_ids": ["EXP-1"]}],
            "files": [{"kind": "runner_report", "expected_ids": ["EXP-1"]}],
        },
    }
    result = {
        "schema_version": execution_control.EXECUTION_SCHEMA_VERSION,
        "case_id": CASE_ID,
        "status": "BLOCKED",
        "actual_execution": "NOT_EXECUTED",
        "target_action_executed": False,
        "blocked_reason_type": "upstream_case",
        "blocked_reason": "上游创建 Case 经 Reviewer 确认 FAIL，恢复前不得执行读取。",
        "affected_by": "TC-API-CREATE-VALID",
        "expected_results": [
            {
                "id": "EXP-1",
                "actual": "依赖门禁确认上游仍为 Reviewer-confirmed FAIL，未发目标 API 请求。",
                "result": "blocked",
                "evidence_refs": [GATE_REF, REPORT_REF],
            }
        ],
        "automation_run": {
            "script_ref": SCRIPT_REF,
            "script_sha256": hashlib.sha256(script_path.read_bytes()).hexdigest(),
            "runner": "vitest",
            "driver": "node-native-fetch",
            "static_check": "passed",
            "debug_attempts": [],
            "official_run": {
                "run_id": "actual-run-from-test-fixture",
                "exit_code": 0,
                "script_sha256": hashlib.sha256(script_path.read_bytes()).hexdigest(),
                "started_at": started.isoformat(),
                "finished_at": finished.isoformat(),
                "report_ref": REPORT_REF,
            },
        },
    }
    dependency_context = {
        "TC-API-CREATE-VALID": {
            "case_id": "TC-API-CREATE-VALID",
            "batch_id": "B01",
            "status": "FAIL",
            "final_result": "FAIL",
            "reviewer_confirmed": True,
        }
    }
    return plan, result, run_root, gate, dependency_context


def test_blocked_upstream_uses_gate_evidence_not_request_response(tmp_path):
    plan, result, run_root, gate, dependency_context = _blocked_fixture(tmp_path)

    assert "request_response" in {
        item.get("kind") for item in plan["evidence_plan"].get("api", [])
    }
    assert gate["request_made"] is False
    assert execution_control.validate(
        plan, result, run_root, dependency_context=dependency_context
    ) == {
        "ok": True,
        "case_id": CASE_ID,
        "status": "BLOCKED",
    }


@pytest.mark.parametrize(
    "mutation",
    ["missing_gate_ref", "missing_gate_file", "dependency_passed", "review_not_confirmed", "affected_by_mismatch", "nested_request_payload", "request_payload_in_other_evidence", "request_payload_in_result_refs", "request_payload_in_file_refs"],
)
def test_blocked_upstream_rejects_incomplete_or_inconsistent_gate(tmp_path, mutation):
    plan, result, run_root, gate, dependency_context = _blocked_fixture(tmp_path)
    if mutation == "missing_gate_ref":
        result["expected_results"][0]["evidence_refs"].remove(GATE_REF)
    elif mutation == "missing_gate_file":
        (run_root / GATE_REF).unlink()
    elif mutation == "dependency_passed":
        gate["dependency_results"][0]["status"] = "PASS"
        _write_json(run_root / GATE_REF, gate)
    elif mutation == "review_not_confirmed":
        gate["dependency_results"][0]["reviewer_confirmed"] = False
        _write_json(run_root / GATE_REF, gate)
    elif mutation == "affected_by_mismatch":
        gate["affected_by"] = "TC-UNRELATED"
        _write_json(run_root / GATE_REF, gate)
    elif mutation == "nested_request_payload":
        gate["metadata"] = {"request": {"url": "http://fixture.invalid"}}
        _write_json(run_root / GATE_REF, gate)
    elif mutation == "request_payload_in_other_evidence":
        other_ref = f"evidence/{BATCH_ID}/{CASE_ID}/unexpected-response.json"
        _write_json(run_root / other_ref, {"request": {"url": "http://fixture.invalid"}, "response": {"status": 500}})
        result["expected_results"][0]["evidence_refs"].append(other_ref)
    elif mutation in {"request_payload_in_result_refs", "request_payload_in_file_refs"}:
        other_ref = f"evidence/{BATCH_ID}/{CASE_ID}/{mutation}.json"
        _write_json(run_root / other_ref, {"response": {"status": 500}})
        result["evidence_refs" if mutation == "request_payload_in_result_refs" else "file_evidence_refs"] = [other_ref]

    with pytest.raises(AssertionError):
        execution_control.validate(
            plan, result, run_root, dependency_context=dependency_context
        )


def test_blocked_upstream_rejects_missing_trusted_dependency_context(tmp_path):
    plan, result, run_root, _, _ = _blocked_fixture(tmp_path)

    with pytest.raises((AssertionError, TypeError)):
        execution_control.validate(plan, result, run_root, dependency_context={})


def test_blocked_upstream_rejects_context_that_disagrees_with_gate_evidence(tmp_path):
    plan, result, run_root, _, dependency_context = _blocked_fixture(tmp_path)
    dependency_context["TC-API-CREATE-VALID"]["status"] = "PASS"
    dependency_context["TC-API-CREATE-VALID"]["final_result"] = "PASS"

    with pytest.raises(AssertionError):
        execution_control.validate(
            plan, result, run_root, dependency_context=dependency_context
        )


def test_reviewer_snapshot_rejects_dependency_context_different_from_worker_task(tmp_path):
    snapshot_path = tmp_path / "internal" / "snapshot.json"
    _write_json(snapshot_path, {"frozen": True})
    snapshot_hash = hashlib.sha256(snapshot_path.read_bytes()).hexdigest()
    manifest = {
        "source.json": {
            "snapshot_ref": "internal/snapshot.json",
            "sha256": snapshot_hash,
        }
    }
    worker_context = {
        "TC-API-CREATE-VALID": {
            "case_id": "TC-API-CREATE-VALID",
            "batch_id": "B01",
            "status": "FAIL",
            "final_result": "FAIL",
            "reviewer_confirmed": True,
        }
    }
    reviewer_task = {
        "artifact_snapshot_manifest": manifest,
        "artifact_snapshot_sha256": runtime_orchestrator._canonical_sha256(manifest),
        "artifact_sha256": {"source.json": snapshot_hash},
        "dependency_context": {},
        "batch_id": "B03",
    }

    with pytest.raises(AssertionError, match="frozen Runtime Worker Task"):
        runtime_orchestrator._validate_frozen_artifacts(
            tmp_path, reviewer_task, {"dependency_context": worker_context}, []
        )


def test_normal_api_product_fail_still_requires_redacted_request_response(tmp_path):
    plan, result, run_root, _, dependency_context = _blocked_fixture(tmp_path)
    script_path = run_root / SCRIPT_REF
    script_path.write_text("it('reports API failure', () => expect(false).toBe(true));\n", encoding="utf-8")
    script_hash = hashlib.sha256(script_path.read_bytes()).hexdigest()
    report = {
        "startTime": int(datetime.now(timezone.utc).timestamp() * 1000),
        "testResults": [
            {
                "name": f"C:/fixture/{SCRIPT_REF}",
                "assertionResults": [{"status": "failed"}],
            }
        ],
    }
    _write_json(run_root / REPORT_REF, report)
    api_ref = f"evidence/{BATCH_ID}/{CASE_ID}/response.json"
    _write_json(run_root / api_ref, {"request": {"method": "POST"}, "response": {"status": 500}})

    plan["evidence_plan"]["api"] = [{"kind": "request_response", "expected_ids": ["EXP-1"]}]
    plan["evidence_plan"]["files"] = [{"kind": "runner_report", "expected_ids": ["EXP-1"]}]
    result.update(
        {
            "status": "FAIL",
            "actual_execution": "API",
            "target_action_executed": True,
            "reason_type": "product_issue",
            "expected": "创建接口返回 201",
            "actual": "创建接口返回 500",
            "reproduced": True,
        }
    )
    result.pop("blocked_reason_type")
    result.pop("blocked_reason")
    result.pop("affected_by")
    result["expected_results"][0].update(
        {
            "actual": "POST /api/items 返回 500。",
            "result": "fail",
            "evidence_refs": [api_ref, REPORT_REF],
        }
    )
    result["evidence_refs"] = [api_ref]
    result["automation_run"].update(
        {
            "script_sha256": script_hash,
            "official_run": {
                **result["automation_run"]["official_run"],
                "script_sha256": script_hash,
            },
        }
    )

    with pytest.raises(AssertionError, match="redacted=true"):
        execution_control.validate(
            plan, result, run_root, dependency_context=dependency_context
        )
