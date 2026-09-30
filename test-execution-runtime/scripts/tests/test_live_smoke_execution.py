"""Isolated live API/UI runner smoke, NOT real host Worker/Reviewer forward acceptance.

Verifies REAL execution of TypeScript + Vitest (API) and TypeScript + Playwright Test (UI),
including real pre-flight healthcheck, real browser launch, real screenshot (.png),
and real recording (.webm), with no mocked runner results. Dispatch receipt is synthetic.
"""

import hashlib
import json
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
import importlib.util
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
FRESH_PROJECT = REPO_ROOT / ".phase6-forward" / "fresh-project"
AUTOMATION_DIR = FRESH_PROJECT / "work" / "test-automation"
SERVER_SCRIPT = FRESH_PROJECT / "app" / "server.mjs"

_ctl_path = REPO_ROOT / "test-execution-runtime" / "scripts" / "execution_control.py"
_ctl_spec = importlib.util.spec_from_file_location("execution_control", _ctl_path)
_ctl_mod = importlib.util.module_from_spec(_ctl_spec)
_ctl_spec.loader.exec_module(_ctl_mod)


def _is_server_listening(host="127.0.0.1", port=4173):
    sock = socket.socket()
    try:
        sock.settimeout(0.5)
        res = sock.connect_ex((host, port))
        return res == 0
    finally:
        sock.close()


def _ensure_server_running():
    if _is_server_listening():
        return None
    proc = subprocess.Popen([sys.executable.replace("python.exe", "node.exe") if "node.exe" in sys.executable else "node", str(SERVER_SCRIPT)], cwd=str(FRESH_PROJECT))
    for _ in range(30):
        if _is_server_listening():
            break
        time.sleep(0.1)
    return proc


def _preflight_healthcheck(base_url="http://127.0.0.1:4173"):
    # 1. Check API endpoint
    req = urllib.request.Request(f"{base_url}/api/health", headers={"User-Agent": "PreflightCheck"})
    with urllib.request.urlopen(req, timeout=5) as resp:
        assert resp.status == 200
        data = json.loads(resp.read().decode("utf-8"))
        assert data.get("status") == "ready"

    # 2. Check UI page
    req_ui = urllib.request.Request(f"{base_url}/?object=TC-SMOKE", headers={"User-Agent": "PreflightCheck"})
    with urllib.request.urlopen(req_ui, timeout=5) as resp_ui:
        assert resp_ui.status == 200
        html = resp_ui.read().decode("utf-8")
        assert "本地测试页面" in html
        assert "执行本地操作" in html


def _canonical(data):
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sha256(data):
    return hashlib.sha256(data).hexdigest()


