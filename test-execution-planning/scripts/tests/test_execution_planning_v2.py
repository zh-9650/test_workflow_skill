"""Unit and integration tests for Execution Planning V2 validation rules."""

import pytest
import hashlib
import json
import importlib.util
from pathlib import Path

_plan_path = Path(__file__).resolve().parents[1] / "execution_plan.py"
_spec = importlib.util.spec_from_file_location("execution_plan", _plan_path)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
validate = _mod.validate


def _sample_confirmed_cases():
    return {
        "cases": [
            {
                "case_id": "TC-API-001",
                "title": "API Test Case",
                "target_action": "POST /api/login",
                "preconditions": ["User exists"],
                "test_data": {"user": "tester"},
                "steps": ["Send POST /api/login"],
                "expected_results": [
                    {"id": "E1", "expected": "HTTP 200 returned"}
                ],
                "evidence_policy": {
                    "level": "standard",
                    "recording_required": False,
                    "required": [
                        {"kind": "request_response", "assertion_ids": ["E1"], "redacted": True}
                    ]
                }
            },
            {
                "case_id": "TC-UI-001",
                "title": "UI Test Case",
                "target_action": "Click login button",
                "preconditions": ["Page opened"],
                "test_data": {},
                "steps": ["Click #submit"],
                "expected_results": [
                    {"id": "E2", "expected": "Dashboard visible"}
                ],
                "evidence_policy": {
                    "level": "critical",
                    "recording_required": True,
                    "required": [
                        {"kind": "screenshot", "assertion_ids": ["E2"]}
                    ]
                }
            }
        ]
    }


def _sample_valid_plan(confirmed_cases):
    return {
        "schema_version": 2,
        "confirmed_case_ids": ["TC-API-001", "TC-UI-001"],
        "confirmed_cases_sha256": "dummy-hash",
        "self_review": {
            "status": "passed",
            "checks": {
                "all_cases_assigned": True,
                "execution_method_checked": True,
                "batch_logic_checked": True,
                "dependency_checked": True,
                "evidence_checked": True,
                "data_strategy_checked": True
            }
        },
        "user_confirmation": {
            "status": "confirmed"
        },
        "target_environment": {
            "env_id": "test",
            "initial_deployment_version": "v1.0.0",
            "web_base_url": "http://127.0.0.1:3000",
            "api_base_url": "http://127.0.0.1:3000/api"
        },
        "defect_platform": {
            "platform_type": "generic",
            "project_key": "PROJ-1",
            "credential_ref": "env:DEFECT_TOKEN"
        },
        "data_requirements": [
            {
                "scope": "base_resource",
                "object_type": "user_account",
                "case_ids": ["TC-API-001", "TC-UI-001"]
            }
        ],
        "batches": [
            {
                "id": "B01",
                "parallel_safe": False,
                "case_ids": ["TC-API-001"]
            },
            {
                "id": "B02",
                "parallel_safe": False,
                "case_ids": ["TC-UI-001"]
            }
        ],
        "cases": [
            {
                "case_id": "TC-API-001",
                "title": "API Test Case",
                "target_action": "POST /api/login",
                "preconditions": ["User exists"],
                "test_data": {"user": "tester"},
                "steps": ["Send POST /api/login"],
                "expected_results": [
                    {"id": "E1", "expected": "HTTP 200 returned"}
                ],
                "primary_execution": "API",
                "batch_id": "B01",
                "dependencies": [],
                "automation": {
                    "required": True,
                    "language": "typescript",
                    "runner": "vitest",
                    "driver": "node-native-fetch",
                    "script_target": "scripts/api/B01/TC-API-001.test.ts",
                    "script_strategy": "create_or_update"
                },
                "evidence_plan": {
                    "level": "standard",
                    "screenshots": [],
                    "recording": False,
                    "api": [{"kind": "request_response", "expected_ids": ["E1"], "redacted": True}],
                    "network": [],
                    "files": [],
                    "read_back_required": False
                },
                "jev_policy": {
                    "mode": "conditional",
                    "target_type": "api_semantic_judgment",
                    "purpose": "Verify semantic equivalence of error body",
                    "trigger_condition": "Status code is 422",
                    "bounded_options": ["valid_validation_error", "internal_error"],
                    "failure_fallback": "mark_step_fail",
                    "max_cost_usd": 0.05,
                    "expected_ids": ["E1"]
                }
            },
            {
                "case_id": "TC-UI-001",
                "title": "UI Test Case",
                "target_action": "Click login button",
                "preconditions": ["Page opened"],
                "test_data": {},
                "steps": ["Click #submit"],
                "expected_results": [
                    {"id": "E2", "expected": "Dashboard visible"}
                ],
                "primary_execution": "UI",
                "batch_id": "B02",
                "dependencies": ["TC-API-001"],
                "automation": {
                    "required": True,
                    "language": "typescript",
                    "runner": "playwright-test",
                    "driver": "playwright-page",
                    "script_target": "scripts/ui/B02/TC-UI-001.spec.ts",
                    "script_strategy": "create_or_update"
                },
                "evidence_plan": {
                    "level": "critical",
                    "screenshots": [{"kind": "screenshot", "expected_ids": ["E2"]}],
                    "recording": True,
                    "api": [],
                    "network": [],
                    "files": []
                },
                "jev_policy": {
                    "mode": "none",
                    "target_type": "ui_candidate_revalidation",
                    "purpose": "None",
                    "trigger_condition": "None",
                    "bounded_options": ["default"],
                    "failure_fallback": "abort",
                    "max_cost_usd": 0.01,
                    "expected_ids": ["E2"]
                }
            }
        ]
    }


