from __future__ import annotations

import hashlib
import json

import pytest

from conftest import load_script


def _write_json(path, value) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    path.write_text(content, encoding="utf-8")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_final_review_rejects_stale_closed_run_without_current_case_confirmation(
    tmp_path,
) -> None:
    run = tmp_path / "stale-closed-run"
    plan = run / "internal/execution/execution-plan.json"
    ledger = run / "internal/execution/results/case-results-ledger.json"
    state = run / "internal/state/run-status.json"
    plan_hash = _write_json(plan, {})
    _write_json(ledger, {"cases": {}})
    _write_json(
        state,
        {
            "current_stage": "closed",
            "final_review_status": "passed",
            "confirmation_bindings": {
                "execution-plan": {
                    "contract_path": str(plan),
                    "contract_sha256": plan_hash,
                },
                "test-cases": {
                    "contract_path": str(plan),
                    "contract_sha256": plan_hash,
                },
            },
            "confirmations": {
                "test_cases_confirmed": False,
                "test_cases_self_review_passed": False,
            },
        },
    )
    final_review = load_script(
        "test-result-review/scripts/final_review.py",
        "test_final_review_contract_module",
    )

    with pytest.raises(AssertionError, match="current test-case self-review and user-confirmation flags"):
        final_review.validate(
            {
                "execution_plan_ref": "internal/execution/execution-plan.json",
                "case_result_ledger_ref": "internal/execution/results/case-results-ledger.json",
            },
            run_dir=run,
        )