def test_live_smoke_api_and_ui():
    server_proc = _ensure_server_running()
    try:
        # Pre-flight healthcheck
        _preflight_healthcheck("http://127.0.0.1:4173")

        # Setup isolated unique temporary Run directory
        import uuid
        run_id = f"RUN-SMOKE-{uuid.uuid4().hex[:12]}"
        run_dir = FRESH_PROJECT / "work" / "test-runs" / run_id
        assert not run_dir.exists(), 'Never overwrite an existing smoke Run'

        # Create Run structure
        for d in [
            "internal/execution/tasks",
            "internal/execution/dispatch",
            "internal/execution/runtime-state",
            "internal/execution/results",
            "scripts/api/B01",
            "scripts/ui/B01",
            "evidence/B01/TC-API-001/api",
            "evidence/B01/TC-UI-002/ui",
        ]:
            (run_dir / d).mkdir(parents=True, exist_ok=True)

        # Execution context
        context_file = run_dir / "internal/execution/execution-context.yaml"
        context_file.write_text(
            json.dumps({
                "environment_ready": True,
                "api_base_url": "http://127.0.0.1:4173",
                "web_base_url": "http://127.0.0.1:4173",
            }),
            encoding="utf-8",
        )

        # Write API test script
        api_script = run_dir / "scripts/api/B01/TC-API-001.test.ts"
        api_script.write_text(
            """import { mkdir } from 'node:fs/promises';
import { join, resolve } from 'node:path';
import { describe, expect, it } from 'vitest';
import { saveJsonEvidence } from '../../../../../test-automation/framework/evidence.js';
import { request } from '../../../../../test-automation/framework/api-client.js';
import { runtimeContext } from '../../../../../test-automation/framework/runtime-context.js';

const context = runtimeContext();
const caseDir = join(context.runDir, 'evidence', context.batchId, 'TC-API-001', 'api');

describe('TC-API-001 Local API health endpoint returns ready', () => {
  it('A-API-STATUS', async () => {
    const result = await request({
      method: 'GET',
      path: '/api/health',
      timeoutMs: 5_000,
    });

    await mkdir(caseDir, { recursive: true });
    await saveJsonEvidence(resolve(caseDir, 'health-request-response.json'), result.evidence);

    expect(result.status).toBe(200);
    expect(result.body).toEqual({ status: 'ready' });
    expect(result.correlationId).toBe('phase6-api-smoke');
    expect(result.evidence.redacted).toBe(true);
  });
});
""",
            encoding="utf-8",
        )

        # Write UI test script
        ui_script = run_dir / "scripts/ui/B01/TC-UI-002.spec.ts"
        ui_script.write_text(
            """import { mkdir } from 'node:fs/promises';
import { join, resolve } from 'node:path';
import { expect, test } from '../../../../../test-automation/framework/playwright.js';
import { runtimeContext } from '../../../../../test-automation/framework/runtime-context.js';

const context = runtimeContext();
const caseId = 'TC-UI-002';
const evidenceDir = join(context.runDir, 'evidence', context.batchId, caseId, 'ui');
const baseUrl = context.webBaseUrl ?? 'http://127.0.0.1:4173';

test.use({ video: 'on' });

test(`${caseId}: increment once and verify the same value after browser reload`, async ({ page }) => {
  await mkdir(evidenceDir, { recursive: true });
  const objectKey = `${caseId}-${Date.now()}`;
  await page.goto(`${baseUrl}/?object=${objectKey}`);

  const count = page.getByLabel('操作次数');
  await expect(count).toHaveText('0');

  await page.getByRole('button', { name: '执行本地操作' }).click();
  await expect(count).toHaveText('1');

  await page.reload();
  await expect(count).toHaveText('1');
  await page.screenshot({ path: resolve(evidenceDir, 'A-UI-002-PERSIST.png'), fullPage: true });
});
""",
            encoding="utf-8",
        )

        # Create current-version Task
        task = {
            "schema_version": 3,
            "workflow_version": "2.0.0",
            "task_id": "B01-live-task-001",
            "batch_id": "B01",
            "target_environment": "local-smoke",
            "deployment_version": "fixture-v1",
            "goal": "B01 Live Verification",
            "case_order": ["TC-API-001", "TC-UI-002"],
            "cases": [
                {
                    "case_id": "TC-API-001",
                    "batch_id": "B01",
                    "primary_execution": "API",
                    "title": "Local API health",
                    "steps": ["GET /api/health"],
                    "expected_results": [{"id": "E1", "expected": "status 200 ready"}],
                    "target_action": "GET /api/health",
                    "automation": {
                        "required": True,
                        "language": "typescript",
                        "runner": "vitest",
                        "driver": "node-native-fetch",
                        "script_target": "scripts/api/B01/TC-API-001.test.ts",
                        "script_strategy": "create_or_update",
                    },
                    "evidence_plan": {
                        "level": "standard",
                        "screenshots": [],
                        "recording": False,
                        "api": [{"kind": "request_response", "expected_ids": ["E1"], "redacted": True}],
                        "network": [],
                        "files": [],
                        "read_back_required": False,
                    },
                },
                {
                    "case_id": "TC-UI-002",
                    "batch_id": "B01",
                    "primary_execution": "UI",
                    "title": "Local UI increment and reload",
                    "steps": ["Click button and reload"],
                    "expected_results": [{"id": "E2", "expected": "persisted value 1"}],
                    "target_action": "Click button and reload",
                    "automation": {
                        "required": True,
                        "language": "typescript",
                        "runner": "playwright-test",
                        "driver": "playwright-page",
                        "script_target": "scripts/ui/B01/TC-UI-002.spec.ts",
                        "script_strategy": "create_or_update",
                    },
                    "evidence_plan": {
                        "level": "critical",
                        "screenshots": [{"kind": "screenshot", "expected_ids": ["E2"]}],
                        "recording": True,
                        "api": [],
                        "network": [],
                        "files": [],
                    },
                },
            ],
        }
        task_hash = _sha256(_canonical({k: v for k, v in task.items() if k != "task_hash"}))
        task["task_hash"] = task_hash
        task_path = run_dir / "internal/execution/tasks/B01-task.json"
        task_path.write_text(json.dumps(task, ensure_ascii=False, indent=2), encoding="utf-8")

        # Synthetic scope binding only; this does not prove a host Agent was dispatched.
        worker_session_id = "synthetic-runner-scope-001"
        receipt = {
            "agent_role": "execution_worker",
            "receipt_status": "dispatched",
            "accepted_at": "2026-09-28T00:00:00Z",
            "agent_session_id": worker_session_id,
            "task_id": task["task_id"],
            "task_hash": task_hash,
            "host_dispatch_ref": "synthetic-runner-scope-only",
            "dispatch_source": "codex_subagent_tool",
        }
        receipt_path = run_dir / "internal/execution/dispatch/B01-worker-receipt.json"
        receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8")

        # Initial runtime state pointing to TC-API-001
        state = {
            "batch_id": "B01",
            "status": "running",
            "task_ref": "internal/execution/tasks/B01-task.json",
            "current_case": "TC-API-001",
            "current_worker": worker_session_id,
            "worker_dispatch_receipt": receipt,
            "worker_receipt_ref": "internal/execution/dispatch/B01-worker-receipt.json",
        }
        state_path = run_dir / "internal/execution/runtime-state/B01-state.json"
        state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

        # -------------------------------------------------------------
        # 1. RUN API TEST via run-vitest.mjs
        # -------------------------------------------------------------
        env_api = os.environ.copy()
        env_api["TEST_RUN_DIR"] = str(run_dir)
        env_api["TEST_BATCH_ID"] = "B01"
        env_api["TEST_CASE_ID"] = "TC-API-001"
        env_api["TEST_SCRIPT_TARGET"] = "scripts/api/B01/TC-API-001.test.ts"
        env_api["TEST_ATTEMPT_ID"] = "attempt-001"
        env_api["TEST_RESULTS_DIR"] = str(run_dir / "runner-results/B01/TC-API-001/attempt-001")
        env_api["TEST_TASK_ID"] = task["task_id"]
        env_api["TEST_TASK_HASH"] = task_hash
        env_api["TEST_WORKER_SESSION_ID"] = worker_session_id
        env_api["TEST_API_BASE_URL"] = "http://127.0.0.1:4173"

        res_api = subprocess.run(
            ["node", "run-vitest.mjs"],
            cwd=str(AUTOMATION_DIR),
            env=env_api,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
        )
        assert res_api.returncode == 0, f"Vitest failed:\nSTDOUT:\n{res_api.stdout}\nSTDERR:\n{res_api.stderr}"

        # Verify API evidence produced
        api_evidence = run_dir / "evidence/B01/TC-API-001/api/health-request-response.json"
        assert api_evidence.is_file(), "API request-response evidence was not created"
        evidence_data = json.loads(api_evidence.read_text(encoding="utf-8"))
        assert evidence_data.get("redacted") is True
        assert evidence_data.get("response", {}).get("status") == 200

        # Verify Vitest runner report produced
        vitest_report = run_dir / "runner-results/B01/TC-API-001/attempt-001/vitest-report.json"
        assert vitest_report.is_file(), "vitest-report.json was not created"
        report_json = json.loads(vitest_report.read_text(encoding="utf-8"))
        assert report_json.get("success") is True

        # -------------------------------------------------------------
        # 2. RUN UI TEST via run-playwright.mjs
        # -------------------------------------------------------------
        # Update runtime state to TC-UI-002
        state["current_case"] = "TC-UI-002"
        state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

        env_ui = os.environ.copy()
        env_ui["TEST_RUN_DIR"] = str(run_dir)
        env_ui["TEST_BATCH_ID"] = "B01"
        env_ui["TEST_CASE_ID"] = "TC-UI-002"
        env_ui["TEST_SCRIPT_TARGET"] = "scripts/ui/B01/TC-UI-002.spec.ts"
        env_ui["TEST_ATTEMPT_ID"] = "attempt-001"
        env_ui["TEST_RESULTS_DIR"] = str(run_dir / "runner-results/B01/TC-UI-002/attempt-001")
        env_ui["TEST_TASK_ID"] = task["task_id"]
        env_ui["TEST_TASK_HASH"] = task_hash
        env_ui["TEST_WORKER_SESSION_ID"] = worker_session_id
        env_ui["TEST_WEB_BASE_URL"] = "http://127.0.0.1:4173"
        env_ui["TEST_RECORDING"] = "true"

        res_ui = subprocess.run(
            ["node", "run-playwright.mjs"],
            cwd=str(AUTOMATION_DIR),
            env=env_ui,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
        )
        assert res_ui.returncode == 0, f"Playwright failed:\nSTDOUT:\n{res_ui.stdout}\nSTDERR:\n{res_ui.stderr}"

        # Verify UI screenshot evidence produced
        ui_screenshot = run_dir / "evidence/B01/TC-UI-002/ui/A-UI-002-PERSIST.png"
        assert ui_screenshot.is_file(), "UI screenshot A-UI-002-PERSIST.png was not created"
        assert ui_screenshot.stat().st_size > 500, f"Screenshot file too small: {ui_screenshot.stat().st_size}"

        # Verify Playwright runner report produced
        playwright_report = run_dir / "runner-results/B01/TC-UI-002/attempt-001/playwright-report.json"
        assert playwright_report.is_file(), "playwright-report.json was not created"
        pw_report_json = json.loads(playwright_report.read_text(encoding="utf-8"))
        assert pw_report_json.get("stats", {}).get("unexpected") == 0

        # Verify WebM video produced
        artifacts_dir = run_dir / "runner-results/B01/TC-UI-002/attempt-001/playwright-artifacts"
        videos = list(artifacts_dir.glob("**/*.webm"))
        assert len(videos) >= 1, f"Playwright video not found in {artifacts_dir}"
        assert videos[0].stat().st_size > 500, f"Video file too small: {videos[0].stat().st_size}"

        # Copy official reports and video into evidence structure
        official_vitest_report = run_dir / "evidence/B01/TC-API-001/vitest-report.json"
        shutil.copy2(vitest_report, official_vitest_report)

        official_pw_report = run_dir / "evidence/B01/TC-UI-002/playwright-report.json"
        shutil.copy2(playwright_report, official_pw_report)

        video_target = run_dir / "evidence/B01/TC-UI-002/ui/TC-UI-002-recording.webm"
        shutil.copy2(videos[0], video_target)

        # -------------------------------------------------------------
        # 3. Formally validate Case Results against execution_control.py
        # -------------------------------------------------------------
        api_start = datetime.fromtimestamp(report_json["startTime"] / 1000 - 1, tz=timezone.utc).isoformat()
        api_finish = datetime.fromtimestamp(report_json["startTime"] / 1000 + 30, tz=timezone.utc).isoformat()
        api_result = {
            "schema_version": 3,
            "case_id": "TC-API-001",
            "target_environment": "local-smoke",
            "deployment_version": "fixture-v1",
            "status": "PASS",
            "actual_execution": "API",
            "expected_results": [
                {
                    "id": "E1",
                    "actual": "HTTP 200 ready",
                    "result": "pass",
                    "evidence_refs": ["evidence/B01/TC-API-001/api/health-request-response.json"],
                }
            ],
            "automation_run": {
                "script_ref": "scripts/api/B01/TC-API-001.test.ts",
                "script_sha256": hashlib.sha256(api_script.read_bytes()).hexdigest(),
                "runner": "vitest",
                "driver": "node-native-fetch",
                "static_check": "passed",
                "debug_attempts": [],
                "official_run": {
                    "run_id": "run-api-official-001",
                    "started_at": api_start,
                    "finished_at": api_finish,
                    "exit_code": 0,
                    "report_ref": "evidence/B01/TC-API-001/vitest-report.json",
                    "script_sha256": hashlib.sha256(api_script.read_bytes()).hexdigest(),
                },
            },
        }
        res_check_api = _ctl_mod.validate(task["cases"][0], api_result, evidence_root=run_dir)
        assert res_check_api["ok"] is True
        assert res_check_api["status"] == "PASS"

        pw_start_dt = datetime.fromisoformat(pw_report_json["stats"]["startTime"].replace("Z", "+00:00"))
        ui_start = (pw_start_dt - timedelta(seconds=1)).isoformat()
        ui_finish = (pw_start_dt + timedelta(seconds=60)).isoformat()
        ui_result = {
            "schema_version": 3,
            "case_id": "TC-UI-002",
            "target_environment": "local-smoke",
            "deployment_version": "fixture-v1",
            "status": "PASS",
            "actual_execution": "UI",
            "recording_ref": "evidence/B01/TC-UI-002/ui/TC-UI-002-recording.webm",
            "expected_results": [
                {
                    "id": "E2",
                    "actual": "persisted value 1 verified",
                    "result": "pass",
                    "evidence_refs": ["evidence/B01/TC-UI-002/ui/A-UI-002-PERSIST.png"],
                }
            ],
            "automation_run": {
                "script_ref": "scripts/ui/B01/TC-UI-002.spec.ts",
                "script_sha256": hashlib.sha256(ui_script.read_bytes()).hexdigest(),
                "runner": "playwright-test",
                "driver": "playwright-page",
                "static_check": "passed",
                "debug_attempts": [],
                "official_run": {
                    "run_id": "run-ui-official-001",
                    "started_at": ui_start,
                    "finished_at": ui_finish,
                    "exit_code": 0,
                    "report_ref": "evidence/B01/TC-UI-002/playwright-report.json",
                    "script_sha256": hashlib.sha256(ui_script.read_bytes()).hexdigest(),
                },
            },
        }
        res_check_ui = _ctl_mod.validate(task["cases"][1], ui_result, evidence_root=run_dir)
        assert res_check_ui["ok"] is True
        assert res_check_ui["status"] == "PASS"
        (run_dir / 'internal/execution/results/isolated-runner-results.json').write_text(
            json.dumps({'acceptance_level':'isolated_runner_smoke','host_dispatch_verified':False,'case_results':[api_result,ui_result]},ensure_ascii=False,indent=2),encoding='utf-8')

    finally:
        # Preserve the unique ignored Run for inspection of script hashes, reports and raw evidence.
        if server_proc:
            server_proc.terminate()
            server_proc.wait()