def test_valid_v2_plan():
    confirmed = _sample_confirmed_cases()
    plan = _sample_valid_plan(confirmed)
    result = validate(plan, require_confirmed=True, confirmed_cases=confirmed, require_context=True)
    assert result["ok"] is True
    assert result["cases"] == 2
    assert result["batches"] == 2


def test_reject_plain_secret_in_defect_platform():
    confirmed = _sample_confirmed_cases()
    plan = _sample_valid_plan(confirmed)
    plan["defect_platform"]["credential_ref"] = "password123"
    with pytest.raises(AssertionError, match="credential_ref"):
        validate(plan, require_confirmed=True, confirmed_cases=confirmed, require_context=True)


def test_reject_invalid_api_url():
    confirmed = _sample_confirmed_cases()
    plan = _sample_valid_plan(confirmed)
    plan["target_environment"]["api_base_url"] = "ftp://invalid-url"
    with pytest.raises(AssertionError, match="api_base_url"):
        validate(plan, require_confirmed=True, confirmed_cases=confirmed, require_context=True)


def test_reject_provider_switching_fallback():
    confirmed = _sample_confirmed_cases()
    plan = _sample_valid_plan(confirmed)
    plan["cases"][0]["jev_policy"]["failure_fallback"] = "switch_provider_to_openai"
    with pytest.raises(AssertionError, match="failure_fallback"):
        validate(plan, require_confirmed=True, confirmed_cases=confirmed, require_context=True)


def test_reject_mismatched_target_type():
    confirmed = _sample_confirmed_cases()
    plan = _sample_valid_plan(confirmed)
    # API case must not use ui_candidate_revalidation
    plan["cases"][0]["jev_policy"]["target_type"] = "ui_candidate_revalidation"
    with pytest.raises(AssertionError, match="target_type"):
        validate(plan, require_confirmed=True, confirmed_cases=confirmed, require_context=True)


def test_reject_unknown_expected_id_in_jev_policy():
    confirmed = _sample_confirmed_cases()
    plan = _sample_valid_plan(confirmed)
    plan["cases"][0]["jev_policy"]["expected_ids"] = ["E999"]
    with pytest.raises(AssertionError, match="expected_ids"):
        validate(plan, require_confirmed=True, confirmed_cases=confirmed, require_context=True)


def test_ui_case_accepts_ui_candidate_revalidation():
    confirmed = _sample_confirmed_cases()
    plan = _sample_valid_plan(confirmed)
    # UI case using ui_candidate_revalidation per SKILL.md:445
    plan["cases"][1]["jev_policy"]["target_type"] = "ui_candidate_revalidation"
    out = validate(plan, require_confirmed=True, confirmed_cases=confirmed, require_context=True)
    assert out["ok"] is True


def test_legacy_plan_without_context_rejected_by_default():
    confirmed = _sample_confirmed_cases()
    plan = _sample_valid_plan(confirmed)
    del plan["target_environment"]
    with pytest.raises(AssertionError, match="target_environment"):
        validate(plan, require_confirmed=True, confirmed_cases=confirmed)

