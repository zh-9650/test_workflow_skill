"""Executable forward gates. Each xfail is owned by a later phase.

These are intentionally small probes. Phase-specific work must replace them
with behavior checks and real API/UI/Agent runs before removing xfail.
"""

from __future__ import annotations

import pytest

from conftest import load_script
from test_execution_plan_v2 import _confirmed_cases, _plan
from test_runtime_schema_v2 import _case_contract_payload, _reviewer_result


@pytest.mark.xfail(strict=True, reason="Phase 2 Planning V2 stack mapping")
def test_api_plan_rejects_playwright_as_primary_driver() -> None:
    contract = load_script(
        "test-execution-planning/scripts/execution_plan.py",
        "forward_plan_contract",
    )
    plan = _plan(2)
    plan["cases"][0]["automation"] = {
        "required": True,
        "language": "typescript",
        "runner": "playwright-test",
        "driver": "playwright-api-request-context",
        "script_target": "scripts/api/B01/TC-API-001.test.ts",
    }

    with pytest.raises(AssertionError, match="runner|driver|automation"):
        contract.validate(
            plan,
            confirmed_cases=_confirmed_cases(),
            confirmed_cases_sha256="confirmed-sha",
        )


@pytest.mark.xfail(strict=True, reason="Phase 4 official script provenance")
def test_case_result_requires_final_script_and_official_run(tmp_path) -> None:
    contract = load_script(
        "test-execution-runtime/scripts/execution_control.py",
        "forward_case_contract",
    )
    plan_case, result = _case_contract_payload(tmp_path)

    with pytest.raises(AssertionError, match="automation_run|script|official_run"):
        contract.validate(plan_case, result, tmp_path)


@pytest.mark.xfail(strict=True, reason="Phase 4 independent Reviewer session")
def test_reviewer_cannot_reuse_worker_session() -> None:
    contract = load_script(
        "test-execution-runtime/scripts/reviewer_contract.py",
        "forward_reviewer_contract",
    )
    review = _reviewer_result()
    review["agent_session_id"] = "worker-session"

    with pytest.raises(AssertionError, match="agent_session_id|session"):
        contract.validate(
            review,
            ["TC-001"],
            worker_session_id="worker-session",
        )
