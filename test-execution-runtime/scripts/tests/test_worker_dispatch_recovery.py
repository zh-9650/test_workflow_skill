"""File-backed recovery contracts with synthetic receipts, not real host acceptance."""
import importlib.util
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1]
REPO = SCRIPTS.parents[1]
sys.path.insert(0, str(SCRIPTS))
import runtime_orchestrator as runtime


def fixture(tmp_path, *, started=False, retest=False):
    spec = importlib.util.spec_from_file_location(
        'host_recovery_plan_samples',
        REPO / 'test-execution-planning/scripts/tests/test_execution_planning_v2.py')
    samples = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(samples)
    plan = samples._sample_valid_plan({})
    task = runtime.build_task(plan, 'B01', 'internal/execution/context.json', 'internal/data/B01.json')
    task_ref = 'internal/execution/tasks/B01.json'
    runtime._write_json(tmp_path / task_ref, task)
    previous = {
        'agent_role': 'execution_worker', 'task_id': task['task_id'],
        'task_hash': task['task_hash'], 'agent_session_id': 'synthetic-old-worker',
        'dispatch_source': 'codex_subagent_tool',
        'host_dispatch_ref': 'synthetic-contract-only:old',
        'started_at': '2026-10-04T00:00:00Z', 'receipt_status': 'dispatched'}
    replacement = {**previous, 'agent_session_id': 'synthetic-new-worker',
                   'host_dispatch_ref': 'synthetic-contract-only:new',
                   'started_at': '2026-10-04T00:02:00Z'}
    terminal = {
        'status': 'failed', 'agent_session_id': previous['agent_session_id'],
        'host_dispatch_ref': previous['host_dispatch_ref'], 'task_id': task['task_id'],
        'task_hash': task['task_hash'], 'reason': 'Synthetic terminal failure',
        'observed_at': '2026-10-04T00:01:00Z', 'observed_via': 'codex_subagent_tool'}
    holder = {'task_ref': task_ref, 'worker_dispatch_receipt': previous,
              'current_case': task['case_order'][0] if started else None,
              'partial_case_results': {}, 'current_worker': previous['agent_session_id']}
    state = {'batch_id': 'B01', 'status': 'retest_running' if retest else 'running'}
    if retest:
        state['active_retest'] = holder
    else:
        state.update(holder)
    state_path = tmp_path / 'internal/execution/runtime-state/B01-state.json'
    runtime._write_json(state_path, state)
    replacement_path = tmp_path / 'internal/execution/host/replacement.json'
    terminal_path = tmp_path / 'internal/execution/host/terminal.json'
    runtime._write_json(replacement_path, replacement)
    runtime._write_json(terminal_path, terminal)
    return task, state_path, replacement_path, terminal_path


@pytest.mark.parametrize('retest', [False, True])
def test_terminal_worker_can_recover_before_first_case(tmp_path, retest):
    task, state_path, receipt, terminal = fixture(tmp_path, retest=retest)
    result = runtime.recover_worker_dispatch_files(tmp_path, 'B01', receipt, terminal, retest)
    holder = result['active_retest'] if retest else result
    assert holder['current_case'] is None  # Recovery must not invent case-start.
    assert holder['partial_case_results'] == {}
    assert holder['worker_dispatch_receipt']['agent_session_id'] == 'synthetic-new-worker'
    history = holder['worker_recovery_history']
    runtime._validate_worker_recovery_history(tmp_path, history, task, 'B01')
    record = runtime._read_json(tmp_path / history[0]['record_ref'])
    assert record['case_id'] == task['case_order'][0]
    assert record['recovery_phase'] == 'before_first_case'
    assert record['previous_worker_receipt']['agent_session_id'] == 'synthetic-old-worker'


def test_terminal_worker_recovery_preserves_active_case_artifacts(tmp_path):
    task, state_path, receipt, terminal = fixture(tmp_path, started=True)
    script = tmp_path / task['cases'][0]['automation']['script_target']
    script.parent.mkdir(parents=True)
    script.write_text('// synthetic unfinished script', encoding='utf8')
    result = runtime.recover_worker_dispatch_files(tmp_path, 'B01', receipt, terminal)
    runtime._validate_worker_recovery_history(tmp_path, result['worker_recovery_history'], task, 'B01')
    assert result['current_case'] == task['case_order'][0]
    record = runtime._read_json(tmp_path / result['worker_recovery_history'][0]['record_ref'])
    assert record['recovery_phase'] == 'active_case'
    assert script.read_text(encoding='utf8') == '// synthetic unfinished script'


@pytest.mark.parametrize('mutation', ['committed', 'same_session', 'wrong_terminal'])
def test_worker_recovery_rejects_unsafe_replacement_without_state_change(tmp_path, mutation):
    task, state_path, receipt, terminal = fixture(tmp_path)
    if mutation == 'committed':
        state = runtime._read_json(state_path)
        state['partial_case_results'] = {task['case_order'][0]: {'status': 'PASS'}}
        runtime._write_json(state_path, state)
    elif mutation == 'same_session':
        value = runtime._read_json(receipt)
        value['agent_session_id'] = 'synthetic-old-worker'
        runtime._write_json(receipt, value)
    else:
        value = runtime._read_json(terminal)
        value['agent_session_id'] = 'unrelated-worker'
        runtime._write_json(terminal, value)
    before = {p.relative_to(tmp_path): p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()}
    with pytest.raises(AssertionError):
        runtime.recover_worker_dispatch_files(tmp_path, 'B01', receipt, terminal)
    assert {p.relative_to(tmp_path): p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()} == before
