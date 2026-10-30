from __future__ import annotations

import json
import hashlib
import subprocess
import sys
from pathlib import Path

import yaml


SKILL = Path(__file__).resolve().parents[1]
SCRIPT = SKILL / "scripts" / "asset_registry.py"


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-X", "utf8", str(SCRIPT), *args],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def write_yaml(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(value, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )


def automation_digest(root: Path) -> str:
    aggregate = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix not in {".py", ".json", ".ini"}:
            continue
        relative = path.relative_to(root).as_posix()
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        aggregate.update(relative.encode("utf-8"))
        aggregate.update(b"\0")
        aggregate.update(digest.encode("ascii"))
        aggregate.update(b"\n")
    return f"sha256:{aggregate.hexdigest()}"


def write_automation_dependencies(
    project: Path,
    *,
    dom_id: str = "dom.system.user",
    operation_id: str = "operation.system.user",
) -> None:
    write_yaml(
        project / "project-context" / "dom-maps" / f"{dom_id}.yaml",
        {
            "schema_version": "vnext-2",
            "asset_type": "dom-map",
            "asset_id": dom_id,
            "version": 1,
            "status": "candidate",
            "semantic_name": "user DOM",
            "route_pattern": "/users",
            "framework": "element-plus",
            "page_fingerprint": {"route": "/users"},
            "elements": [
                {
                    "element_id": "users.name",
                    "name": "name",
                    "component_type": "input",
                    "container": "form",
                    "primary_locator": "input[name=name]",
                    "fallback_locators": [],
                    "readiness": ["visible"],
                    "dependencies": [],
                }
            ],
            "source_runs": ["RUN-1"],
            "evidence_refs": ["evidence/dom.json"],
            "validation_history": [],
        },
    )
    operation = project / "project-context" / "operation-assets" / f"{operation_id}.md"
    operation.parent.mkdir(parents=True, exist_ok=True)
    operation.write_text(
        "---\n"
        + yaml.safe_dump(
            {
                "schema_version": "vnext-2",
                "asset_id": operation_id,
                "version": 1,
                "status": "candidate",
            },
            sort_keys=False,
        )
        + "---\n# operation\n",
        encoding="utf-8",
    )


def test_validates_rebuilds_searches_and_soft_retires_dom_asset(tmp_path: Path) -> None:
    asset = {
        "schema_version": "vnext-2",
        "asset_type": "dom-map",
        "asset_id": "dom.system.user",
        "version": 1,
        "status": "candidate",
        "semantic_name": "用户管理页面",
        "route_pattern": "/system/user",
        "framework": "element-plus",
        "page_fingerprint": {"route": "/system/user", "title": "用户管理"},
        "elements": [
            {
                "element_id": "user.form.department",
                "name": "归属部门",
                "component_type": "tree-select",
                "container": "添加用户",
                "primary_locator": ".el-form-item:has-text('归属部门') .el-select__wrapper",
                "fallback_locators": [],
                "readiness": ["visible", "options-loaded"],
                "dependencies": [],
            }
        ],
        "source_runs": ["RUN-1"],
        "evidence_refs": ["evidence/dom.json"],
        "validation_history": [],
    }
    write_yaml(
        tmp_path / "project-context" / "dom-maps" / "dom.system.user.yaml", asset
    )
    assert run_cli("validate", "--project-root", str(tmp_path)).returncode == 0
    assert run_cli("rebuild", "--project-root", str(tmp_path)).returncode == 0
    search = run_cli("search", "--project-root", str(tmp_path), "--query", "归属部门")
    assert search.returncode == 0, search.stderr
    assert json.loads(search.stdout)["matches"][0]["asset_id"] == "dom.system.user"

    retired = run_cli(
        "transition",
        "--project-root",
        str(tmp_path),
        "--asset-id",
        "dom.system.user",
        "--status",
        "retired",
        "--reason",
        "page removed",
    )
    assert retired.returncode == 0, retired.stderr
    updated = yaml.safe_load(
        (tmp_path / "project-context" / "dom-maps" / "dom.system.user.yaml").read_text(
            encoding="utf-8"
        )
    )
    assert updated["status"] == "retired"
    assert updated["tombstone"]["reason"] == "page removed"


