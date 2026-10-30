"""TD-01 regression: multi-round retest merge must keep every round's judgement.

Defect TD-01: the retest merge baseline was "initial round + last round only", so a
judgement produced by an intermediate round was silently replaced by the initial
round's value whenever the final round did not re-run that Case:

  Mode A: intermediate FAIL, final round does not cover the Case -> washed into the
          initial PASS -> a genuine product failure disappears from the ledger;
  Mode B: intermediate NEEDS_REVIEW not covered by the final round -> either washed
          into the initial PASS, or degraded into the ledger layer's vague
          "cannot commit non-final status NEEDS_REVIEW" error.

Synthetic file-backed coverage of accept_retest_reviewer_files; not host dispatch acceptance.
"""
import sys
from pathlib import Path

import pytest

scripts = Path(__file__).parents[1]
sys.path.insert(0, str(scripts))
import runtime_orchestrator as runtime
import retest_task
from reviewer_contract import EXECUTION_SCHEMA_VERSION

ENV = 'local-fixture'
DEPLOY = 'v1'
WORKER_SESSION = 'worker-session-1'
REVIEWER_SESSION = 'reviewer-session-1'
WORKER_CHECKS = ['all_cases_checked', 'all_expected_checked', 'execution_method_checked',
                 'evidence_binding_checked', 'failure_classification_checked', 'file_cleanup_checked']
REVIEWER_CHECKS = ['completeness_checked', 'method_consistency_checked', 'judgement_checked',
                   'evidence_checked', 'abnormal_classification_checked']


def _row(case_id, status, **extra):
    row = {'case_id': case_id, 'status': status, 'target_environment': ENV, 'deployment_version': DEPLOY}
    row.update(extra)
    return row


def _task(case_order, task_id='B01', dependencies=None):
    cases = []
    for cid in case_order:
        case = {'case_id': cid}
        if dependencies and cid in dependencies:
            case['dependencies'] = list(dependencies[cid])
        cases.append(case)
    return {'schema_version': EXECUTION_SCHEMA_VERSION, 'task_id': task_id, 'batch_id': 'B01',
            'target_environment': ENV, 'deployment_version': DEPLOY, 'case_order': list(case_order),
            'cases': cases, 'dependency_context': {}, 'task_hash': 'a' * 64}


def _install_seams(monkeypatch):
    """Neutralize the contracts that are not the subject of this regression."""
    monkeypatch.setattr(runtime, 'validate_task', lambda task: None)
    monkeypatch.setattr(runtime, 'seal_task', lambda task: None)
    monkeypatch.setattr(runtime, 'validate_case_result', lambda *a, **k: None)
    monkeypatch.setattr(runtime, '_validate_frozen_artifacts', lambda *a, **k: None)
    monkeypatch.setattr(retest_task, 'seal_task', lambda task: None)
    monkeypatch.setattr(retest_task, 'validate', lambda task: None)


def _seed(base, case_order, worker_rows, dependencies=None):
    """Create the initial round artifacts plus the round-0 runtime state."""
    runtime._write_json(base / 'internal/execution/tasks/B01-task.json',
                        _task(case_order, dependencies=dependencies))
    runtime._write_json(base / 'internal/execution/results/B01-worker-results.json', worker_rows)
    runtime._write_json(base / runtime.CASE_LEDGER_REL, {'cases': {}})
    state = {
        'batch_id': 'B01', 'status': 'needs_rework',
        'task_ref': 'internal/execution/tasks/B01-task.json',
        'worker_results_ref': 'internal/execution/results/B01-worker-results.json',
        'worker_self_review': {'status': 'passed', 'checks': {k: True for k in WORKER_CHECKS},
                               'findings': [{'id': 'W0', 'summary': 'initial worker finding'}]},
        'reviewer': {'status': 'passed', 'checks': {k: True for k in REVIEWER_CHECKS},
                     'findings': [{'id': 'R0', 'summary': 'initial reviewer finding'}]},
        'review_history': [], 'retest_history': [], 'retest_tasks': [], 'active_retest': None,
        'partial_case_results': {}, 'current_case': None, 'current_worker': None,
        'case_result_ledger_ref': runtime.CASE_LEDGER_REL,
    }
    runtime._write_json(base / 'internal/execution/runtime-state/B01-state.json', state)


