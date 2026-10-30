from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


SKILL = Path(__file__).resolve().parents[1]
SCRIPT = SKILL / "scripts" / "operation_assets.py"


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-X", "utf8", str(SCRIPT), *args],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def create_asset(project: Path, asset_id: str = "auth.login.standard") -> Path:
    root = project / "project-context" / "operation-assets"
    root.mkdir(parents=True)
    path = root / f"{asset_id}.md"
    path.write_text(
        f"""---
schema_version: vnext-2
asset_id: {asset_id}
semantic_name: Login and verify identity
asset_type: authentication
intent: login
status: candidate
version: 1
environments: [test]
roles: [admin]
components: [form]
business_states: [logged-out]
proof_scope: [identity, role]
compatibility_fingerprint:
  app: demo
source_runs: [RUN-001]
last_verified_at: null
lifecycle_history: []
---
# Login and verify identity

## Purpose and supported inputs
Account alias.

## Applicability
Test environment.

## Non-applicability
MFA without human.

## Dynamic-value resolution
Resolve the account alias from protected configuration.

## Preconditions
Login page is visible.

## Preferred user-level strategy
Fill the labelled fields and submit.

## Proof scope and evidence
Verify displayed account, role, and refresh persistence.

## Failure signatures and recovery
Expired session returns to login.

## Sensitive references
Protected references only.

## Validation and lifecycle history
Created from RUN-001.
""",
        encoding="utf-8",
    )
    return path


def test_validate_rebuild_and_search(tmp_path: Path) -> None:
    create_asset(tmp_path)
    validate = run_cli("validate", "--project-root", str(tmp_path))
    assert validate.returncode == 0, validate.stdout + validate.stderr
    rebuild = run_cli("rebuild", "--project-root", str(tmp_path))
    assert rebuild.returncode == 0, rebuild.stdout + rebuild.stderr
    index = json.loads(
        (tmp_path / "project-context" / "operation-assets" / "index.json").read_text(
            encoding="utf-8"
        )
    )
    assert index["assets"][0]["asset_id"] == "auth.login.standard"
    search = run_cli(
        "search",
        "--project-root",
        str(tmp_path),
        "--intent",
        "login",
        "--environment",
        "test",
        "--role",
        "admin",
    )
    assert search.returncode == 0, search.stdout + search.stderr
    value = json.loads(search.stdout)
    assert value["matches"][0]["asset_id"] == "auth.login.standard"


def test_plaintext_secret_is_rejected(tmp_path: Path) -> None:
    path = create_asset(tmp_path)
    path.write_text(
        path.read_text(encoding="utf-8")
        + "\npassword=abcdefghijklmnopqrstuvwxyz123456\n",
        encoding="utf-8",
    )
    result = run_cli("validate", "--project-root", str(tmp_path))
    assert result.returncode == 1
    assert "possible plaintext secret" in result.stderr


def test_transition_versions_operation_asset_and_records_tombstone(
    tmp_path: Path,
) -> None:
    path = create_asset(tmp_path)
    verified = run_cli(
        "transition",
        "--project-root",
        str(tmp_path),
        "--asset-id",
        "auth.login.standard",
        "--status",
        "verified",
        "--reason",
        "three clean validations",
    )
    assert verified.returncode == 0, verified.stderr
    value = json.loads(verified.stdout)
    assert value["version"] == 2
    assert value["last_verified_at"] is not None
    retired = run_cli(
        "transition",
        "--project-root",
        str(tmp_path),
        "--asset-id",
        "auth.login.standard",
        "--status",
        "retired",
        "--reason",
        "superseded",
    )
    assert retired.returncode == 0, retired.stderr
    text = path.read_text(encoding="utf-8")
    assert "status: retired" in text
    assert "tombstone:" in text
    index = json.loads(
        (tmp_path / "project-context" / "operation-assets" / "index.json").read_text(
            encoding="utf-8"
        )
    )
    assert index["assets"][0]["version"] == 3
