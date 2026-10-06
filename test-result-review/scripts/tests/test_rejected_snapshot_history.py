"""File-backed rejection history checks, not actual host acceptance."""
import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'test-execution-runtime/scripts'))
import runtime_orchestrator as runtime

spec = importlib.util.spec_from_file_location('final_rejected_snapshot_test', ROOT / 'test-result-review/scripts/final_review.py')
final = importlib.util.module_from_spec(spec)
spec.loader.exec_module(final)


def check_history(*args):
    return final._validate_reviewed_artifact_history(*args)


def snapshot(tmp_path, omitted_case='C1'):
    task = {'task_id': 'synthetic-history', 'task_hash': 'a' * 64, 'batch_id': 'B01',
            'target_environment': 'local-fixture', 'deployment_version': 'v1',
            'case_order': ['C1', 'C2'], 'cases': [{'case_id': 'C1'}, {'case_id': 'C2'}]}
    results = []
    for cid in task['case_order']:
        for name in ['value.json', 'actor.json']:
            path = tmp_path / f'evidence/B01/{cid}/{name}'
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(cid + name, encoding='utf8')
        results.append({'case_id': cid, 'expected_results': [{'id': 'E', 'evidence_refs': [f'evidence/B01/{cid}/value.json']}],
                        'precondition_evidence_refs': [f'evidence/B01/{cid}/actor.json']})
    runtime._write_json(tmp_path / 'results.json', results)
    runtime._write_json(tmp_path / 'self.json', {'agent_session_id': 'synthetic-worker'})
    frozen = runtime._build_reviewer_task(tmp_path, 'B01', task, 'task.json', 'results.json', 'self.json', results,
                                          {'agent_session_id': 'synthetic-worker'})
    ref = f'evidence/B01/{omitted_case}/actor.json'
    frozen['artifact_sha256'].pop(ref)
    frozen['artifact_snapshot_manifest'].pop(ref)
    frozen['artifact_snapshot_sha256'] = runtime._canonical_sha256(frozen['artifact_snapshot_manifest'])
    return task, results, frozen


def test_rejected_case_history_keeps_integrity_without_claiming_complete_evidence(tmp_path):
    task, results, frozen = snapshot(tmp_path)
    check_history(tmp_path, frozen, task, results,
                                            {'status': 'rework_required', 'retest_case_ids': ['C1']}, runtime)


def test_passed_review_cannot_waive_missing_frozen_input(tmp_path):
    task, results, frozen = snapshot(tmp_path)
    with pytest.raises(AssertionError, match='referenced input'):
        check_history(tmp_path, frozen, task, results,
                                                {'status': 'passed', 'retest_case_ids': []}, runtime)


def test_partial_rejection_cannot_waive_an_accepted_case_input(tmp_path):
    task, results, frozen = snapshot(tmp_path, 'C2')
    with pytest.raises(AssertionError, match='referenced input'):
        check_history(tmp_path, frozen, task, results,
                                                {'status': 'rework_required', 'retest_case_ids': ['C1']}, runtime)


def test_even_rejected_snapshot_bytes_must_remain_immutable(tmp_path):
    task, results, frozen = snapshot(tmp_path)
    entry = frozen['artifact_snapshot_manifest']['evidence/B01/C1/value.json']
    (tmp_path / entry['snapshot_ref']).write_text('tampered', encoding='utf8')
    with pytest.raises(AssertionError, match='missing or changed'):
        check_history(tmp_path, frozen, task, results,
                                                {'status': 'rework_required', 'retest_case_ids': ['C1']}, runtime)


@pytest.mark.parametrize('ids', [[], ['unknown']])
def test_invalid_rejection_scope_cannot_waive_inputs(tmp_path, ids):
    task, results, frozen = snapshot(tmp_path)
    with pytest.raises(AssertionError):
        check_history(tmp_path, frozen, task, results,
                                                {'status': 'rework_required', 'retest_case_ids': ids}, runtime)
