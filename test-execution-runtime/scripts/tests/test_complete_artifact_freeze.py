"""Synthetic file-backed snapshot coverage; not host dispatch acceptance."""
import sys
from copy import deepcopy
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import runtime_orchestrator as runtime


def setup(tmp_path):
    task = {'task_id': 'synthetic-freeze', 'task_hash': 'a' * 64, 'batch_id': 'B01',
            'target_environment': 'local-fixture', 'deployment_version': 'v1',
            'case_order': ['C1'], 'cases': [{'case_id': 'C1'}]}
    result = {'case_id': 'C1',
              'expected_results': [{'id': 'E1', 'evidence_refs': ['evidence/B01/C1/value.json']}],
              'precondition_evidence_refs': ['evidence/B01/C1/actor.json'],
              'script_basis_ref': 'internal/execution/basis.md',
              'automation_run': {'script_ref': 'scripts/api/B01/C1.test.ts',
                                 'official_run': {'report_ref': 'evidence/B01/C1/report.json',
                                                  'runner_results_ref': 'runner-results/B01/C1/a/report.json'},
                                 'debug_attempts': [{'diagnosis_ref': 'evidence/B01/C1/debug/a/diagnosis.json',
                                                     'listener_observation_ref': 'evidence/B01/C1/debug/a/listener.json'}]}}
    refs = ['evidence/B01/C1/value.json', 'evidence/B01/C1/actor.json',
            'internal/execution/basis.md', 'scripts/api/B01/C1.test.ts',
            'evidence/B01/C1/report.json', 'runner-results/B01/C1/a/report.json',
            'evidence/B01/C1/debug/a/diagnosis.json', 'evidence/B01/C1/debug/a/listener.json',
            'evidence/B01/C1/debug/a/failed-script.test.ts', 'evidence/B01/C1/debug/a/failed-report.json']
    for ref in refs:
        path = tmp_path / ref
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(ref, encoding='utf8')
    runtime._write_json(tmp_path / 'results.json', [result])
    runtime._write_json(tmp_path / 'self.json', {'agent_session_id': 'synthetic-worker'})
    return task, result, refs


def test_freeze_includes_preconditions_basis_and_all_case_diagnostics(tmp_path):
    task, result, refs = setup(tmp_path)
    manifest = runtime._case_artifact_manifest(tmp_path, task, [result])
    assert set(refs) <= set(manifest)
    snapshot = runtime._snapshot_case_artifacts(tmp_path, task, [result])
    for ref in refs:
        assert (tmp_path / snapshot[ref]['snapshot_ref']).read_bytes() == (tmp_path / ref).read_bytes()


@pytest.mark.parametrize('ref', ['precondition', 'basis', 'diagnosis'])
def test_freeze_rejects_missing_referenced_supporting_input(tmp_path, ref):
    task, result, refs = setup(tmp_path)
    missing = {'precondition': refs[1], 'basis': refs[2], 'diagnosis': refs[6]}[ref]
    (tmp_path / missing).unlink()
    with pytest.raises(AssertionError, match='missing referenced artifact'):
        runtime._case_artifact_manifest(tmp_path, task, [result])
    assert not (tmp_path / 'internal/execution/snapshots').exists()


def test_frozen_validation_rejects_omitted_required_input_even_if_manifest_rehashed(tmp_path):
    task, result, refs = setup(tmp_path)
    reviewer_task = runtime._build_reviewer_task(tmp_path, 'B01', task, 'task.json',
                                                'results.json', 'self.json', [result],
                                                {'agent_session_id': 'synthetic-worker'})
    modified = deepcopy(reviewer_task)
    omitted = refs[1]
    modified['artifact_sha256'].pop(omitted, None)
    modified['artifact_snapshot_manifest'].pop(omitted, None)
    modified['artifact_snapshot_sha256'] = runtime._canonical_sha256(modified['artifact_snapshot_manifest'])
    with pytest.raises(AssertionError, match='referenced input'):
        runtime._validate_frozen_artifacts(tmp_path, modified, task, [result])


def test_later_attempt_file_does_not_invalidate_historical_snapshot(tmp_path):
    task, result, refs = setup(tmp_path)
    reviewer_task = runtime._build_reviewer_task(tmp_path, 'B01', task, 'task.json',
                                                'results.json', 'self.json', [result],
                                                {'agent_session_id': 'synthetic-worker'})
    later = tmp_path / 'evidence/B01/C1/debug/later/new.txt'
    later.parent.mkdir(parents=True)
    later.write_text('later attempt must not be required by old snapshot', encoding='utf8')
    runtime._validate_frozen_artifacts(tmp_path, reviewer_task, task, [result])
