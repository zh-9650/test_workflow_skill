from __future__ import annotations

import hashlib
import json
import os
import subprocess

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


def test_bootstrap_refuses_profile_with_different_owner_marker(tmp_path) -> None:
    project = tmp_path / "foreign-profile-owner"
    project.mkdir()
    module = _bootstrap()
    module.bootstrap(project)
    profile_path = project / ".test-workflow/project-profile.json"
    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    profile["managed_by"] = "another-tool"
    profile_path.write_text(json.dumps(profile), encoding="utf-8")
    before = profile_path.read_bytes()

    with pytest.raises(ValueError, match="unrecognized Bootstrap profile"):
        module.bootstrap(project)

    assert profile_path.read_bytes() == before


def test_bootstrap_refuses_legacy_profile_without_owner_marker(tmp_path) -> None:
    project = tmp_path / "legacy-unmarked-profile"
    project.mkdir()
    module = _bootstrap()
    module.bootstrap(project)
    profile_path = project / ".test-workflow/project-profile.json"
    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    profile.pop("managed_by")
    profile["workflow_version"] = "legacy-version"
    profile_path.write_text(json.dumps(profile), encoding="utf-8")
    before = profile_path.read_bytes()

    with pytest.raises(ValueError, match="unrecognized Bootstrap profile"):
        module.bootstrap(project)

    assert profile_path.read_bytes() == before


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


def test_bootstrap_refuses_to_overwrite_preexisting_project_assets(tmp_path) -> None:
    project = tmp_path / "existing-project-assets"
    project.mkdir()
    claude = project / "CLAUDE.md"
    claude.write_text("# Existing project instructions\n", encoding="utf-8")
    custom_agent = project / ".claude/agents/test-execution-worker.md"
    custom_agent.parent.mkdir(parents=True)
    custom_agent.write_text("# Project-specific Worker\n", encoding="utf-8")
    custom_api_client = project / "work/test-automation/framework/api-client.ts"
    custom_api_client.parent.mkdir(parents=True)
    custom_api_client.write_text("// Project-specific API client\n", encoding="utf-8")

    module = _bootstrap()

    with pytest.raises(ValueError, match="refusing to overwrite"):
        module.bootstrap(project)

    assert claude.read_text(encoding="utf-8") == "# Existing project instructions\n"
    assert custom_agent.read_text(encoding="utf-8") == "# Project-specific Worker\n"
    assert custom_api_client.read_text(encoding="utf-8") == "// Project-specific API client\n"
    assert not (project / ".test-workflow/project-profile.json").exists()


def test_bootstrap_refuses_to_replace_user_modified_managed_asset(tmp_path) -> None:
    project = tmp_path / "modified-managed-asset"
    project.mkdir()
    module = _bootstrap()
    module.bootstrap(project)
    api_client = project / "work/test-automation/framework/api-client.ts"
    original_profile = (project / ".test-workflow/project-profile.json").read_bytes()
    customized = api_client.read_text(encoding="utf-8") + "\n// Local project customization\n"
    api_client.write_text(customized, encoding="utf-8")

    with pytest.raises(ValueError, match="refusing to overwrite"):
        module.bootstrap(project)

    assert api_client.read_text(encoding="utf-8") == customized
    assert (project / ".test-workflow/project-profile.json").read_bytes() == original_profile


def test_bootstrap_preflights_late_asset_conflicts_before_any_write(tmp_path) -> None:
    project = tmp_path / "late-conflict"
    project.mkdir()
    claude = project / "CLAUDE.md"
    claude.write_text("# Existing project instructions\n", encoding="utf-8")
    late_asset = project / "work/test-automation/vitest.config.ts"
    late_asset.parent.mkdir(parents=True)
    late_asset.write_text("// Existing project Vitest config\n", encoding="utf-8")
    module = _bootstrap()

    with pytest.raises(ValueError, match="refusing to overwrite"):
        module.bootstrap(project)

    assert claude.read_text(encoding="utf-8") == "# Existing project instructions\n"
    assert late_asset.read_text(encoding="utf-8") == "// Existing project Vitest config\n"
    assert not (project / ".claude/agents/test-execution-worker.md").exists()
    assert not (project / ".test-workflow/project-profile.json").exists()


