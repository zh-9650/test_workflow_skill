import importlib.util
import json
from pathlib import Path


FINAL_REVIEW = Path(__file__).resolve().parents[1] / "final_review.py"
spec = importlib.util.spec_from_file_location("final_review_product_regression_test", FINAL_REVIEW)
final_review = importlib.util.module_from_spec(spec)
spec.loader.exec_module(final_review)


def test_product_regression_review_does_not_replace_local_retest_aggregate(tmp_path):
    reviewer_task = tmp_path / "local-reviewer-task.json"
    reviewer_task.write_text(json.dumps({"task_hash": "local-task-hash"}), encoding="utf-8")
    local_review = {"status": "passed", "findings": ["ordinary local Retest"]}
    product_review = {"status": "passed", "findings": ["product Regression"]}
    run_state = {
        "review_history": [
            {"type": "initial_or_batch_review", "review": {"status": "passed", "findings": ["initial"]}},
            {"type": "local_retest_review", "reviewer_task_hash": "local-task-hash", "review": local_review},
            {"type": "local_retest_review", "reviewer_task_hash": "product-task-hash", "review": product_review},
        ],
        "retest_history": [
            {
                "mode": "local_retest",
                "reviewer_task_ref": str(reviewer_task),
                "review": local_review,
            },
            {
                "mode": "product_regression",
                "reviewer_task_ref": "must-not-be-loaded-for-local-aggregate.json",
                "review": product_review,
            },
        ],
    }

    result = final_review._latest_accepted_local_retest_review(tmp_path, "B01", run_state)

    assert result == local_review


def test_product_regression_only_returns_no_local_retest_review():
    run_state = {
        "review_history": [
            {"type": "local_retest_review", "reviewer_task_hash": "product-task-hash", "review": {"status": "passed"}}
        ],
        "retest_history": [{"mode": "product_regression", "reviewer_task_ref": "not-loaded.json"}],
    }

    assert final_review._latest_accepted_local_retest_review(Path("."), "B01", run_state) is None