def _open_round(base, sequence, scope, rows, worker_findings=None, mode=None, regression_id=None):
    """Attach the finished artifacts of one retest round to the active round."""
    state_path = base / 'internal/execution/runtime-state/B01-state.json'
    state = runtime._read_json(state_path)
    if not state.get('active_retest'):
        task_ref = f'internal/execution/tasks/B01-retest-{sequence:03d}.json'
        runtime._write_json(base / task_ref, _task(scope, task_id=f'B01-retest-{sequence:03d}'))
        state['active_retest'] = {'task_ref': task_ref, 'sequence': sequence}
        state.setdefault('retest_tasks', []).append(task_ref)
    results_ref = f'internal/execution/results/B01-retest-{sequence:03d}-results.json'
    self_ref = f'internal/execution/dispatch/B01-retest-{sequence:03d}-worker-self-review.json'
    reviewer_task_ref = f'internal/execution/dispatch/B01-retest-{sequence:03d}-reviewer-task.json'
    runtime._write_json(base / results_ref, rows)
    runtime._write_json(base / self_ref, {'agent_session_id': WORKER_SESSION, 'status': 'passed',
                                          'checks': {k: True for k in WORKER_CHECKS},
                                          'findings': list(worker_findings or [])})
    reviewer_task = {
        'schema_version': EXECUTION_SCHEMA_VERSION, 'task_id': f'B01-reviewer-{sequence:03d}',
        'batch_id': 'B01', 'target_environment': ENV, 'deployment_version': DEPLOY,
        'case_order': list(scope), 'worker_task_id': f'B01-retest-{sequence:03d}',
        'worker_task_hash': 'b' * 64, 'worker_session_id': WORKER_SESSION,
        'results_ref': results_ref, 'results_sha256': runtime._sha256(base / results_ref),
        'worker_self_review_ref': self_ref, 'worker_self_review_sha256': runtime._sha256(base / self_ref),
    }
    reviewer_task['task_hash'] = runtime._canonical_sha256(reviewer_task)
    runtime._write_json(base / reviewer_task_ref, reviewer_task)
    state['active_retest'].update({'sequence': sequence, 'results_ref': results_ref,
                                    'self_review_ref': self_ref,
                                    'self_review': runtime._read_json(base / self_ref),
                                    'reviewer_task_ref': reviewer_task_ref,
                                    'mode': mode, 'regression_id': regression_id,
                                    'worker_dispatch_receipt': {'agent_session_id': WORKER_SESSION},
                                    'reviewer_dispatch_receipt': {'agent_session_id': REVIEWER_SESSION}})
    state['status'] = 'retest_reviewing'
    runtime._write_json(state_path, state)
    return reviewer_task


def _review(reviewer_task, scope, status, retest_case_ids=None, findings=None):
    return {
        'schema_version': EXECUTION_SCHEMA_VERSION, 'status': status, 'findings': list(findings or []),
        'checked_case_ids': list(scope), 'retest_case_ids': list(retest_case_ids or []), 'return_stage': None,
        'checks': {k: True for k in REVIEWER_CHECKS},
        'reviewer_task_id': reviewer_task['task_id'], 'input_task_hash': reviewer_task['task_hash'],
        'input_results_sha256': reviewer_task['results_sha256'], 'agent_session_id': REVIEWER_SESSION,
    }


def _run_reviewer(base, reviewer_task, review):
    path = base / f"internal/execution/dispatch/review-{reviewer_task['task_id']}.json"
    runtime._write_json(path, review)
    return runtime.accept_retest_reviewer_files(base, 'B01', path)


def test_intermediate_round_fail_is_not_washed_into_the_initial_pass(tmp_path, monkeypatch):
    """Mode A: a Case the final round did not re-run keeps its intermediate FAIL."""
    _install_seams(monkeypatch)
    base = tmp_path
    _seed(base, ['C1', 'C2', 'C3'], [_row('C1', 'PASS'), _row('C2', 'PASS'), _row('C3', 'PASS')])
    # Round 1 re-runs C1 and C2. C2 fails as a product issue and is not asked for rework;
    # C1 stays in NEEDS_REVIEW and is the only Case the Reviewer asks to re-run.
    rt1 = _open_round(base, 1, ['C1', 'C2'],
                       [_row('C1', 'NEEDS_REVIEW'), _row('C2', 'FAIL', reason_type='product_issue')])
    _run_reviewer(base, rt1, _review(rt1, ['C1', 'C2'], 'rework_required', retest_case_ids=['C1']))
    # Round 2 re-runs C1 only and passes.
    rt2 = _open_round(base, 2, ['C1'], [_row('C1', 'PASS')])
    _run_reviewer(base, rt2, _review(rt2, ['C1'], 'passed'))
    merged = {r['case_id']: r for r in
              runtime._read_json(base / 'internal/execution/results/B01-merged-after-retest-002.json')}
    assert merged['C2']['status'] == 'FAIL'
    ledger = runtime._read_json(base / runtime.CASE_LEDGER_REL)['cases']
    assert ledger['C2']['final_result'] == 'FAIL'


