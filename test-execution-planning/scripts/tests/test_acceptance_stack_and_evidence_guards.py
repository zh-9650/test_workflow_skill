"""Explicit acceptance-negative contracts, not native-host forward evidence."""
import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    'acceptance_planning_fixtures', Path(__file__).with_name('test_execution_planning_v2.py'))
fixtures = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixtures)


def sample():
    confirmed = fixtures._sample_confirmed_cases()
    plan = fixtures._sample_valid_plan(confirmed)
    assert fixtures.validate(plan, require_confirmed=True, confirmed_cases=confirmed, require_context=True)['ok']
    return confirmed, plan


def reject(confirmed, plan, message):
    with pytest.raises(AssertionError, match=message):
        fixtures.validate(plan, require_confirmed=True, confirmed_cases=confirmed, require_context=True)


@pytest.mark.parametrize('driver', ['playwright-api-request-context', 'APIRequestContext'])
def test_api_request_context_cannot_be_primary_driver(driver):
    confirmed, plan = sample()
    plan['cases'][0]['automation']['driver'] = driver
    reject(confirmed, plan, 'driver')


def test_ordinary_ui_requires_a_planned_expected_screenshot():
    confirmed, plan = sample()
    confirmed['cases'][1]['evidence_policy'] = {
        'level': 'standard', 'recording_required': False,
        'required': [{'kind': 'screenshot', 'assertion_ids': ['E2']}]}
    plan['cases'][1]['evidence_plan'].update(level='standard', recording=False, screenshots=[])
    reject(confirmed, plan, 'screenshot')


@pytest.mark.parametrize('missing', ['recording', 'screenshots'])
def test_critical_ui_cannot_drop_video_or_screenshots(missing):
    confirmed, plan = sample()
    plan['cases'][1]['evidence_plan'][missing] = False if missing == 'recording' else []
    reject(confirmed, plan, 'recording|screenshot|critical')


@pytest.mark.parametrize('case_index', [0, 1])
def test_automated_case_requires_explicit_script_target(case_index):
    confirmed, plan = sample()
    del plan['cases'][case_index]['automation']['script_target']
    reject(confirmed, plan, 'script_target')


@pytest.mark.parametrize('field', ['target_environment', 'defect_platform'])
def test_run_binding_cannot_be_replaced_by_project_defaults(field):
    confirmed, plan = sample()
    del plan[field]
    reject(confirmed, plan, field)
