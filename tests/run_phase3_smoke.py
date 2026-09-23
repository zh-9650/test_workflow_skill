"""Run real API and UI cases against isolated local fixtures."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).resolve().parent / "phase3-smoke"


def run(command: list[str], cwd: Path, env: dict[str, str]) -> None:
    print(f"$ {' '.join(command)}", flush=True)
    if os.name == "nt":
        subprocess.run(subprocess.list2cmdline(command), cwd=cwd, env=env, check=True, shell=True)
    else:
        subprocess.run(command, cwd=cwd, env=env, check=True)


def available_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def wait_for_fixture(url: str, process: subprocess.Popen) -> None:
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"local fixture server exited early with {process.returncode}")
        try:
            with urllib.request.urlopen(url, timeout=1) as response:
                if response.status == 200 and response.read() == b"ready":
                    return
        except OSError:
            time.sleep(0.1)
    raise TimeoutError(f"local fixture server did not become ready: {url}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-install", action="store_true", help="reuse an existing npm install")
    parser.add_argument("--skip-browser-install", action="store_true", help="reuse an installed Chromium")
    args = parser.parse_args()

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    project = REPO / ".phase3-smoke" / f"project-{stamp}"
    project.mkdir(parents=True)
    (project / "README.md").write_text("# Isolated Phase 3 smoke project\n", encoding="utf-8")

    import runpy

    bootstrap_module = runpy.run_path(str(REPO / "test-project-bootstrap/scripts/bootstrap_project.py"))
    bootstrap_result = bootstrap_module["bootstrap"](project)
    if not bootstrap_result["ok"]:
        raise RuntimeError(f"bootstrap failed: {bootstrap_result}")

    runtime = project / "work/test-automation"
    run_id = f"SMOKE-{stamp}"
    run_dir = project / "work/test-runs" / run_id
    api_script = run_dir / "scripts/api/B01/TC-API-001.test.ts"
    ui_script = run_dir / "scripts/ui/B01/TC-UI-001.spec.ts"
    api_script.parent.mkdir(parents=True, exist_ok=True)
    ui_script.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(FIXTURES / "templates/TC-API-001.test.ts", api_script)
    shutil.copyfile(FIXTURES / "templates/TC-UI-001.spec.ts", ui_script)

    if not api_script.is_file() or not ui_script.is_file():
        raise RuntimeError("formal case scripts must exist before either runner starts")

    if not args.skip_install:
        run(["npm", "ci"], runtime, os.environ.copy())
    if not args.skip_browser_install:
        run(["npx", "playwright", "install", "chromium"], runtime, os.environ.copy())

    run(["npm", "run", "typecheck"], runtime, os.environ.copy())

    port = available_port()
    fixture_env = os.environ.copy()
    fixture_env["PHASE3_SMOKE_PORT"] = str(port)
    server = subprocess.Popen(
        ["node", str(FIXTURES / "fixture-server.mjs")],
        cwd=REPO,
        env=fixture_env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        base_url = f"http://127.0.0.1:{port}"
        wait_for_fixture(f"{base_url}/health", server)
        results_dir = run_dir / "runner-results"
        env = os.environ.copy()
        env.update(
            {
                "TEST_RUN_DIR": str(run_dir),
                "TEST_BATCH_ID": "B01",
                "TEST_API_BASE_URL": base_url,
                "TEST_WEB_BASE_URL": base_url,
                "TEST_RESULTS_DIR": str(results_dir),
                "TEST_RECORDING": "true",
            }
        )
        run(["npm", "run", "test:api"], runtime, env)
        run(["npm", "run", "test:ui"], runtime, env)
    finally:
        server.terminate()
        try:
            server.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server.kill()
            server.wait()

    report_api = results_dir / "vitest-report.json"
    report_ui = results_dir / "playwright-report.json"
    screenshot = run_dir / "evidence/TC-UI-001-key-result.png"
    api_evidence = run_dir / "evidence/TC-API-001-request-response.json"
    videos = list((results_dir / "playwright-artifacts").rglob("*.webm"))
    required = [report_api, report_ui, screenshot, api_evidence]
    missing = [str(path) for path in required if not path.is_file()]
    if missing or not videos:
        raise RuntimeError(f"missing smoke artifacts: {missing}; videos={videos}")
    evidence = json.loads(api_evidence.read_text(encoding="utf-8"))
    if "smoke-secret" in json.dumps(evidence):
        raise RuntimeError("API evidence redaction failed")

    print(json.dumps({
        "project": str(project),
        "run": str(run_dir),
        "api_script": str(api_script),
        "ui_script": str(ui_script),
        "api_report": str(report_api),
        "ui_report": str(report_ui),
        "screenshot": str(screenshot),
        "video": [str(path) for path in videos],
        "redaction_verified": True,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