def test_case_left_in_need_review_blocks_batch_close_and_names_the_case(tmp_path, monkeypatch):
    """Mode B: a Case left in NEEDS_REVIEW by an earlier round cannot be closed silently."""
    _install_seams(monkeypatch)
    base = tmp_path
    _seed(base, ['C1', 'C2'], [_row('C1', 'PASS'), _row('C2', 'PASS')])
    rt1 = _open_round(base, 1, ['C1', 'C2'], [_row('C1', 'NEEDS_REVIEW'), _row('C2', 'NEEDS_REVIEW')])
    _run_reviewer(base, rt1, _review(rt1, ['C1', 'C2'], 'rework_required', retest_case_ids=['C1']))
    rt2 = _open_round(base, 2, ['C1'], [_row('C1', 'PASS')])
    with pytest.raises(AssertionError) as err:
        _run_reviewer(base, rt2, _review(rt2, ['C1'], 'passed'))
    message = str(err.value)
    assert 'retest_merge.pending_cases' in message
    assert 'C2' in message


def test_intermediate_round_findings_are_preserved(tmp_path, monkeypatch):
    """Findings produced by an intermediate round must survive into the composed review."""
    _install_seams(monkeypatch)
    base = tmp_path
    _seed(base, ['C1', 'C2'], [_row('C1', 'PASS'), _row('C2', 'PASS')])
    rt1 = _open_round(base, 1, ['C1', 'C2'], [_row('C1', 'NEEDS_REVIEW'), _row('C2', 'PASS')],
                       worker_findings=[{'id': 'W1', 'summary': 'round-1 worker finding'}])
    _run_reviewer(base, rt1, _review(rt1, ['C1', 'C2'], 'rework_required', retest_case_ids=['C1'],
                                     findings=[{'id': 'R1', 'summary': 'round-1 reviewer finding'}]))
    rt2 = _open_round(base, 2, ['C1'], [_row('C1', 'PASS')],
                      worker_findings=[{'id': 'W2', 'summary': 'round-2 worker finding'}])
    state = _run_reviewer(base, rt2, _review(rt2, ['C1'], 'passed',
                                             findings=[{'id': 'R2', 'summary': 'round-2 reviewer finding'}]))
    reviewer_ids = {f.get('id') for f in state['reviewer']['findings']}
    assert {'R0', 'R1', 'R2'} <= reviewer_ids
    worker_ids = {f.get('id') for f in state['worker_self_review']['findings']}
    assert {'W0', 'W1', 'W2'} <= worker_ids


def test_next_rework_round_baseline_carries_the_intermediate_judgement(tmp_path, monkeypatch):
    """The next retest Task must be built on the cumulative judgement, not on round 0."""
    _install_seams(monkeypatch)
    base = tmp_path
    _seed(base, ['C1', 'C2'], [_row('C1', 'PASS'), _row('C2', 'PASS')], dependencies={'C1': ['C2']})
    rt1 = _open_round(base, 1, ['C1', 'C2'], [_row('C1', 'NEEDS_REVIEW'), _row('C2', 'FAIL')])
    state = _run_reviewer(base, rt1, _review(rt1, ['C1', 'C2'], 'rework_required', retest_case_ids=['C1']))
    cumulative_ref = state.get('retest_cumulative_ref')
    assert cumulative_ref, 'the retest chain must record a cumulative baseline'
    cumulative = {r['case_id']: r for r in runtime._read_json(base / cumulative_ref)}
    assert cumulative['C2']['status'] == 'FAIL'
    task2 = runtime._read_json(base / 'internal/execution/tasks/B01-retest-002.json')
    assert task2['dependency_context']['C2']['status'] == 'FAIL'


