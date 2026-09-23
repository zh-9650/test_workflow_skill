from __future__ import annotations

import copy

import pytest

from conftest import load_script


SHA_A = 'a' * 64
SHA_B = 'b' * 64
SHA_C = 'c' * 64


def _worker_review() -> dict:
    return {
        'task_id': 'B01-task',
        'input_task_hash': SHA_A,
        'agent_session_id': 'worker-session',
        'results_sha256': SHA_B,
        'status': 'passed',
        'checked_case_ids': ['TC-001'],
        'checks': {
            'all_cases_checked': True,
            'all_expected_checked': True,
            'execution_method_checked': True,
            'evidence_binding_checked': True,
            'failure_classification_checked': True,
            'file_cleanup_checked': True,
        },
        'findings': [],
    }


def _worker_args() -> dict:
    return {
        'task_id': 'B01-task',
        'task_hash': SHA_A,
        'worker_session_id': 'worker-session',
        'results_sha256': SHA_B,
    }


def _reviewer_task() -> dict:
    return {
        'task_id': 'B01-review-task',
        'task_hash': SHA_C,
        'worker_session_id': 'worker-session',
        'results_sha256': SHA_B,
        'worker_self_review_sha256': SHA_A,
        'case_order': ['TC-001'],
    }


def _reviewer_review() -> dict:
    return {
        'schema_version': 2,
        'reviewer_task_id': 'B01-review-task',
        'input_task_hash': SHA_C,
        'input_results_sha256': SHA_B,
        'agent_session_id': 'reviewer-session',
        'status': 'passed',
        'findings': [],
        'checked_case_ids': ['TC-001'],
        'retest_case_ids': [],
        'return_stage': None,
        'checks': {
            'completeness_checked': True,
            'method_consistency_checked': True,
            'judgement_checked': True,
            'evidence_checked': True,
            'abnormal_classification_checked': True,
        },
    }


def test_worker_self_review_binds_task_session_and_result_digest() -> None:
    contract = load_script(
        'test-execution-runtime/scripts/worker_review.py', 'agent_worker_review_v2'
    )
    assert contract.validate(
        _worker_review(), ['TC-001'], [{'case_id': 'TC-001'}], **_worker_args()
    ) == {'ok': True}


@pytest.mark.parametrize(
    ('field', 'replacement', 'message'),
    [
        ('task_id', None, 'task_id'),
        ('input_task_hash', SHA_C, 'input_task_hash'),
        ('agent_session_id', 'other-session', 'agent_session_id'),
        ('results_sha256', SHA_C, 'results_sha256'),
    ],
)
def test_worker_self_review_rejects_missing_or_drifted_receipt_fields(
    field: str, replacement: str | None, message: str
) -> None:
    contract = load_script(
        'test-execution-runtime/scripts/worker_review.py', f'agent_worker_review_{field}'
    )
    review = _worker_review()
    if replacement is None:
        review.pop(field)
    else:
        review[field] = replacement
    with pytest.raises(AssertionError, match=message):
        contract.validate(review, ['TC-001'], [{'case_id': 'TC-001'}], **_worker_args())


def test_reviewer_contract_accepts_distinct_receipt_bound_to_review_task() -> None:
    contract = load_script(
        'test-execution-runtime/scripts/reviewer_contract.py', 'agent_reviewer_contract_v2'
    )
    assert contract.validate(
        _reviewer_review(),
        ['TC-001'],
        [{'case_id': 'TC-001', 'status': 'PASS'}],
        reviewer_task=_reviewer_task(),
        worker_session_id='worker-session',
        reviewer_session_id='reviewer-session',
        results_sha256=SHA_B,
    ) == {'ok': True, 'status': 'passed'}


def test_reviewer_contract_rejects_missing_binding_fields() -> None:
    contract = load_script(
        'test-execution-runtime/scripts/reviewer_contract.py', 'agent_reviewer_missing_fields'
    )
    review = _reviewer_review()
    for field in ('reviewer_task_id', 'input_task_hash', 'input_results_sha256', 'agent_session_id'):
        candidate = copy.deepcopy(review)
        candidate.pop(field)
        with pytest.raises(AssertionError, match=field):
            contract.validate(
                candidate, ['TC-001'], reviewer_task=_reviewer_task(),
                worker_session_id='worker-session', reviewer_session_id='reviewer-session',
                results_sha256=SHA_B,
            )


def test_reviewer_contract_rejects_same_worker_session() -> None:
    contract = load_script(
        'test-execution-runtime/scripts/reviewer_contract.py', 'agent_reviewer_same_session'
    )
    review = _reviewer_review()
    review['agent_session_id'] = 'worker-session'
    with pytest.raises(AssertionError, match='different session'):
        contract.validate(
            review, ['TC-001'], reviewer_task=_reviewer_task(),
            worker_session_id='worker-session', reviewer_session_id='worker-session',
            results_sha256=SHA_B,
        )


@pytest.mark.parametrize(
    ('field', 'value'),
    [
        ('task_hash', SHA_A),
        ('results_sha256', SHA_C),
    ],
)
def test_reviewer_contract_rejects_reviewer_task_hash_drift(field: str, value: str) -> None:
    contract = load_script(
        'test-execution-runtime/scripts/reviewer_contract.py', f'agent_reviewer_task_hash_{field}'
    )
    reviewer_task = _reviewer_task()
    reviewer_task[field] = value
    with pytest.raises(AssertionError, match='input|results_sha256'):
        contract.validate(
            _reviewer_review(), ['TC-001'], reviewer_task=reviewer_task,
            worker_session_id='worker-session', reviewer_session_id='reviewer-session',
            results_sha256=SHA_B,
        )


def test_reviewer_contract_rejects_review_input_digest_drift() -> None:
    contract = load_script(
        'test-execution-runtime/scripts/reviewer_contract.py', 'agent_reviewer_input_hash_drift'
    )
    review = _reviewer_review()
    review['input_results_sha256'] = SHA_C
    with pytest.raises(AssertionError, match='input_results_sha256'):
        contract.validate(
            review, ['TC-001'], reviewer_task=_reviewer_task(),
            worker_session_id='worker-session', reviewer_session_id='reviewer-session',
            results_sha256=SHA_B,
        )