@pytest.mark.parametrize("blocked_parent", [".claude", ".test-workflow", "work"])
def test_bootstrap_preflights_non_directory_managed_parents(
    tmp_path, blocked_parent: str
) -> None:
    project = tmp_path / f"blocked-parent-{blocked_parent.replace('.', 'dot-')}"
    project.mkdir()
    claude = project / "CLAUDE.md"
    original_claude = "# Original project instructions\n"
    claude.write_text(original_claude, encoding="utf-8")
    blocker = project / blocked_parent
    blocker.write_text("project-owned file\n", encoding="utf-8")
    module = _bootstrap()

    with pytest.raises(ValueError, match="non-directory parent"):
        module.bootstrap(project)

    assert claude.read_text(encoding="utf-8") == original_claude
    assert blocker.read_text(encoding="utf-8") == "project-owned file\n"
    assert not (project / ".claude/agents/test-execution-worker.md").exists()
    assert not (project / ".test-workflow/project-profile.json").exists()


def test_bootstrap_refuses_to_overwrite_unregistered_project_testing_index(tmp_path) -> None:
    project = tmp_path / "existing-index"
    project.mkdir()
    claude = project / "CLAUDE.md"
    claude.write_text("# Existing project instructions\n", encoding="utf-8")
    index = project / ".test-workflow/PROJECT_TESTING_INDEX.md"
    index.parent.mkdir(parents=True)
    index.write_text("# Project-authored index\n", encoding="utf-8")
    module = _bootstrap()

    with pytest.raises(ValueError, match="refusing to overwrite"):
        module.bootstrap(project)

    assert claude.read_text(encoding="utf-8") == "# Existing project instructions\n"
    assert index.read_text(encoding="utf-8") == "# Project-authored index\n"
    assert not (project / ".claude/agents/test-execution-worker.md").exists()
    assert not (project / ".test-workflow/project-profile.json").exists()


def test_bootstrap_refuses_to_overwrite_unrecognized_project_profile(tmp_path) -> None:
    project = tmp_path / "existing-profile"
    project.mkdir()
    claude = project / "CLAUDE.md"
    claude.write_text("# Existing project instructions\n", encoding="utf-8")
    profile = project / ".test-workflow/project-profile.json"
    profile.parent.mkdir(parents=True)
    profile.write_text('{"owner":"project"}\n', encoding="utf-8")
    module = _bootstrap()

    with pytest.raises(ValueError, match="refusing to overwrite"):
        module.bootstrap(project)

    assert claude.read_text(encoding="utf-8") == "# Existing project instructions\n"
    assert profile.read_text(encoding="utf-8") == '{"owner":"project"}\n'
    assert not (project / ".claude/agents/test-execution-worker.md").exists()
    assert not (project / ".test-workflow/PROJECT_TESTING_INDEX.md").exists()


def test_bootstrap_refuses_claude_symlink_target(tmp_path) -> None:
    project = tmp_path / "claude-symlink"
    project.mkdir()
    instructions = project / "project-instructions.md"
    instructions.write_text("# Existing project instructions\n", encoding="utf-8")
    link = project / "CLAUDE.md"
    try:
        os.symlink(instructions, link)
    except OSError as exc:
        pytest.skip(f"symlink creation is unavailable: {exc}")
    module = _bootstrap()

    with pytest.raises(ValueError, match="symlink|junction"):
        module.bootstrap(project)

    assert link.is_symlink()
    assert instructions.read_text(encoding="utf-8") == "# Existing project instructions\n"


def test_bootstrap_refuses_managed_parent_directory_symlink(tmp_path) -> None:
    project = tmp_path / "parent-symlink"
    project.mkdir()
    target = project / "project-owned"
    target.mkdir()
    link = project / ".test-workflow"
    try:
        os.symlink(target, link, target_is_directory=True)
    except OSError as exc:
        if os.name != "nt":
            pytest.skip(f"directory symlink creation is unavailable: {exc}")
        junction = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(link), str(target)],
            capture_output=True,
            text=True,
            check=False,
        )
        if junction.returncode != 0:
            pytest.skip(f"directory symlink/junction creation is unavailable: {exc}")
    module = _bootstrap()

    with pytest.raises(ValueError, match="symlink|junction"):
        module.bootstrap(project)

    assert link.is_symlink() or link.is_junction()
    assert not (target / "project-profile.json").exists()
    assert not (project / "CLAUDE.md").exists()