def test_single_round_chain_keeps_its_own_judgement(tmp_path, monkeypatch):
    """Regression guard for the ordinary one-round retest: the merged set stays the same."""
    _install_seams(monkeypatch)
    base = tmp_path
    _seed(base, ['C1', 'C2'], [_row('C1', 'PASS'), _row('C2', 'FAIL', reason_type='product_issue')])
    rt1 = _open_round(base, 1, ['C1'], [_row('C1', 'PASS')])
    _run_reviewer(base, rt1, _review(rt1, ['C1'], 'passed'))
    merged = {r['case_id']: r for r in
              runtime._read_json(base / 'internal/execution/results/B01-merged-after-retest-001.json')}
    assert merged['C1']['status'] == 'PASS'
    assert merged['C2']['status'] == 'FAIL'
    ledger = runtime._read_json(base / runtime.CASE_LEDGER_REL)['cases']
    assert ledger['C1']['final_result'] == 'PASS'
    assert ledger['C2']['final_result'] == 'FAIL'


def test_blocked_resume_round_keeps_its_own_commit_path(tmp_path, monkeypatch):
    """The BLOCKED-resume path commits the resumed rows, not the merged set."""
    _install_seams(monkeypatch)
    base = tmp_path
    _seed(base, ['C1', 'C2'], [_row('C1', 'BLOCKED'), _row('C2', 'PASS')])
    ledger = runtime._read_json(base / runtime.CASE_LEDGER_REL)
    ledger['cases']['C1'] = {'case_id': 'C1', 'batch_id': 'B01', 'status': 'BLOCKED', 'final_result': 'BLOCKED',
                             'reviewer_confirmed': True, 'runtime_result': _row('C1', 'BLOCKED')}
    runtime._write_json(base / runtime.CASE_LEDGER_REL, ledger)
    rt1 = _open_round(base, 1, ['C1'], [_row('C1', 'PASS')], mode='resume_after_regression')
    state = _run_reviewer(base, rt1, _review(rt1, ['C1'], 'passed'))
    assert state['status'] == 'completed'
    rows = runtime._read_json(base / runtime.CASE_LEDGER_REL)['cases']
    assert rows['C1']['final_result'] == 'PASS'
    assert rows['C1']['source'] == 'unblocked_cases_reviewer_passed'
    assert rows['C1']['resume_result']['status'] == 'PASS'
    assert rows['C1']['blocked_runtime_result']['status'] == 'BLOCKED'


def test_blocked_resume_round_is_not_stalled_by_an_unjudged_case_outside_its_scope(tmp_path, monkeypatch):
    """A BLOCKED resume commits the resumed rows alone, so an unjudged Case elsewhere must not stall it."""
    _install_seams(monkeypatch)
    base = tmp_path
    _seed(base, ['C1', 'C2'], [_row('C1', 'BLOCKED'), _row('C2', 'NEEDS_REVIEW')])
    ledger = runtime._read_json(base / runtime.CASE_LEDGER_REL)
    ledger['cases']['C1'] = {'case_id': 'C1', 'batch_id': 'B01', 'status': 'BLOCKED', 'final_result': 'BLOCKED',
                             'reviewer_confirmed': True, 'runtime_result': _row('C1', 'BLOCKED')}
    runtime._write_json(base / runtime.CASE_LEDGER_REL, ledger)
    rt1 = _open_round(base, 1, ['C1'], [_row('C1', 'PASS')], mode='resume_after_regression')
    state = _run_reviewer(base, rt1, _review(rt1, ['C1'], 'passed'))
    assert state['status'] == 'completed'
    rows = runtime._read_json(base / runtime.CASE_LEDGER_REL)['cases']
    assert rows['C1']['final_result'] == 'PASS'


def test_product_regression_round_keeps_its_own_aggregate(tmp_path, monkeypatch):
    """The product-regression path aggregates by regression id and does not touch the general ledger."""
    _install_seams(monkeypatch)
    base = tmp_path
    _seed(base, ['C1'], [_row('C1', 'FAIL', reason_type='product_issue', bug_ref='BUG-1')])
    rt1 = _open_round(base, 1, ['C1'], [_row('C1', 'FAIL', reason_type='product_issue', bug_ref='BUG-1')],
                      mode='product_regression', regression_id='REG-1')
    state = _run_reviewer(base, rt1, _review(rt1, ['C1'], 'passed'))
    assert state['status'] == 'completed'
    assert state.get('retest_cumulative_ref') is None, 'product regression keeps its own aggregate'
    aggregate_ref = state['product_regression_results_ref']
    assert aggregate_ref == 'internal/execution/results/B01-REG-1-final-regression-results.json'
    aggregate = runtime._read_json(base / aggregate_ref)
    assert [r['status'] for r in aggregate] == ['FAIL']
    assert runtime._read_json(base / runtime.CASE_LEDGER_REL)['cases'] == {}
