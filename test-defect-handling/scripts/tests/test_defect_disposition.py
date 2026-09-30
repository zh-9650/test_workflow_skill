import json
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
DASHBOARD_REL = Path("dashboard/dashboard-data.json")

SOURCE_CASE = "TC-API-CREATE-VALID"
BLOCKED_CASE = "TC-API-CREATE-RECOVER"


def _read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _isolated_run(tmp_path):
    run_dir = tmp_path / "run"
    shutil.copytree(FIXTURE, run_dir)
    status_path = run_dir / RUN_STATUS_REL
    status = _read_json(status_path)
    plan_path = run_dir / PLAN_REL
    plan_binding = status["confirmation_bindings"]["execution-plan"]
    plan_binding["contract_path"] = str(plan_path.resolve())
    _write_json(status_path, status)
    ledger = _read_json(run_dir / LEDGER_REL)
    ledger['cases'][SOURCE_CASE]['defect_id'] = 'DEFECT-CLI-001'
    ledger['cases'][SOURCE_CASE]['bug_ref'] = 'BUG-001'
    _write_json(run_dir / LEDGER_REL, ledger)
    return run_dir


def test_defect_disposition_succeeds_and_updates_ledger_and_dashboard(tmp_path):
    run_dir = _isolated_run(tmp_path)
    ledger_path = run_dir / LEDGER_REL
    status_path = run_dir / RUN_STATUS_REL

    # Ensure status is defect-handling so dashboard event passes stage check
    status = _read_json(status_path)
    status["current_stage"] = "defect-handling"
    status["open_defects"] = ["DEFECT-CLI-001"]
    _write_json(status_path, status)

    disp_payload = {
        "defect_id": "DEFECT-CLI-001",
        "bug_ref": "BUG-001",
        "decision_source": "user-message:explicit-postponement-001",
        "disposition": "postponed",
        "operator": "quality-auditor",
        "rationale": "Spec agreed to postpone fix to next release",
        "affected_case_ids": [SOURCE_CASE],
        "target_version": "v3.1"
    }
    disp_path = tmp_path / "disp.json"
    _write_json(disp_path, disp_payload)

    proc = subprocess.run(
        [sys.executable, str(DEFECT_CLI), "--input", str(disp_path), "--type", "disposition", "--apply-run-dir", str(run_dir)],
        cwd=REPO_ROOT,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )
    assert proc.returncode == 0, f"stdout: {proc.stdout}, stderr: {proc.stderr}"
    
    # 1. Verify ledger: FAIL fact is preserved, disposition record is added
    ledger = _read_json(ledger_path)
    case_row = ledger["cases"][SOURCE_CASE]
    assert case_row["status"] == "FAIL"
    assert case_row["final_result"] == "FAIL"
    assert case_row["disposition"] == "postponed"
    assert case_row["disposition_record"]["operator"] == "quality-auditor"

    # 2. Verify run status: open defect is removed
    updated_status = _read_json(status_path)
    assert "DEFECT-CLI-001" not in updated_status.get("open_defects", [])
    assert updated_status.get("defect_dispositions") is not None
    assert updated_status.get("next_action", {}).get("type") in {"result_review", "handle_defects"}


def test_defect_disposition_fails_cleanly_on_invalid_disposition_without_ledger_mutation(tmp_path):
    run_dir = _isolated_run(tmp_path)
    ledger_path = run_dir / LEDGER_REL
    ledger_before = _read_json(ledger_path)

    disp_payload = {
        "defect_id": "DEFECT-CLI-001",
        "bug_ref": "BUG-001",
        "decision_source": "user-message:explicit-postponement-001",
        "disposition": "invalid_disp",
        "operator": "quality-auditor",
        "rationale": "Invalid",
        "affected_case_ids": [SOURCE_CASE]
    }
    disp_path = tmp_path / "disp_invalid.json"
    _write_json(disp_path, disp_payload)

    proc = subprocess.run(
        [sys.executable, str(DEFECT_CLI), "--input", str(disp_path), "--type", "disposition", "--apply-run-dir", str(run_dir)],
        cwd=REPO_ROOT,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )
    assert proc.returncode != 0
    ledger_after = _read_json(ledger_path)
    assert ledger_before == ledger_after
