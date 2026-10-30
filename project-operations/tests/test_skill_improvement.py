from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path

import pytest
import yaml


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "skill_improvement.py"
SPEC = importlib.util.spec_from_file_location("skill_improvement", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def create_group(root: Path) -> Path:
    router = root / "clarify-before-testing"
    (router / "references").mkdir(parents=True)
    (router / "references" / "skill-group.json").write_text(
        json.dumps(
            {
                "schema_version": "vnext-2",
                "public_entry": "clarify-before-testing",
                "members": {"clarify-before-testing": {"role": "router"}},
                "stages": {},
            }
        ),
        encoding="utf-8",
    )
    (router / "SKILL.md").write_text("# deterministic group\n", encoding="utf-8")
    return root


def create_learning(root: Path, status: str = "generalized") -> str:
    identifier = "learning-generalized-one"
    records = root / "records"
    records.mkdir(parents=True)
    (records / f"{identifier}.yaml").write_text(
        yaml.safe_dump(
            {
                "schema_version": "vnext-2",
                "learning_id": identifier,
                "classification": "component-interaction",
                "mechanism": "an asynchronous popup can mount before data arrives",
                "strategy": "wait for readiness and reread the visible controlled popup",
                "applicability": {"component": "async-select"},
                "failure_signature": "first visible read is empty",
                "status": status,
                "observation_count": 3,
                "source_projects": ["a", "b"],
                "source_runs": ["1", "2", "3"],
                "counterexample_challenges": 1,
                "created_at": "2026-01-01T00:00:00+00:00",
                "updated_at": "2026-01-01T00:00:00+00:00",
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    return identifier


def regression_report(path: Path, digest: str) -> None:
    path.write_text(
        json.dumps(
            {
                "schema_version": "vnext-2",
                "report_type": "core-skill-regression-baseline",
                "passed": True,
                "skill_group_unchanged": True,
                "skill_group_digest_before": digest,
                "skill_group_digest_after": digest,
                "validation": {"returncode": 0},
                "tests": {"returncode": 0},
            }
        ),
        encoding="utf-8",
    )


def test_proposal_requires_generalized_learning_and_current_regression(
    tmp_path: Path,
) -> None:
    group = create_group(tmp_path / "skills")
    learning = tmp_path / "learning"
    identifier = create_learning(learning)
    report = tmp_path / "regression.json"
    digest = MODULE.skill_group_digest(group)
    regression_report(report, digest)
    args = argparse.Namespace(
        learning_root=str(learning),
        skill_group_root=str(group),
        regression_report=str(report),
        learning_id=[identifier],
    )
    result = MODULE.command_propose(args)
    assert result["status"] == "pending-human-confirmation"
    assert result["required_decision_type"] == "core-skill-change"
    assert result["publication_performed"] is False
    proposal = learning / "proposals" / f"{result['proposal_id']}.yaml"
    assert proposal.is_file()
    events = (learning / "events" / "skill-improvement-events.jsonl").read_text(
        encoding="utf-8"
    )
    assert events.count("proposal-created") == 1
    repeated = MODULE.command_propose(args)
    assert repeated["proposal_id"] == result["proposal_id"]
    assert (learning / "events" / "skill-improvement-events.jsonl").read_text(
        encoding="utf-8"
    ).count("proposal-created") == 1


def test_observed_learning_and_stale_regression_are_rejected(tmp_path: Path) -> None:
    group = create_group(tmp_path / "skills")
    learning = tmp_path / "learning"
    identifier = create_learning(learning, status="observed")
    report = tmp_path / "regression.json"
    regression_report(report, MODULE.skill_group_digest(group))
    args = argparse.Namespace(
        learning_root=str(learning),
        skill_group_root=str(group),
        regression_report=str(report),
        learning_id=[identifier],
    )
    with pytest.raises(MODULE.ImprovementError, match="require generalized"):
        MODULE.command_propose(args)

    record = yaml.safe_load(
        (learning / "records" / f"{identifier}.yaml").read_text(encoding="utf-8")
    )
    record["status"] = "generalized"
    (learning / "records" / f"{identifier}.yaml").write_text(
        yaml.safe_dump(record, sort_keys=False), encoding="utf-8"
    )
    (group / "clarify-before-testing" / "SKILL.md").write_text(
        "# changed after regression\n", encoding="utf-8"
    )
    with pytest.raises(MODULE.ImprovementError, match="current Skill group"):
        MODULE.command_propose(args)
