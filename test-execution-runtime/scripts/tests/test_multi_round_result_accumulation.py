"""Rework chains must keep the per-Case latest result and must not commit byte-stale results."""
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1]
REPO = SCRIPTS.parents[1]
sys.path.insert(0, str(SCRIPTS))
import runtime_orchestrator as runtime


def _sample_plan():
    spec = importlib.util.spec_from_file_location(
        'runtime_merge_samples',
        REPO / 'test-execution-planning/scripts/tests/test_execution_planning_v2.py')
    samples = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(samples)
    return samples._sample_valid_plan({})


def _write(tmp_path, ref, payload):
    path = tmp_path / ref
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding='utf-8')
    return path


def _script(tmp_path, rel, body):
    path = tmp_path / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding='utf-8')
    return path


def _result(case_id, rel, body):
    digest = hashlib.sha256(body.encode('utf-8')).hexdigest()
    return {
        'case_id': case_id,
        'status': 'PASS',
        'automation_run': {'script_ref': rel, 'script_sha256': digest},
    }


def _round(tmp_path, name, results):
    ref = f'internal/execution/results/{name}.json'
    _write(tmp_path, ref, results)
    return ref


def test_accumulated_results_keep_the_per_case_latest_round(tmp_path):
    rel0 = 'scripts/ui/B01/first.spec.ts'
    rel1 = 'scripts/ui/B01/second.spec.ts'
    _script(tmp_path, rel0, '// v1')
    _script(tmp_path, rel1, '// v1')
    first, second = 'TC-FIRST', 'TC-SECOND'

    worker_ref = _round(tmp_path, 'B01-worker-results', [
        _result(first, rel0, '// v1'), _result(second, rel1, '// v1')])
    retest_ref = _round(tmp_path, 'B01-retest-001-results', [
        _result(first, rel0, '// v1')])

    state = {
        'batch_id': 'B01',
        'worker_results_ref': worker_ref,
        'retest_history': [{'results_ref': retest_ref}],
    }
    by = runtime._accumulated_results(tmp_path, state)
    assert set(by) == {first, second}
    # Both Cases keep a result; the retested Case comes from the later round, the other from the original.
    assert by[first]['automation_run']['script_sha256'] == hashlib.sha256('// v1'.encode()).hexdigest()
    assert by[second]['automation_run']['script_sha256'] == hashlib.sha256('// v1'.encode()).hexdigest()


def test_accumulated_results_let_a_later_round_replace_only_its_own_cases(tmp_path):
    rel = 'scripts/ui/B01/case.spec.ts'
    _script(tmp_path, rel, '// v2')
    worker_ref = _round(tmp_path, 'B01-worker-results', [_result('TC-1', rel, '// v1')])
    retest_ref = _round(tmp_path, 'B01-retest-001-results', [
        dict(_result('TC-1', rel, '// v2'), status='FAIL')])
    state = {'batch_id': 'B01', 'worker_results_ref': worker_ref,
             'retest_history': [{'results_ref': retest_ref}]}
    by = runtime._accumulated_results(tmp_path, state)
    assert by['TC-1']['status'] == 'FAIL'
    assert by['TC-1']['automation_run']['script_sha256'] == hashlib.sha256('// v2'.encode()).hexdigest()


def test_stale_script_cases_reports_bytes_changed_after_the_run(tmp_path):
    rel = 'scripts/ui/B01/case.spec.ts'
    _script(tmp_path, rel, '// frozen bytes')
    good = _result('TC-1', rel, '// frozen bytes')
    edited = _result('TC-2', rel, '// older bytes')
    missing = {'case_id': 'TC-3', 'status': 'PASS',
               'automation_run': {'script_ref': 'scripts/ui/B01/gone.spec.ts',
                                  'script_sha256': 'deadbeef'}}
    stale = runtime._stale_script_cases(tmp_path, {'TC-1': good, 'TC-2': edited, 'TC-3': missing})
    assert stale == ['TC-2', 'TC-3']


def test_next_retest_round_covers_requested_and_byte_stale_cases(tmp_path):
    rel = 'scripts/ui/B01/case.spec.ts'
    _script(tmp_path, rel, '// newer bytes')
    results = {'TC-1': _result('TC-1', rel, '// older bytes'), 'TC-2': _result('TC-2', rel, '// newer bytes')}
    wanted = runtime._next_retest_case_ids(tmp_path, results, ['TC-2'])
    assert wanted == ['TC-1', 'TC-2']


def test_next_retest_round_is_unchanged_when_everything_is_current(tmp_path):
    rel = 'scripts/ui/B01/case.spec.ts'
    _script(tmp_path, rel, '// same bytes')
    results = {'TC-1': _result('TC-1', rel, '// same bytes')}
    assert runtime._next_retest_case_ids(tmp_path, results, ['TC-1']) == ['TC-1']
    assert runtime._next_retest_case_ids(tmp_path, results, []) == []
