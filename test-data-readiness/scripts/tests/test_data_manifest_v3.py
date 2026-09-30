import hashlib
import importlib.util
import json
from pathlib import Path

import pytest


MODULE_PATH = Path(__file__).resolve().parents[1] / "data_manifest.py"
SPEC = importlib.util.spec_from_file_location("data_manifest_v3_test", MODULE_PATH)
data_manifest = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(data_manifest)


def _write_json(path: Path, payload: dict) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _plan():
    return {
        "schema_version": 3,
        "target_environment": {"env_id": "test", "initial_deployment_version": "v1"},
        "batches": [{"id": "B01", "case_ids": ["C01"]}],
        "cases": [{"case_id": "C01", "batch_id": "B01"}],
        "data_requirements": [
            {
                "scope": "runtime_generated",
                "object_type": "receipt",
                "case_ids": ["C01"],
                "actor_role": "tester",
                "permission_requirements": ["create_receipt"],
                "creation_timing": "runtime",
                "isolation_scope": "case",
                "source": "case_action",
            }
        ],
    }


def _manifest(run_dir: Path):
    report = run_dir / "evidence/B01/C01/account/runner-report.json"
    report_hash = _write_json(report, {"exit_code": 0})
    evidence = run_dir / "evidence/B01/C01/account/verification.json"
    evidence_hash = _write_json(
        evidence,
        {
            "batch_id": "B01",
            "case_id": "C01",
            "actor_ref": "acct:test:operator-01",
            "roles": ["tester"],
            "permissions": ["create_receipt"],
            "authenticated": True,
            "permissions_verified": True,
            "secret_resolved": True,
            "observed_via": "node-native-fetch",
            "runner_report_ref": "evidence/B01/C01/account/runner-report.json",
            "runner_report_sha256": report_hash,
        },
    )
    return {
        "schema_version": 3,
        "batch_id": "B01",
        "data_required": False,
        "reason": "Only runtime-generated data is planned",
        "objects": [],
        "builders": [],
        "actor_bindings": [
            {
                "actor_ref": "acct:test:operator-01",
                "roles": ["tester"],
                "permissions": ["create_receipt"],
                "secret_ref": "env:TEST_OPERATOR_TOKEN",
                "case_ids": ["C01"],
                "verified": True,
                "verification_evidence_ref": "evidence/B01/C01/account/verification.json",
                "verification_evidence_sha256": evidence_hash,
            }
        ],
    }


def test_valid_manifest_binds_real_actor_and_secret_reference(tmp_path):
    result = data_manifest.validate(_manifest(tmp_path), _plan(), tmp_path)
    assert result["ok"] is True


def test_manifest_rejects_missing_actor_bindings(tmp_path):
    manifest = _manifest(tmp_path)
    manifest.pop("actor_bindings")
    with pytest.raises(AssertionError, match="actor_bindings"):
        data_manifest.validate(manifest, _plan(), tmp_path)


def test_manifest_rejects_plain_secret_value(tmp_path):
    manifest = _manifest(tmp_path)
    manifest["actor_bindings"][0]["secret_ref"] = "real-token-value"
    with pytest.raises(AssertionError, match="secret_ref"):
        data_manifest.validate(manifest, _plan(), tmp_path)


def test_manifest_rejects_schema_v2(tmp_path):
    manifest = _manifest(tmp_path)
    manifest["schema_version"] = 2
    with pytest.raises(AssertionError, match="schema_version"):
        data_manifest.validate(manifest, _plan(), tmp_path)


def test_actor_role_must_cover_planning_requirement(tmp_path):
    plan=_plan(); plan['data_requirements'][0]['actor_role']='administrator'
    with pytest.raises(AssertionError,match='role|actor'):
        data_manifest.validate(_manifest(tmp_path),plan,tmp_path)


def test_actor_permission_must_cover_planning_requirement(tmp_path):
    plan=_plan(); plan['data_requirements'][0]['permission_requirements']=['delete_receipt']
    with pytest.raises(AssertionError,match='permission|actor'):
        data_manifest.validate(_manifest(tmp_path),plan,tmp_path)
