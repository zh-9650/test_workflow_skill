from __future__ import annotations

import hashlib
import json

import pytest

from conftest import load_script


def _bootstrap():
    return load_script(
        "test-project-bootstrap/scripts/bootstrap_project.py",
        "test_project_bootstrap_module",
    )


def _managed_snapshot(project) -> dict[str, str]:
    paths = [
        project / "CLAUDE.md",
        project / ".test-workflow/PROJECT_TESTING_INDEX.md",
        project / ".test-workflow/project-profile.json",
        project / ".claude/agents/test-execution-worker.md",
        project / ".claude/agents/test-result-reviewer.md",
        project / "work/test-automation/package.json",
        project / "work/test-automation/package-lock.json",
    ]
    return {
        p.relative_to(project).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in paths
    }


def test_initial_bootstrap_and_second_run_are_stable(tmp_path) -> None:
    project = tmp_path / "sample-project"
    project.mkdir()
    original = "# 项目自己的说明\n\n构建命令：npm run build。\n"
    (project / "CLAUDE.md").write_text(original, encoding="utf-8")
    (project / "README.md").write_text("# Sample project\n", encoding="utf-8")
    (project / "tests").mkdir()
    (project / "tests/login.spec.ts").write_text("test('login', () => {});\n", encoding="utf-8")
    (project / "e2e").mkdir()
    (project / "e2e/login.spec.ts").write_text("test('e2e', () => {});\n", encoding="utf-8")
    existing_temp = project / "CLAUDE.md.tmp"
    existing_temp.write_text("another owner's temporary file", encoding="utf-8")
    (project / "package.json").write_text(
        json.dumps({"scripts": {"build": "SECRET_TOKEN=private-value tsc -b"}}),
        encoding="utf-8",
    )
    module = _bootstrap()

    first = module.bootstrap(project)
    first_snapshot = _managed_snapshot(project)
    second = module.bootstrap(project)

    assert first["ok"] is True
    assert first["changed"]
    assert second["changed"] == []
    assert _managed_snapshot(project) == first_snapshot
    claude = (project / "CLAUDE.md").read_text(encoding="utf-8")
    assert claude.startswith(original)
    assert claude.count("<!-- TEST-WORKFLOW:START -->") == 1
    assert claude.count("<!-- TEST-WORKFLOW:END -->") == 1
    assert existing_temp.read_text(encoding="utf-8") == "another owner's temporary file"
    index = (project / ".test-workflow/PROJECT_TESTING_INDEX.md").read_text(
        encoding="utf-8"
    )
    assert "npm run build" in index
    assert "tests/login.spec.ts" in index
    assert "e2e/login.spec.ts" in index
    assert "private-value" not in index
    runtime_package = json.loads(
        (project / "work/test-automation/package.json").read_text(encoding="utf-8")
    )
    assert runtime_package["engines"]["node"] == "^22.12.0 || ^24.0.0 || >=26.0.0"


def test_version_drift_refreshes_managed_profile_and_preserves_project_text(
    tmp_path,
) -> None:
    project = tmp_path / "version-drift"
    project.mkdir()
    original = "# 业务说明\n不可删除本段。\n"
    (project / "CLAUDE.md").write_text(original, encoding="utf-8")
    module = _bootstrap()
    module.bootstrap(project)
    profile_path = project / ".test-workflow/project-profile.json"
    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    profile["workflow_version"] = "1.0.0"
    profile_path.write_text(json.dumps(profile), encoding="utf-8")

    check = module.bootstrap(project, check=True)
    refreshed = module.bootstrap(project)
    stable = module.bootstrap(project)

    assert check["ok"] is False
    assert ".test-workflow/project-profile.json" in check["changed"]
    assert ".test-workflow/project-profile.json" in refreshed["changed"]
    assert stable["changed"] == []
    assert (project / "CLAUDE.md").read_text(encoding="utf-8").startswith(original)


def test_duplicate_or_unpaired_markers_stop_before_writing(tmp_path) -> None:
    project = tmp_path / "bad-markers"
    project.mkdir()
    claude = project / "CLAUDE.md"
    claude.write_text("# Existing\n<!-- TEST-WORKFLOW:START -->\n", encoding="utf-8")
    module = _bootstrap()

    with pytest.raises(ValueError, match="markers"):
        module.bootstrap(project)

    assert not (project / ".test-workflow").exists()
    assert claude.read_text(encoding="utf-8").startswith("# Existing")
