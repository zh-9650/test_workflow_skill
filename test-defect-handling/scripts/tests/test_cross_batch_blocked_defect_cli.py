"""End-to-end tests for cross-Batch defect association using real Runtime receipts.

The fixture under fixtures/phase5-runtime-run was captured from the isolated
Phase 5 synthetic Run-002. The test copies it before changing the Router's
execution-plan binding, so every test invocation is isolated from the fixture.
"""

import json
import hashlib
import importlib.util
import os
import shutil
import subprocess
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[2]
FIXTURE = SCRIPT_DIR / "fixtures" / "phase5-runtime-run"
DEFECT_CLI = REPO_ROOT / "test-defect-handling" / "scripts" / "defect_contract.py"
LEDGER_REL = Path("internal/execution/results/case-results-ledger.json")
RUN_STATUS_REL = Path("internal/state/run-status.json")
PLAN_REL = Path("internal/execution/execution-plan.json")

SOURCE_CASE = "TC-API-CREATE-VALID"
BLOCKED_CASE = "TC-API-CREATE-RECOVER"


def _read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _defect_input():
    return {
        "defect_id": "DEFECT-CLI-CROSS-BATCH-001",
        "source_cases": [SOURCE_CASE],
        "source_batch": "B01",
        "blocked_case_ids": [BLOCKED_CASE],
        "reviewer_confirmed": True,
        "duplicate_check": {"performed": True, "result": "new", "scope": "isolated CLI integration fixture"},
        "root_cause_group": "synthetic-valid-create-injected-500",
        "payload": {
            "title": "Synthetic fixture create failure",
            "project": "isolated synthetic fixture",
            "module": "in-memory catalog API",
            "developer": "synthetic fixture owner",
            "severity": "P2 - synthetic workflow test only",
            "environment": "isolated local fixture; no real business system",
            "preconditions": ["Only synthetic Run artifacts are used."],
            "steps": ["Run the planned B01 API Case."],
            "actual": "The planned create request returned the injected HTTP 500.",
            "expected": "The valid item is created with HTTP 201.",
            "reproduction_rate": "1/1 in the isolated fixture",
            "evidence_refs": [
                "evidence/B01/TC-API-CREATE-VALID/api/create-request-response.json",
                "evidence/B01/TC-API-CREATE-VALID/runner/vitest-report.json",
            ],
        },
        "self_review": {"status": "passed", "findings": ["Synthetic evidence only."]},
        "submission": {"status": "submitted", "bug_ref": "SYNTH-BUG-CLI-001", "destination": "test ledger only"},
    }


def _isolated_run(tmp_path):
    run_dir = tmp_path / "run"
    shutil.copytree(FIXTURE, run_dir)
    # Build fresh synthetic v3 contracts; archived receipts remain untouched.
    sys.path.insert(0,str(SCRIPT_DIR))
    from synthetic_v3_fixture import build
    build(run_dir)

    # The frozen plan itself stays byte-for-byte intact; only move the host-local
    # confirmation binding to the temporary copy, as required by the contract.
    status_path = run_dir / RUN_STATUS_REL
    status = _read_json(status_path)
    plan_path = run_dir / PLAN_REL
    plan_binding = status["confirmation_bindings"]["execution-plan"]
    plan_binding["contract_path"] = str(plan_path.resolve())
    _write_json(status_path, status)

    defect_path = tmp_path / "defect.json"
    _write_json(defect_path, _defect_input())
    return run_dir, defect_path


def _invoke_cli(run_dir, defect_path):
    return subprocess.run(
        [sys.executable, str(DEFECT_CLI), "--input", str(defect_path), "--type", "bug", "--apply-run-dir", str(run_dir)],
        cwd=REPO_ROOT,
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=False,
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )


def test_cli_links_reviewer_confirmed_fail_to_cross_batch_reviewer_confirmed_blocked(tmp_path):
    run_dir, defect_path = _isolated_run(tmp_path)
    ledger_path = run_dir / LEDGER_REL
    before = _read_json(ledger_path)
    source = before["cases"][SOURCE_CASE]
    blocked = before["cases"][BLOCKED_CASE]
    assert source["reviewer_confirmed"] is True and source["final_result"] == "FAIL"
    assert blocked["reviewer_confirmed"] is True and blocked["final_result"] == "BLOCKED"
    assert blocked["runtime_result"]["blocked_reason_type"] == "upstream_case"
    assert source["runtime_result"]["task_id"] != blocked["runtime_result"]["task_id"]

    completed = _invoke_cli(run_dir, defect_path)

    assert completed.returncode == 0, completed.stdout + completed.stderr
    result = json.loads(completed.stdout)
    assert result["ok"] is True
    assert result["updated_case_ids"] == [SOURCE_CASE]
    after = _read_json(ledger_path)
    assert after["cases"][SOURCE_CASE]["bug_ref"] == "SYNTH-BUG-CLI-001"
    assert after["cases"][BLOCKED_CASE]["final_result"] == "BLOCKED"
    assert after["cases"][BLOCKED_CASE]["runtime_result"] == blocked["runtime_result"]


def test_cli_rejects_tampered_blocked_runtime_result_without_mutating_ledger(tmp_path):
    run_dir, defect_path = _isolated_run(tmp_path)
    ledger_path = run_dir / LEDGER_REL
    ledger = _read_json(ledger_path)
    ledger["cases"][BLOCKED_CASE]["runtime_result"]["affected_by"] = []
    _write_json(ledger_path, ledger)
    before = ledger_path.read_bytes()

    completed = _invoke_cli(run_dir, defect_path)

    assert completed.returncode != 0, completed.stdout
    assert "blocked_case_ids" in completed.stderr
    assert ledger_path.read_bytes() == before


def test_cli_rejects_source_case_not_in_confirmed_source_batch_without_mutating_ledger(tmp_path):
    run_dir, defect_path = _isolated_run(tmp_path)
    plan_path = run_dir / PLAN_REL
    plan = _read_json(plan_path)
    plan_case = next(case for case in plan["cases"] if case["case_id"] == SOURCE_CASE)
    plan_case["batch_id"] = "B03"
    _write_json(plan_path, plan)
    status_path = run_dir / RUN_STATUS_REL
    status = _read_json(status_path)
    status["confirmation_bindings"]["execution-plan"]["contract_sha256"] = hashlib.sha256(plan_path.read_bytes()).hexdigest()
    _write_json(status_path, status)

    ledger_path = run_dir / LEDGER_REL
    before = ledger_path.read_bytes()
    completed = _invoke_cli(run_dir, defect_path)

    assert completed.returncode != 0
    assert "source Case must belong to source_batch" in completed.stderr
    assert ledger_path.read_bytes() == before


def test_frozen_worker_task_case_must_equal_confirmed_plan_case():
    contract_path = REPO_ROOT / "test-defect-handling" / "scripts" / "defect_contract.py"
    spec = importlib.util.spec_from_file_location("defect_contract_under_test", contract_path)
    contract = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(contract)
    planned = {"TC-1": {"case_id": "TC-1", "expected_results": [{"id": "A-1", "expected": "201"}]}}
    altered_task = {
        "batch_id": "B01",
        "case_order": ["TC-1"],
        "cases": [{"case_id": "TC-1", "expected_results": [{"id": "A-1", "expected": "200"}]}],
    }

    try:
        contract._assert_task_matches_plan(altered_task, "B01", ["TC-1"], planned, "task")
    except AssertionError as exc:
        assert "must exactly match the confirmed Execution Plan Case" in str(exc)
    else:
        raise AssertionError("modified Task Expected must not pass plan equality validation")
