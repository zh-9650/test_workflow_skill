import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest


FINAL_REVIEW = Path(__file__).resolve().parents[1] / "final_review.py"
spec = importlib.util.spec_from_file_location("final_review_pending_resume_gate_test", FINAL_REVIEW)
final_review = importlib.util.module_from_spec(spec)
spec.loader.exec_module(final_review)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_final_review_rejects_nonempty_pending_resume_in_isolated_run(tmp_path):
    run = tmp_path / "isolated-run"
    plan_path = run / "internal" / "execution" / "execution-plan.json"
    ledger_path = run / "internal" / "execution" / "results" / "case-results-ledger.json"
    state_path = run / "internal" / "state" / "run-status.json"

    _write_json(plan_path, {"cases": [], "batches": []})
    _write_json(ledger_path, {"cases": {}})
    _write_json(state_path, {"pending_resume": {"batch_id": "B03", "case_ids": ["TC-001"]}})

    with pytest.raises(AssertionError, match=r"run_status\.pending_resume: a regression-unblocked Batch resume is still active"):
        final_review.validate(
            {
                "run_dir": str(run),
                "execution_plan_ref": str(plan_path),
                "case_result_ledger_ref": str(ledger_path),
            }
        )


@pytest.mark.parametrize(
    ("state_key", "state_value", "expected_error"),
    [
        (
            "pending_resume",
            {"batch_id": "B03", "case_ids": ["TC-001"]},
            "run_status.pending_resume: a regression-unblocked Batch resume is still active",
        ),
        (
            "pending_resume_batches",
            ["B03"],
            "run_status.pending_resume_batches: Cases unblocked by regression still require data recheck, execution and Reviewer closure",
        ),
    ],
)
def test_final_review_cli_rejects_pending_resume_before_run_closure(
    tmp_path, state_key, state_value, expected_error
):
    run = tmp_path / f"isolated-{state_key}"
    _write_json(run / "internal" / "execution" / "execution-plan.json", {"cases": [], "batches": []})
    _write_json(run / "internal" / "execution" / "results" / "case-results-ledger.json", {"cases": {}})
    _write_json(run / "internal" / "state" / "run-status.json", {state_key: state_value})
    input_path = tmp_path / f"{state_key}-input.json"
    _write_json(input_path, {"run_dir": str(run)})

    result = subprocess.run(
        [sys.executable, str(FINAL_REVIEW), "--input", str(input_path), "--run-dir", str(run)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )

    assert result.returncode != 0
    assert expected_error in result.stderr
