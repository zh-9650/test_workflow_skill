import re
import runpy
from pathlib import Path


EXECUTION_SCHEMA_VERSION = runpy.run_path(
    str(Path(__file__).resolve().parents[2] / 'clarify-before-testing/scripts/workflow_versions.py')
)['EXECUTION_SCHEMA_VERSION']

VALID = {'passed', 'rework_required', 'return_upstream'}
RETURN = {None, 'case_design', 'execution_planning', 'data_readiness'}
MANDATORY = [
    'completeness_checked',
    'method_consistency_checked',
    'judgement_checked',
    'evidence_checked',
    'abnormal_classification_checked',
]
_SHA256 = re.compile(r'^[0-9a-f]{64}$')


def fail(path, msg):
    raise AssertionError(f'{path}: {msg}')


def _required_text(value, path):
    if not isinstance(value, str) or not value.strip():
        fail(path, 'non-empty string required')


def _required_sha256(value, path):
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        fail(path, '64-character lowercase SHA-256 required')


def validate(review, planned_case_ids, case_results=None, *, reviewer_task,
             worker_session_id, reviewer_session_id, results_sha256):
    if not isinstance(review, dict):
        fail('reviewer', 'object required')
    if not isinstance(reviewer_task, dict):
        fail('reviewer_task', 'object required')

    schema_version = review.get('schema_version')
    if type(schema_version) is not int or schema_version != EXECUTION_SCHEMA_VERSION:
        fail('reviewer.schema_version', f'must be integer {EXECUTION_SCHEMA_VERSION}')

    for name, value in (
        ('reviewer_task.task_id', reviewer_task.get('task_id')),
        ('reviewer_task.worker_session_id', reviewer_task.get('worker_session_id')),
        ('worker_session_id', worker_session_id),
        ('reviewer_session_id', reviewer_session_id),
    ):
        _required_text(value, name)
    for name in ('task_hash', 'results_sha256', 'worker_self_review_sha256'):
        _required_sha256(reviewer_task.get(name), f'reviewer_task.{name}')
    _required_sha256(results_sha256, 'results_sha256')

    task_case_order = reviewer_task.get('case_order')
    if (not isinstance(task_case_order, list)
            or not all(isinstance(case_id, str) for case_id in task_case_order)
            or len(task_case_order) != len(set(task_case_order))):
        fail('reviewer_task.case_order', 'unique Case ID list required')
    if (not isinstance(planned_case_ids, list)
            or len(planned_case_ids) != len(set(planned_case_ids))
            or task_case_order != planned_case_ids):
        fail('reviewer_task.case_order', 'must match planned Case order exactly')

    if reviewer_task['worker_session_id'] != worker_session_id:
        fail('reviewer_task.worker_session_id', 'does not match the actual Worker receipt')
    if reviewer_task['results_sha256'] != results_sha256:
        fail('reviewer_task.results_sha256', 'does not match the actual results input')
    if reviewer_session_id == worker_session_id:
        fail('reviewer_session_id', 'Reviewer must run in a different session from Worker')

    bindings = {
        'reviewer_task_id': reviewer_task['task_id'],
        'input_task_hash': reviewer_task['task_hash'],
        'input_results_sha256': results_sha256,
        'agent_session_id': reviewer_session_id,
    }
    for key, expected in bindings.items():
        if review.get(key) != expected:
            fail(f'reviewer.{key}', 'does not match the actual Reviewer task/input/receipt')

    st = review.get('status')
    if st not in VALID:
        fail('reviewer.status', f'must be one of {sorted(VALID)}')
    if not isinstance(review.get('findings'), list):
        fail('reviewer.findings', 'list required')
    checked = review.get('checked_case_ids', [])
    if not isinstance(checked, list) or set(checked) != set(planned_case_ids) or len(checked) != len(planned_case_ids):
        fail('reviewer.checked_case_ids', 'must cover every Case in the reviewer task')
    retest = review.get('retest_case_ids', [])
    if not isinstance(retest, list):
        fail('reviewer.retest_case_ids', 'list required')
    if len(retest) != len(set(retest)):
        fail('reviewer.retest_case_ids', 'duplicate case ids are forbidden')
    unknown = set(retest) - set(planned_case_ids)
    if unknown:
        fail('reviewer.retest_case_ids', f'unknown cases {sorted(unknown)}')
    return_stage = review.get('return_stage')
    if return_stage not in RETURN:
        fail('reviewer.return_stage', f'invalid {return_stage}')
    checks = review.get('checks')
    if not isinstance(checks, dict):
        fail('reviewer.checks', 'object required')
    for key in MANDATORY:
        if key not in checks or not isinstance(checks.get(key), bool):
            fail(f'reviewer.checks.{key}', 'boolean check result required')

    result_by = {
        result.get('case_id'): result
        for result in (case_results or [])
        if isinstance(result, dict)
    }
    needs_review = sorted(
        case_id for case_id in planned_case_ids
        if result_by.get(case_id, {}).get('status') == 'NEEDS_REVIEW'
    )
    if st == 'passed':
        for key in MANDATORY:
            if checks.get(key) is not True:
                fail(f'reviewer.checks.{key}', 'must be true when status=passed')
        if retest or return_stage is not None:
            fail('reviewer', 'passed cannot request retest or upstream return')
        if needs_review:
            fail('reviewer.status', f'cannot pass while NEEDS_REVIEW remains: {needs_review}')
    if st == 'rework_required':
        for key in MANDATORY:
            if checks.get(key) is not True:
                fail(f'reviewer.checks.{key}', 'must be true when requesting local rework')
        if not retest:
            fail('reviewer.retest_case_ids', 'required for rework_required')
        if return_stage is not None:
            fail('reviewer.return_stage', 'must be null for local rework')
    if st == 'return_upstream':
        if return_stage is None:
            fail('reviewer.return_stage', 'required for return_upstream')
        if not review.get('findings'):
            fail('reviewer.findings', 'return_upstream needs findings')
    return {'ok': True, 'status': st}
