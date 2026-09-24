from __future__ import annotations

import hashlib
import json

import pytest

from conftest import load_script


def _contract():
    return load_script(
        "test-data-readiness/scripts/data_manifest.py",
        "data_readiness_manifest_contract",
    )


def _ready_manifest(tmp_path):
    run = tmp_path / "run"
    script = run / "scripts/data/create-project.test.ts"
    script.parent.mkdir(parents=True)
    script.write_text("// TypeScript API builder\n", encoding="utf-8")
    script_hash = hashlib.sha256(script.read_bytes()).hexdigest()
    builder_evidence = run / "evidence/B01/TC-001/builder-read-back.json"
    object_evidence = run / "evidence/B01/TC-001/object-read-back.json"
    observation = run / "evidence/B01/TC-001/raw-object-response.json"
    report = run / "evidence/B01/TC-001/builder-run-report.json"
    builder_evidence.parent.mkdir(parents=True)
    observation.write_text(json.dumps({"object_ref": "project-123", "object_type": "project", "observed_fields": {"status": "ready", "name": "isolated-smoke"}}), encoding="utf-8")
    report.write_text(json.dumps({"exit_code": 0, "script_sha256": script_hash}), encoding="utf-8")
    evidence_refs = {
        "builder_id": "create-project-v1",
        "observation_ref": "evidence/B01/TC-001/raw-object-response.json",
        "observation_sha256": hashlib.sha256(observation.read_bytes()).hexdigest(),
        "runner_report_ref": "evidence/B01/TC-001/builder-run-report.json",
        "runner_report_sha256": hashlib.sha256(report.read_bytes()).hexdigest(),
        "observed_via": "node-native-fetch",
        "script_ref": "scripts/data/create-project.test.ts",
        "script_sha256": script_hash,
    }
    builder_evidence.write_text(
        json.dumps(
            {
                "batch_id": "B01",
                "case_id": "TC-001",
                "builder_id": "create-project-v1",
                "object_ref": "project-123",
                "read_back_verified": True,
                **evidence_refs,
            }
        ),
        encoding="utf-8",
    )
    object_evidence.write_text(
        json.dumps(
            {
                "batch_id": "B01",
                "case_id": "TC-001",
                "object_ref": "project-123",
                "read_back_verified": True,
                **evidence_refs,
            }
        ),
        encoding="utf-8",
    )
    plan = {
        "batches": [{"id": "B01", "case_ids": ["TC-001"]}],
        "cases": [{"case_id": "TC-001", "data_required": True}],
    }
    manifest = {
        "batch_id": "B01",
        "data_required": True,
        "builders": [
            {
                "builder_id": "create-project-v1",
                "object_type": "project",
                "business_entry": "api",
                "language": "typescript",
                "runner": "vitest",
                "script_ref": "scripts/data/create-project.test.ts",
                "script_sha256": script_hash,
                "verified": True,
                "verified_environment": "isolated-test",
                "verified_at": "2026-09-23T00:00:00Z",
                "verified_case_id": "TC-001",
                "verified_object_ref": "project-123",
                "read_back_evidence_ref": "evidence/B01/TC-001/builder-read-back.json",
            }
        ],
        "objects": [
            {
                "object_type": "project",
                "object_ref": "project-123",
                "creation": {
                    "business_entry": "api",
                    "implementation": "script",
                    "builder_id": "create-project-v1",
                    "builder_ref": "scripts/data/create-project.test.ts",
                },
                "state_applicable": False,
                "verified": True,
                "read_back_verified": True,
                "read_back_evidence_ref": "evidence/B01/TC-001/object-read-back.json",
                "relations_verified": True,
                "case_ids": ["TC-001"],
            }
        ],
    }
    return run, plan, manifest


def test_manifest_binds_typescript_builder_hash_and_real_read_back_evidence(tmp_path):
    contract = _contract()
    run, plan, manifest = _ready_manifest(tmp_path)

    result = contract.validate(manifest, plan, run)

    assert result["ok"] is True
    assert result["readiness"]["ready"] is True


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("wrong_runner", "runner"),
        ("stale_hash", "script_sha256"),
        ("missing_read_back", "read_back_evidence_ref"),
        ("mismatched_read_back", "object_ref"),
        ("missing_observed_fields", "observed_fields"),
        ("wrong_observed_state", "target_state"),
        ("script_escape", "scripts/data"),
    ],
)
def test_manifest_rejects_unverifiable_builder_or_read_back(tmp_path, mutation, message):
    contract = _contract()
    run, plan, manifest = _ready_manifest(tmp_path)
    builder = manifest["builders"][0]
    obj = manifest["objects"][0]
    evidence_path = run / obj["read_back_evidence_ref"]
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))

    if mutation == "wrong_runner":
        builder["runner"] = "playwright-test"
    elif mutation == "stale_hash":
        builder["script_sha256"] = "0" * 64
    elif mutation == "missing_read_back":
        obj.pop("read_back_evidence_ref")
    elif mutation == "mismatched_read_back":
        evidence["object_ref"] = "different-project"
        evidence_path.write_text(json.dumps(evidence), encoding="utf-8")
    elif mutation == "missing_observed_fields":
        observation = run / "evidence/B01/TC-001/raw-object-response.json"
        observation.write_text(json.dumps({"object_ref": "project-123", "object_type": "project"}), encoding="utf-8")
        evidence["observation_sha256"] = hashlib.sha256(observation.read_bytes()).hexdigest()
        evidence_path.write_text(json.dumps(evidence), encoding="utf-8")
        builder_evidence_path = run / "evidence/B01/TC-001/builder-read-back.json"
        builder_evidence = json.loads(builder_evidence_path.read_text(encoding="utf-8"))
        builder_evidence["observation_sha256"] = evidence["observation_sha256"]
        builder_evidence_path.write_text(json.dumps(builder_evidence), encoding="utf-8")
    elif mutation == "wrong_observed_state":
        obj.update({"state_applicable": True, "target_state": "active", "current_state": "active"})
        observation = run / "evidence/B01/TC-001/raw-object-response.json"
        observation.write_text(json.dumps({"object_ref": "project-123", "object_type": "project", "observed_fields": {"status": "draft"}}), encoding="utf-8")
        evidence["observation_sha256"] = hashlib.sha256(observation.read_bytes()).hexdigest()
        evidence_path.write_text(json.dumps(evidence), encoding="utf-8")
        builder_evidence_path = run / "evidence/B01/TC-001/builder-read-back.json"
        builder_evidence = json.loads(builder_evidence_path.read_text(encoding="utf-8"))
        builder_evidence["observation_sha256"] = evidence["observation_sha256"]
        builder_evidence_path.write_text(json.dumps(builder_evidence), encoding="utf-8")
    elif mutation == "script_escape":
        builder["script_ref"] = "../outside.ts"
        manifest["objects"][0]["creation"]["builder_ref"] = "../outside.ts"

    with pytest.raises(AssertionError, match=message):
        contract.validate(manifest, plan, run)