def test_automation_promotion_requires_three_clean_independent_replays(
    tmp_path: Path,
) -> None:
    write_automation_dependencies(tmp_path)
    run_dir = tmp_path / "work" / "test-runs" / "RUN-1"
    staged = run_dir / "automation-staging" / "automation.user.yaml"
    staged_code = run_dir / "automation-staging" / "automation.user"
    staged_code.mkdir(parents=True)
    (staged_code / "runner.py").write_text("print('replay')\n", encoding="utf-8")
    code_digest = automation_digest(staged_code)
    write_yaml(
        staged,
        {
            "schema_version": "vnext-2",
            "asset_type": "automation",
            "asset_id": "automation.user",
            "version": 1,
            "status": "candidate",
            "semantic_name": "用户管理自动化",
            "code_path": "automation/assets/automation.user",
            "code_digest": code_digest,
            "case_ids": ["TC-USR-001"],
            "oracle_refs": ["COND-USR-001"],
            "actor_refs": ["admin"],
            "data_contract_refs": ["DATA-USR-001"],
            "dom_asset_refs": ["dom.system.user@1"],
            "operation_asset_refs": ["operation.system.user@1"],
            "validation_runs": [
                {
                    "run_id": "RUN-1",
                    "context_id": "CTX-1",
                    "result": "passed",
                    "repaired": False,
                    "scope": "affected-module",
                },
                {
                    "run_id": "RUN-1",
                    "context_id": "CTX-2",
                    "result": "passed",
                    "repaired": False,
                    "scope": "full-suite",
                },
            ],
            "unknown_effects": [],
            "cleanup_failures": [],
            "secret_findings": [],
            "source_runs": ["RUN-1"],
            "evidence_refs": ["evidence/replay.json"],
            "validation_history": [],
        },
    )
    failed = run_cli(
        "promote",
        "--project-root",
        str(tmp_path),
        "--run-dir",
        str(run_dir),
        "--source",
        str(staged),
    )
    assert failed.returncode == 1
    assert "three independent" in failed.stderr

    value = yaml.safe_load(staged.read_text(encoding="utf-8"))
    value["validation_runs"].append(
        {
            "run_id": "RUN-1",
            "context_id": "CTX-3",
            "result": "passed",
            "repaired": False,
            "scope": "case",
        }
    )
    (staged_code / "runner.py").write_text(
        "token = 'abcdefghijklmnopqrstuvwxyz123456'\nprint('replay')\n",
        encoding="utf-8",
    )
    value["code_digest"] = automation_digest(staged_code)
    write_yaml(staged, value)
    secret_blocked = run_cli(
        "promote",
        "--project-root",
        str(tmp_path),
        "--run-dir",
        str(run_dir),
        "--source",
        str(staged),
    )
    assert secret_blocked.returncode == 1
    assert "plaintext secrets" in secret_blocked.stderr

    (staged_code / "runner.py").write_text("print('replay')\n", encoding="utf-8")
    value["code_digest"] = automation_digest(staged_code)
    write_yaml(staged, value)
    promoted = run_cli(
        "promote",
        "--project-root",
        str(tmp_path),
        "--run-dir",
        str(run_dir),
        "--source",
        str(staged),
    )
    assert promoted.returncode == 0, promoted.stderr
    installed = yaml.safe_load(
        (
            tmp_path / "project-context" / "automation-assets" / "automation.user.yaml"
        ).read_text(encoding="utf-8")
    )
    assert installed["status"] == "verified"
    assert (
        tmp_path / "automation" / "assets" / "automation.user" / "runner.py"
    ).read_text(encoding="utf-8") == "print('replay')\n"


def test_hard_delete_allows_only_unreferenced_candidate_and_writes_tombstone(
    tmp_path: Path,
) -> None:
    path = tmp_path / "project-context" / "data-recipes" / "data.temp.yaml"
    write_yaml(
        path,
        {
            "schema_version": "vnext-2",
            "asset_type": "data-recipe",
            "asset_id": "data.temp",
            "version": 1,
            "status": "candidate",
            "semantic_name": "temporary recipe",
            "contract_id": "DATA-TEMP",
            "provision_channel": "api",
            "verify_steps": ["verify marker"],
            "cleanup_steps": ["delete marker"],
            "reconcile_steps": ["query marker"],
            "actor_refs": ["ACTOR-1"],
            "source_runs": ["RUN-TEMP"],
            "evidence_refs": ["evidence/temp.json"],
            "validation_history": [],
        },
    )
    deleted = run_cli(
        "delete",
        "--project-root",
        str(tmp_path),
        "--asset-id",
        "data.temp",
        "--reason",
        "secret-bearing unreferenced candidate",
        "--hard",
    )
    assert deleted.returncode == 0, deleted.stderr
    assert not path.exists()
    tombstone = yaml.safe_load(
        (tmp_path / "project-context" / "tombstones" / "data.temp.yaml").read_text(
            encoding="utf-8"
        )
    )
    assert tombstone["physical_delete"] is True
    assert "contract_id" not in tombstone
    assert "evidence_refs" not in tombstone
    index = json.loads(
        (tmp_path / "project-context" / "asset-index.json").read_text(encoding="utf-8")
    )
    assert index["assets"] == []


def test_hard_delete_rejects_candidate_referenced_by_another_asset(
    tmp_path: Path,
) -> None:
    dom = {
        "schema_version": "vnext-2",
        "asset_type": "dom-map",
        "asset_id": "dom.referenced",
        "version": 1,
        "status": "candidate",
        "semantic_name": "referenced DOM",
        "route_pattern": "/users",
        "framework": "element-plus",
        "page_fingerprint": {"route": "/users"},
        "elements": [
            {
                "element_id": "users.name",
                "name": "name",
                "component_type": "input",
                "container": "form",
                "primary_locator": "input[name=name]",
                "fallback_locators": [],
                "readiness": ["visible"],
                "dependencies": [],
            }
        ],
        "source_runs": ["RUN-1"],
        "evidence_refs": ["evidence/dom.json"],
        "validation_history": [],
    }
    write_yaml(tmp_path / "project-context" / "dom-maps" / "dom.referenced.yaml", dom)
    operation = tmp_path / "project-context" / "operation-assets" / "consumer.md"
    operation.parent.mkdir(parents=True)
    operation.write_text("uses `dom.referenced@1`\n", encoding="utf-8")
    blocked = run_cli(
        "delete",
        "--project-root",
        str(tmp_path),
        "--asset-id",
        "dom.referenced",
        "--reason",
        "try delete",
        "--hard",
    )
    assert blocked.returncode == 1
    assert "unreferenced candidates" in blocked.stderr
