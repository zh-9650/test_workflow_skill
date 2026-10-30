from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import yaml


SKILL = Path(__file__).resolve().parents[1]
SCRIPT = SKILL / "scripts" / "shared_learning.py"


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-X", "utf8", str(SCRIPT), *args],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def event(
    path: Path,
    *,
    project: str = "project-a",
    run: str = "RUN-1",
    strategy: str = "Wait for the controlled visible listbox and an options-loaded signal, then reread options",
    counterexample: str | None = None,
) -> None:
    path.write_text(
        json.dumps(
            {
                "schema_version": "vnext-2",
                "event_id": f"EVENT-{project}-{run}",
                "classification": "component-interaction",
                "mechanism": "Element Plus async select may mount before options load",
                "strategy": strategy,
                "applicability": {"framework": "element-plus", "component": "select"},
                "failure_signature": "visible listbox has zero options on first read",
                "counterexample": counterexample,
                "project_ref": project,
                "run_ref": run,
                "evidence_refs": ["evidence/dropdown.json"],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def test_ingest_is_immediately_searchable_and_deduplicates(tmp_path: Path) -> None:
    source = tmp_path / "event.json"
    event(source)
    first = run_cli(
        "ingest", "--learning-root", str(tmp_path / "learning"), "--event", str(source)
    )
    assert first.returncode == 0, first.stderr
    record = json.loads(first.stdout)
    assert record["status"] == "observed"
    second = run_cli(
        "ingest", "--learning-root", str(tmp_path / "learning"), "--event", str(source)
    )
    assert second.returncode == 0, second.stderr
    assert json.loads(second.stdout)["observation_count"] == 1
    search = run_cli(
        "search",
        "--learning-root",
        str(tmp_path / "learning"),
        "--query",
        "async select",
    )
    assert search.returncode == 0, search.stderr
    assert json.loads(search.stdout)["matches"][0]["status"] == "observed"


def test_independent_event_ids_raise_confidence_but_duplicate_delivery_does_not(
    tmp_path: Path,
) -> None:
    root = tmp_path / "learning"
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    event(first, run="RUN-1")
    event(second, run="RUN-2")
    created = run_cli("ingest", "--learning-root", str(root), "--event", str(first))
    assert json.loads(created.stdout)["status"] == "observed"
    corroborated = run_cli(
        "ingest", "--learning-root", str(root), "--event", str(second)
    )
    assert corroborated.returncode == 0, corroborated.stderr
    result = json.loads(corroborated.stdout)
    assert result["observation_count"] == 2
    assert result["status"] == "corroborated"


def test_shared_learning_rejects_project_url_and_plaintext_secret(
    tmp_path: Path,
) -> None:
    source = tmp_path / "bad.json"
    event(source)
    value = json.loads(source.read_text(encoding="utf-8"))
    value["strategy"] = (
        "Open http://192.168.1.10 then use password=abcdefghijklmnop123456"
    )
    source.write_text(json.dumps(value), encoding="utf-8")
    result = run_cli(
        "ingest", "--learning-root", str(tmp_path / "learning"), "--event", str(source)
    )
    assert result.returncode == 1
    assert "project-specific or secret" in result.stderr


def test_retired_learning_is_hidden_from_default_search(tmp_path: Path) -> None:
    source = tmp_path / "event.json"
    event(source)
    created = run_cli(
        "ingest", "--learning-root", str(tmp_path / "learning"), "--event", str(source)
    )
    learning_id = json.loads(created.stdout)["learning_id"]
    retired = run_cli(
        "transition",
        "--learning-root",
        str(tmp_path / "learning"),
        "--learning-id",
        learning_id,
        "--status",
        "retired",
        "--reason",
        "superseded",
    )
    assert retired.returncode == 0, retired.stderr
    result = run_cli(
        "search",
        "--learning-root",
        str(tmp_path / "learning"),
        "--query",
        "async select",
    )
    assert json.loads(result.stdout)["matches"] == []
    record = yaml.safe_load(
        (tmp_path / "learning" / "records" / f"{learning_id}.yaml").read_text(
            encoding="utf-8"
        )
    )
    assert record["status"] == "retired"


def test_runtime_feedback_is_idempotent_anonymous_and_degrades_contradiction(
    tmp_path: Path,
) -> None:
    root = tmp_path / "learning"
    source = tmp_path / "event.json"
    event(source)
    created = run_cli("ingest", "--learning-root", str(root), "--event", str(source))
    learning_id = json.loads(created.stdout)["learning_id"]
    feedback = tmp_path / "feedback.json"
    feedback.write_text(
        json.dumps(
            {
                "schema_version": "vnext-2",
                "feedback_id": "FEEDBACK-1",
                "learning_id": learning_id,
                "project_ref": "private-project-name",
                "run_ref": "RUN-PRIVATE-1",
                "outcome": "contradicted",
                "applicability_note": "virtualized listbox exposes options through an accessibility tree before DOM rows exist",
                "evidence_refs": ["private/evidence/path.json"],
            }
        ),
        encoding="utf-8",
    )
    first = run_cli(
        "feedback",
        "--learning-root",
        str(root),
        "--feedback",
        str(feedback),
    )
    assert first.returncode == 0, first.stderr
    assert json.loads(first.stdout)["status"] == "degraded"
    second = run_cli(
        "feedback",
        "--learning-root",
        str(root),
        "--feedback",
        str(feedback),
    )
    assert second.returncode == 0, second.stderr
    record = yaml.safe_load(
        (root / "records" / f"{learning_id}.yaml").read_text(encoding="utf-8")
    )
    assert record["feedback_counts"]["contradicted"] == 1
    assert len(record["feedback_history"]) == 1
    serialized = json.dumps(record, ensure_ascii=False)
    assert "private-project-name" not in serialized
    assert "RUN-PRIVATE-1" not in serialized
    assert "private/evidence/path.json" not in serialized


def test_feedback_rejects_project_specific_applicability_note(tmp_path: Path) -> None:
    root = tmp_path / "learning"
    source = tmp_path / "event.json"
    event(source)
    created = run_cli("ingest", "--learning-root", str(root), "--event", str(source))
    learning_id = json.loads(created.stdout)["learning_id"]
    feedback = tmp_path / "feedback.json"
    feedback.write_text(
        json.dumps(
            {
                "schema_version": "vnext-2",
                "feedback_id": "FEEDBACK-BAD",
                "learning_id": learning_id,
                "project_ref": "project",
                "run_ref": "run",
                "outcome": "not-applicable",
                "applicability_note": "only at http://192.168.1.2/users",
                "evidence_refs": ["evidence.json"],
            }
        ),
        encoding="utf-8",
    )
    result = run_cli(
        "feedback",
        "--learning-root",
        str(root),
        "--feedback",
        str(feedback),
    )
    assert result.returncode == 1
    assert "project-specific" in result.stderr


def test_conflicting_strategy_degrades_both_until_one_is_retired(
    tmp_path: Path,
) -> None:
    root = tmp_path / "learning"
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    event(first, strategy="Wait for loaded options before reading")
    event(
        second,
        project="project-b",
        strategy="Treat an empty first read as final and stop immediately",
    )
    original = run_cli("ingest", "--learning-root", str(root), "--event", str(first))
    conflicting = run_cli(
        "ingest", "--learning-root", str(root), "--event", str(second)
    )
    assert original.returncode == 0, original.stderr
    assert conflicting.returncode == 0, conflicting.stderr
    original_id = json.loads(original.stdout)["learning_id"]
    conflicting_id = json.loads(conflicting.stdout)["learning_id"]
    original_record = yaml.safe_load(
        (root / "records" / f"{original_id}.yaml").read_text(encoding="utf-8")
    )
    assert original_record["status"] == "degraded"
    assert original_record["conflicts_with"] == [conflicting_id]
    assert json.loads(conflicting.stdout)["status"] == "degraded"

    retired = run_cli(
        "transition",
        "--learning-root",
        str(root),
        "--learning-id",
        conflicting_id,
        "--status",
        "retired",
        "--reason",
        "contradicted by independent evidence",
    )
    assert retired.returncode == 0, retired.stderr
    resolved = yaml.safe_load(
        (root / "records" / f"{original_id}.yaml").read_text(encoding="utf-8")
    )
    assert resolved["conflicts_with"] == []
    assert resolved["status"] == "observed"


def test_generalized_transition_cannot_bypass_confidence_threshold(
    tmp_path: Path,
) -> None:
    root = tmp_path / "learning"
    source = tmp_path / "event.json"
    event(source)
    created = run_cli("ingest", "--learning-root", str(root), "--event", str(source))
    learning_id = json.loads(created.stdout)["learning_id"]
    rejected = run_cli(
        "transition",
        "--learning-root",
        str(root),
        "--learning-id",
        learning_id,
        "--status",
        "generalized",
        "--reason",
        "manual shortcut",
    )
    assert rejected.returncode == 1
    assert "lacks independent observations" in rejected.stderr
