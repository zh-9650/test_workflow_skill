import hashlib
import os
import json
import subprocess
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
SCOPE_MODULE = REPO_ROOT / "test-project-bootstrap" / "assets" / "typescript-runtime" / "run-scope.mjs"
NODE_EVAL = """
import { pathToFileURL } from 'node:url';
const { resolveApiScriptScope, resolveUiScriptScope } = await import(pathToFileURL(process.env.RUN_SCOPE_MODULE));
const driver = process.env.TEST_DRIVER ?? 'api';
if (driver === 'ui') console.log(JSON.stringify(resolveUiScriptScope(process.env.TEST_AUTOMATION_DIR, process.env, { prepareAttempt: true })));
else console.log(JSON.stringify(resolveApiScriptScope(process.env.TEST_AUTOMATION_DIR, process.env, { prepareAttempt: true })));
"""


def _invoke_scope(
    tmp_path,
    *,
    run_dir=None,
    batch_id=None,
    script_target=None,
    driver="api",
    results_dir=None,
    case_id=None,
    task_case_id=None,
    task_script_target=None,
    task_hash_override=None,
    task_root=None,
    receipt_session_override=None,
):
    automation_dir = tmp_path / "project" / "work" / "test-automation"
    automation_dir.mkdir(parents=True, exist_ok=True)
    (automation_dir.parent / "test-runs").mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env.pop("TEST_RUN_DIR", None)
    env.pop("TEST_BATCH_ID", None)
    env.pop("TEST_SCRIPT_TARGET", None)
    env.pop("TEST_CASE_ID", None)
    env.pop("TEST_RESULTS_DIR", None)
    env.pop("TEST_ATTEMPT_ID", None)
    env.pop("TEST_TASK_ID", None)
    env.pop("TEST_TASK_HASH", None)
    env.pop("TEST_WORKER_SESSION_ID", None)
    env.pop("TEST_API_BASE_URL", None)
    env.pop("TEST_DRIVER", None)
    env.update(
        {
            "RUN_SCOPE_MODULE": str(SCOPE_MODULE),
            "TEST_AUTOMATION_DIR": str(automation_dir),
        }
    )
    if run_dir is not None:
        env["TEST_RUN_DIR"] = str(run_dir)
    if batch_id is not None:
        env["TEST_BATCH_ID"] = batch_id
    if script_target is not None:
        env["TEST_SCRIPT_TARGET"] = script_target
        case_id = case_id or Path(script_target).name.removesuffix(".test.ts").removesuffix(".spec.ts")
        env["TEST_CASE_ID"] = case_id
        env["TEST_ATTEMPT_ID"] = "attempt-001"
        env["TEST_RESULTS_DIR"] = str(results_dir or (run_dir / "runner-results" / batch_id / case_id / "attempt-001"))
        task_root = task_root or run_dir
        task_path = task_root / "internal" / "execution" / "tasks" / f"{batch_id}-task.json"
        task_path.parent.mkdir(parents=True, exist_ok=True)
        task = {
            "task_id": "task-scope-test-001",
            "batch_id": batch_id,
            "cases": [
                {
                    "case_id": task_case_id or case_id,
                    "title": "中文 Smoke Case",
                    "automation": {"script_target": task_script_target or script_target},
                }
            ],
        }
        canonical_task = json.dumps(task, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        task_hash = task_hash_override or hashlib.sha256(canonical_task.encode("utf-8")).hexdigest()
        task["task_hash"] = task_hash
        task_path.write_text(json.dumps(task), encoding="utf-8")
        env["TEST_TASK_ID"] = task["task_id"]
        env["TEST_TASK_HASH"] = task_hash
        env["TEST_WORKER_SESSION_ID"] = receipt_session_override or "worker-scope-test-001"
        env["TEST_API_BASE_URL"] = "http://127.0.0.1:44174"
        receipt_ref = f"internal/execution/dispatch/{batch_id}-worker-receipt.json"
        receipt_path = run_dir / receipt_ref
        receipt_path.parent.mkdir(parents=True, exist_ok=True)
        context_path = run_dir / "internal" / "execution" / "execution-context.yaml"
        context_path.parent.mkdir(parents=True, exist_ok=True)
        context_path.write_text(json.dumps({"environment_ready": True, "api_base_url": "http://127.0.0.1:44174"}), encoding="utf-8")
        receipt = {
            "agent_role": "execution_worker",
            "receipt_status": "dispatched",
            "accepted_at": "2026-09-25T00:00:00Z",
            "agent_session_id": receipt_session_override or "worker-scope-test-001",
            "task_id": task["task_id"],
            "task_hash": task_hash,
            "host_dispatch_ref": "test-subagent-dispatch-001",
            "dispatch_source": "codex_subagent_tool",
        }
        receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
        state_path = run_dir / "internal" / "execution" / "runtime-state" / f"{batch_id}-state.json"
        state_path.parent.mkdir(parents=True, exist_ok=True)
        runtime_state = {
            "batch_id": batch_id,
            "status": "running",
            "task_ref": f"internal/execution/tasks/{batch_id}-task.json",
            "current_case": case_id,
            "current_worker": receipt["agent_session_id"],
            "worker_dispatch_receipt": receipt,
            "worker_receipt_ref": receipt_ref,
        }
        state_path.write_text(json.dumps(runtime_state), encoding="utf-8")
        if task_root != run_dir:
            try:
                task_link = run_dir / "internal" / "execution" / "tasks"
                task_link.parent.mkdir(parents=True, exist_ok=True)
                task_link.symlink_to(task_root / "internal" / "execution" / "tasks", target_is_directory=True)
            except OSError as exc:
                pytest.skip(f"Windows symlink privilege unavailable: {exc}")
    env["TEST_DRIVER"] = driver
    return subprocess.run(
        ["node", "--input-type=module", "-e", NODE_EVAL],
        cwd=automation_dir,
        env=env,
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=False,
    )


def test_vitest_scope_rejects_missing_run_batch_or_script_target(tmp_path):
    result = _invoke_scope(tmp_path)

    assert result.returncode != 0
    assert "TEST_RUN_DIR" in result.stderr


def test_vitest_scope_only_includes_the_exact_script_for_one_run_and_batch(tmp_path):
    test_runs = tmp_path / "project" / "work" / "test-runs"
    run_dir = test_runs / "run-2026-09"
    target = run_dir / "scripts" / "api" / "B01" / "TC-001.test.ts"
    target.parent.mkdir(parents=True)
    target.write_text("export {};\n", encoding="utf-8")
    (test_runs / "older-run" / "scripts" / "api" / "B01" / "old.test.ts").parent.mkdir(parents=True)
    (test_runs / "older-run" / "scripts" / "api" / "B01" / "old.test.ts").write_text("export {};\n", encoding="utf-8")
    (run_dir / "scripts" / "api" / "B02").mkdir(parents=True)
    (run_dir / "scripts" / "api" / "B02" / "other-batch.test.ts").write_text("export {};\n", encoding="utf-8")

    result = _invoke_scope(
        tmp_path,
        run_dir=run_dir,
        batch_id="B01",
        script_target="scripts/api/B01/TC-001.test.ts",
    )

    assert result.returncode == 0, result.stderr
    scope = json.loads(result.stdout)
    assert scope["include"] == "../test-runs/run-2026-09/scripts/api/B01/TC-001.test.ts"
    assert "older-run" not in scope["include"]
    assert "B02" not in scope["include"]
    assert Path(scope["resultsDir"]) == run_dir / "runner-results" / "B01" / "TC-001" / "attempt-001"


def test_vitest_scope_uses_frozen_case_id_when_script_name_has_a_descriptive_suffix(tmp_path):
    run_dir = tmp_path / "project" / "work" / "test-runs" / "run-2026-09"
    target = run_dir / "scripts" / "api" / "B01" / "TC-API-001-health.test.ts"
    target.parent.mkdir(parents=True)
    target.write_text("export {};\n", encoding="utf-8")

    result = _invoke_scope(
        tmp_path,
        run_dir=run_dir,
        batch_id="B01",
        script_target="scripts/api/B01/TC-API-001-health.test.ts",
        case_id="TC-API-001",
    )

    assert result.returncode == 0, result.stderr
    scope = json.loads(result.stdout)
    assert Path(scope["resultsDir"]) == run_dir / "runner-results" / "B01" / "TC-API-001" / "attempt-001"


def test_scope_rejects_case_id_not_bound_to_the_frozen_task_script(tmp_path):
    run_dir = tmp_path / "project" / "work" / "test-runs" / "run-2026-09"
    target = run_dir / "scripts" / "api" / "B01" / "TC-001.test.ts"
    target.parent.mkdir(parents=True)
    target.write_text("export {};\n", encoding="utf-8")

    result = _invoke_scope(
        tmp_path,
        run_dir=run_dir,
        batch_id="B01",
        script_target="scripts/api/B01/TC-001.test.ts",
        case_id="TC-OTHER",
        task_case_id="TC-001",
    )

    assert result.returncode != 0
    assert "frozen Batch task" in result.stderr


def test_scope_rejects_task_whose_frozen_hash_does_not_match_its_payload(tmp_path):
    run_dir = tmp_path / "project" / "work" / "test-runs" / "run-2026-09"
    target = run_dir / "scripts" / "api" / "B01" / "TC-001.test.ts"
    target.parent.mkdir(parents=True)
    target.write_text("export {};\n", encoding="utf-8")

    result = _invoke_scope(
        tmp_path,
        run_dir=run_dir,
        batch_id="B01",
        script_target="scripts/api/B01/TC-001.test.ts",
        task_hash_override="0" * 64,
    )

    assert result.returncode != 0
    assert "task_hash" in result.stderr


def test_scope_rejects_frozen_task_loaded_through_a_symlinked_parent(tmp_path):
    run_dir = tmp_path / "project" / "work" / "test-runs" / "run-2026-09"
    target = run_dir / "scripts" / "api" / "B01" / "TC-001.test.ts"
    target.parent.mkdir(parents=True)
    target.write_text("export {};\n", encoding="utf-8")

    result = _invoke_scope(
        tmp_path,
        run_dir=run_dir,
        batch_id="B01",
        script_target="scripts/api/B01/TC-001.test.ts",
        task_root=tmp_path / "outside-run",
    )

    assert result.returncode != 0
    assert "without symbolic links" in result.stderr


def test_scope_rejects_glob_metacharacters_in_script_filenames(tmp_path):
    run_dir = tmp_path / "project" / "work" / "test-runs" / "run-2026-09"
    target = run_dir / "scripts" / "api" / "B01" / "TC-001[1].test.ts"
    target.parent.mkdir(parents=True)
    target.write_text("export {};\n", encoding="utf-8")

    result = _invoke_scope(
        tmp_path,
        run_dir=run_dir,
        batch_id="B01",
        script_target="scripts/api/B01/TC-001[1].test.ts",
        case_id="TC-001",
    )

    assert result.returncode != 0
    assert "glob-safe" in result.stderr


def test_vitest_scope_rejects_script_outside_current_batch(tmp_path):
    run_dir = tmp_path / "project" / "work" / "test-runs" / "run-2026-09"
    target = run_dir / "scripts" / "api" / "B02" / "TC-002.test.ts"
    target.parent.mkdir(parents=True)
    target.write_text("export {};\n", encoding="utf-8")

    result = _invoke_scope(
        tmp_path,
        run_dir=run_dir,
        batch_id="B01",
        script_target="scripts/api/B02/TC-002.test.ts",
    )

    assert result.returncode != 0
    assert "current Batch" in result.stderr


def test_vitest_scope_rejects_paths_outside_test_runs(tmp_path):
    outside_run = tmp_path / "project" / "external-run"
    outside_run.mkdir(parents=True)

    result = _invoke_scope(
        tmp_path,
        run_dir=outside_run,
        batch_id="B01",
        script_target="scripts/api/B01/TC-001.test.ts",
    )

    assert result.returncode != 0
    assert "test-runs" in result.stderr


def test_playwright_scope_targets_only_the_current_run_batch_and_case(tmp_path):
    run_dir = tmp_path / "project" / "work" / "test-runs" / "run-2026-09"
    target = run_dir / "scripts" / "ui" / "B01" / "TC-UI-001.spec.ts"
    target.parent.mkdir(parents=True)
    target.write_text("export {};\n", encoding="utf-8")
    (run_dir / "scripts" / "ui" / "B02").mkdir(parents=True)
    (run_dir / "scripts" / "ui" / "B02" / "other.spec.ts").write_text("export {};\n", encoding="utf-8")

    result = _invoke_scope(
        tmp_path,
        run_dir=run_dir,
        batch_id="B01",
        script_target="scripts/ui/B01/TC-UI-001.spec.ts",
        driver="ui",
    )

    assert result.returncode == 0, result.stderr
    scope = json.loads(result.stdout)
    assert Path(scope["testDir"]) == target.parent
    assert scope["testMatch"] == "TC-UI-001.spec.ts"
    assert Path(scope["resultsDir"]) == run_dir / "runner-results" / "B01" / "TC-UI-001" / "attempt-001"


def test_playwright_scope_rejects_api_target(tmp_path):
    run_dir = tmp_path / "project" / "work" / "test-runs" / "run-2026-09"
    target = run_dir / "scripts" / "api" / "B01" / "TC-001.test.ts"
    target.parent.mkdir(parents=True)
    target.write_text("export {};\n", encoding="utf-8")
    result = _invoke_scope(
        tmp_path,
        run_dir=run_dir,
        batch_id="B01",
        script_target="scripts/api/B01/TC-001.test.ts",
        driver="ui",
    )

    assert result.returncode != 0


def test_vitest_scope_rejects_results_directory_outside_case(tmp_path):
    run_dir = tmp_path / "project" / "work" / "test-runs" / "run-2026-09"
    target = run_dir / "scripts" / "api" / "B01" / "TC-001.test.ts"
    target.parent.mkdir(parents=True)
    target.write_text("export {};\n", encoding="utf-8")

    result = _invoke_scope(
        tmp_path,
        run_dir=run_dir,
        batch_id="B01",
        script_target="scripts/api/B01/TC-001.test.ts",
        results_dir=tmp_path / "elsewhere",
    )

    assert result.returncode != 0
    assert "dedicated runner-results" in result.stderr


def test_scope_rejects_glob_characters_in_run_and_case_identifiers(tmp_path):
    run_dir = tmp_path / "project" / "work" / "test-runs" / "RUN-[12]"
    target = run_dir / "scripts" / "api" / "B01" / "TC-API-[12].test.ts"
    target.parent.mkdir(parents=True)
    target.write_text("export {};\n", encoding="utf-8")

    result = _invoke_scope(
        tmp_path,
        run_dir=run_dir,
        batch_id="B01",
        script_target="scripts/api/B01/TC-API-[12].test.ts",
    )

    assert result.returncode != 0
    assert "glob-safe" in result.stderr


def test_scope_rejects_dot_segments_as_case_identifiers(tmp_path):
    run_dir = tmp_path / "project" / "work" / "test-runs" / "run-2026-09"
    target = run_dir / "scripts" / "api" / "B01" / "....test.ts"
    target.parent.mkdir(parents=True)
    target.write_text("export {};\n", encoding="utf-8")

    result = _invoke_scope(
        tmp_path,
        run_dir=run_dir,
        batch_id="B01",
        script_target="scripts/api/B01/....test.ts",
    )

    assert result.returncode != 0
    assert "TEST_CASE_ID is invalid" in result.stderr


def test_scope_rejects_reused_attempt_output_directory(tmp_path):
    run_dir = tmp_path / "project" / "work" / "test-runs" / "run-2026-09"
    target = run_dir / "scripts" / "api" / "B01" / "TC-001.test.ts"
    target.parent.mkdir(parents=True)
    target.write_text("export {};\n", encoding="utf-8")
    attempt_dir = run_dir / "runner-results" / "B01" / "TC-001" / "attempt-001"
    attempt_dir.mkdir(parents=True)

    result = _invoke_scope(
        tmp_path,
        run_dir=run_dir,
        batch_id="B01",
        script_target="scripts/api/B01/TC-001.test.ts",
    )

    assert result.returncode != 0
    assert "never overwrite evidence" in result.stderr


def test_vitest_scope_rejects_cross_batch_script_symlink(tmp_path):
    run_dir = tmp_path / "project" / "work" / "test-runs" / "run-2026-09"
    batch_one = run_dir / "scripts" / "api" / "B01"
    batch_two = run_dir / "scripts" / "api" / "B02"
    batch_one.mkdir(parents=True)
    batch_two.mkdir(parents=True)
    foreign_script = batch_two / "foreign.test.ts"
    foreign_script.write_text("export {};\n", encoding="utf-8")
    target = batch_one / "TC-001.test.ts"
    try:
        target.symlink_to(foreign_script)
    except OSError as exc:
        pytest.skip(f"Windows symlink privilege unavailable: {exc}")

    result = _invoke_scope(
        tmp_path,
        run_dir=run_dir,
        batch_id="B01",
        script_target="scripts/api/B01/TC-001.test.ts",
    )

    assert result.returncode != 0
    assert "symbolic link" in result.stderr
