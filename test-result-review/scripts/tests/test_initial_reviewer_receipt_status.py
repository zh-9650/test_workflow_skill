import importlib.util
from pathlib import Path

import pytest


FINAL_REVIEW = Path(__file__).resolve().parents[1] / "final_review.py"
spec = importlib.util.spec_from_file_location("final_review_initial_receipt_status_test", FINAL_REVIEW)
final_review = importlib.util.module_from_spec(spec)
spec.loader.exec_module(final_review)


def test_first_reviewer_receipt_is_compared_with_first_review_not_retest_aggregate():
    initial_review = {"status": "rework_required", "retest_case_ids": ["TC-API-001"]}
    final_aggregate = {"status": "passed", "findings": ["retest resolved the finding"]}
    state = {
        "reviewer": final_aggregate,
        "review_history": [
            {"type": "initial_or_batch_review", "review": initial_review},
            {"type": "local_retest_review", "reviewer_task_hash": "retest-hash", "review": final_aggregate},
        ],
    }

    selected = final_review._initial_batch_review(state)

    assert selected == initial_review
    assert selected["status"] == "rework_required"


def test_missing_initial_review_is_rejected_when_retest_history_exists():
    state = {
        "reviewer": {"status": "passed"},
        "review_history": [
            {"type": "local_retest_review", "reviewer_task_hash": "retest-hash", "review": {"status": "passed"}}
        ],
        "retest_history": [{"mode": "local_retest"}],
    }

    with pytest.raises(AssertionError, match="exactly one initial Batch Reviewer record"):
        final_review._initial_batch_review(state)


def test_duplicate_initial_reviews_are_rejected():
    state = {
        "review_history": [
            {"type": "initial_or_batch_review", "review": {"status": "passed"}},
            {"type": "initial_or_batch_review", "review": {"status": "rework_required"}},
        ]
    }

    with pytest.raises(AssertionError, match="exactly one initial Batch Reviewer record"):
        final_review._initial_batch_review(state)
