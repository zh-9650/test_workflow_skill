import importlib.util
from pathlib import Path


VALIDATOR = Path(__file__).resolve().parents[1] / "workspace_validate.py"
SPEC = importlib.util.spec_from_file_location("workspace_validate_runtime_results_test", VALIDATOR)
workspace_validate = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(workspace_validate)


def test_workspace_validator_allows_official_runner_results_directory(tmp_path):
    run = tmp_path / "isolated-run"
    (run / "runner-results" / "B01").mkdir(parents=True)
    (run / "runner-results" / "B01" / "vitest-report.json").write_text("{}", encoding="utf-8")

    assert workspace_validate.validate(run) == {"ok": True, "issues": []}
