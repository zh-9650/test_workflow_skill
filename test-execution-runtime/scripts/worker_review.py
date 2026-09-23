import re


MANDATORY = [
    'all_cases_checked',
    'all_expected_checked',
    'execution_method_checked',
    'evidence_binding_checked',
    'failure_classification_checked',
    'file_cleanup_checked',
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


def validate(review, planned_case_ids, results, *, task_id, task_hash,
             worker_session_id, results_sha256):
    _required_text(task_id, 'worker_self_review.task_id')
    _required_sha256(task_hash, 'worker_self_review.task_hash')
    _required_text(worker_session_id, 'worker_self_review.worker_session_id')
    _required_sha256(results_sha256, 'worker_self_review.results_sha256')

    if not isinstance(review, dict):
        fail('worker_self_review', 'object required')
    expected_bindings = {
        'task_id': task_id,
        'input_task_hash': task_hash,
        'agent_session_id': worker_session_id,
        'results_sha256': results_sha256,
    }
    for key, expected in expected_bindings.items():
        if review.get(key) != expected:
            fail(f'worker_self_review.{key}', 'does not match the actual Worker receipt/input')

    if review.get('status') != 'passed':
        fail('worker_self_review.status', 'must be passed')
    if not isinstance(planned_case_ids, list) or not all(isinstance(cid, str) for cid in planned_case_ids):
        fail('worker_self_review.case_order', 'planned Case ID list required')
    if len(planned_case_ids) != len(set(planned_case_ids)):
        fail('worker_self_review.case_order', 'duplicate planned Case IDs are forbidden')
    if not isinstance(results, list):
        fail('worker_self_review.results', 'list required')
    result_ids = [r.get('case_id') if isinstance(r, dict) else None for r in results]
    if len(result_ids) != len(set(result_ids)):
        fail('worker_self_review.results', 'duplicate case_id in results')
    if set(planned_case_ids) != set(result_ids):
        fail('worker_self_review', 'planned/result case set mismatch')
    checked = review.get('checked_case_ids')
    if (not isinstance(checked, list) or len(checked) != len(set(checked))
            or set(checked) != set(planned_case_ids)):
        fail('worker_self_review.checked_case_ids', 'must cover every planned case exactly once')
    checks = review.get('checks')
    if not isinstance(checks, dict):
        fail('worker_self_review.checks', 'object required')
    for key in MANDATORY:
        if checks.get(key) is not True:
            fail(f'worker_self_review.checks.{key}', 'must be true when status=passed')
    if not isinstance(review.get('findings'), list):
        fail('worker_self_review.findings', 'list required')
    return {'ok': True}
