from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml


SCHEMA_VERSION = "vnext-2"
STATUSES = {"observed", "corroborated", "generalized", "degraded", "retired"}
EVENT_FIELDS = {
    "schema_version",
    "event_id",
    "classification",
    "mechanism",
    "strategy",
    "applicability",
    "failure_signature",
    "counterexample",
    "project_ref",
    "run_ref",
    "evidence_refs",
}
FEEDBACK_FIELDS = {
    "schema_version",
    "feedback_id",
    "learning_id",
    "project_ref",
    "run_ref",
    "outcome",
    "applicability_note",
    "evidence_refs",
}
FORBIDDEN_PATTERNS = (
    re.compile(r"https?://", re.IGNORECASE),
    re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"),
    re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]{12,}", re.IGNORECASE),
    re.compile(
        r"(?i)\b(password|passwd|token|secret|authorization|api[_-]?key)\b"
        r"\s*[:=]\s*['\"]?[A-Za-z0-9._~+/=-]{12,}"
    ),
)


class LearningError(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def atomic_write_yaml(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(
        yaml.safe_dump(value, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )
    os.replace(temporary, path)


def atomic_write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    os.replace(temporary, path)


def append_jsonl(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise LearningError(f"cannot read event {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise LearningError("learning event must be an object")
    return value


def read_yaml(path: Path) -> dict[str, Any]:
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise LearningError(f"cannot read learning record {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise LearningError(f"learning record must be an object: {path}")
    return value


def learning_root(value: str | None) -> Path:
    return (
        Path(value).expanduser().resolve()
        if value
        else (Path.home() / ".claude" / "test-learning").resolve()
    )


def validate_event(event: dict[str, Any]) -> None:
    missing = sorted(EVENT_FIELDS - event.keys())
    if missing:
        raise LearningError(f"learning event missing fields: {missing}")
    if event.get("schema_version") != SCHEMA_VERSION:
        raise LearningError(f"learning event schema must be {SCHEMA_VERSION}")
    for field in (
        "event_id",
        "classification",
        "mechanism",
        "strategy",
        "failure_signature",
        "project_ref",
        "run_ref",
    ):
        if not isinstance(event.get(field), str) or not event[field].strip():
            raise LearningError(f"{field} must be a non-empty string")
    if not isinstance(event.get("applicability"), dict) or not event["applicability"]:
        raise LearningError("applicability must be a non-empty object")
    if not isinstance(event.get("evidence_refs"), list) or not event["evidence_refs"]:
        raise LearningError("evidence_refs must be a non-empty list")
    shareable = json.dumps(
        {
            "mechanism": event["mechanism"],
            "strategy": event["strategy"],
            "applicability": event["applicability"],
            "failure_signature": event["failure_signature"],
            "counterexample": event["counterexample"],
        },
        ensure_ascii=False,
    )
    if any(pattern.search(shareable) for pattern in FORBIDDEN_PATTERNS):
        raise LearningError(
            "learning event contains project-specific or secret content"
        )


def validate_feedback(value: dict[str, Any]) -> None:
    missing = sorted(FEEDBACK_FIELDS - value.keys())
    if missing:
        raise LearningError(f"learning feedback missing fields: {missing}")
    if value.get("schema_version") != SCHEMA_VERSION:
        raise LearningError(f"learning feedback schema must be {SCHEMA_VERSION}")
    for field in ("feedback_id", "learning_id", "project_ref", "run_ref"):
        if not isinstance(value.get(field), str) or not value[field].strip():
            raise LearningError(f"feedback {field} must be non-empty")
    if value.get("outcome") not in {"supported", "contradicted", "not-applicable"}:
        raise LearningError("feedback outcome is unsupported")
    note = value.get("applicability_note")
    if not isinstance(note, str) or not note.strip():
        raise LearningError("feedback applicability_note must be non-empty")
    if any(pattern.search(note) for pattern in FORBIDDEN_PATTERNS):
        raise LearningError("learning feedback contains project-specific content")
    evidence = value.get("evidence_refs")
    if (
        not isinstance(evidence, list)
        or not evidence
        or any(not isinstance(item, str) or not item for item in evidence)
    ):
        raise LearningError("feedback evidence_refs must be a non-empty string list")


def anonymous_ref(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def identity_payload(event: dict[str, Any]) -> str:
    value = {
        "classification": event["classification"],
        "mechanism": event["mechanism"],
        "strategy": event["strategy"],
        "applicability": event["applicability"],
        "failure_signature": event["failure_signature"],
    }
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def conflict_payload(value: dict[str, Any]) -> str:
    """Return the semantic slot in which two different strategies conflict."""
    scope = {
        "classification": value["classification"],
        "mechanism": value["mechanism"],
        "applicability": value["applicability"],
        "failure_signature": value["failure_signature"],
    }
    return json.dumps(scope, ensure_ascii=False, sort_keys=True)


def learning_id(event: dict[str, Any]) -> str:
    digest = hashlib.sha256(identity_payload(event).encode("utf-8")).hexdigest()[:20]
    return f"learning-{digest}"


def record_path(root: Path, identifier: str) -> Path:
    return root / "records" / f"{identifier}.yaml"


def conflicting_records(
    root: Path, event: dict[str, Any], identifier: str
) -> list[tuple[Path, dict[str, Any]]]:
    records_root = root / "records"
    if not records_root.is_dir():
        return []
    expected_scope = conflict_payload(event)
    matches: list[tuple[Path, dict[str, Any]]] = []
    for path in records_root.glob("*.yaml"):
        record = read_yaml(path)
        if (
            record.get("learning_id") != identifier
            and record.get("status") != "retired"
            and all(
                field in record
                for field in (
                    "classification",
                    "mechanism",
                    "strategy",
                    "applicability",
                    "failure_signature",
                )
            )
            and conflict_payload(record) == expected_scope
            and record.get("strategy") != event.get("strategy")
        ):
            matches.append((path, record))
    return matches


def status_for(record: dict[str, Any]) -> str:
    projects = set(record.get("source_projects", []))
    runs = set(record.get("source_runs", []))
    challenges = int(record.get("counterexample_challenges", 0))
    if len(projects) >= 2 or (len(runs) >= 3 and challenges >= 1):
        return "generalized"
    if len(runs) >= 2:
        return "corroborated"
    return "observed"


def public_projection(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": record["schema_version"],
        "learning_id": record["learning_id"],
        "classification": record["classification"],
        "mechanism": record["mechanism"],
        "strategy": record["strategy"],
        "applicability": record["applicability"],
        "failure_signature": record["failure_signature"],
        "status": record["status"],
        "observation_count": record["observation_count"],
        "source_project_count": len(set(record.get("source_projects", []))),
        "source_run_count": len(set(record.get("source_runs", []))),
        "updated_at": record["updated_at"],
    }


def rebuild(root: Path) -> dict[str, Any]:
    records = []
    records_root = root / "records"
    if records_root.is_dir():
        for path in sorted(records_root.glob("*.yaml")):
            records.append(public_projection(read_yaml(path)))
    index = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": utc_now(),
        "records": records,
    }
    atomic_write_json(root / "index.json", index)
    return index


def command_ingest(args: argparse.Namespace) -> dict[str, Any]:
    root = learning_root(args.learning_root)
    event = read_json(Path(args.event).resolve())
    validate_event(event)
    identifier = learning_id(event)
    path = record_path(root, identifier)
    now = utc_now()
    project = anonymous_ref(event["project_ref"])
    run = anonymous_ref(f"{event['project_ref']}:{event['run_ref']}")
    observation = anonymous_ref(
        f"{event['project_ref']}:{event['run_ref']}:{event['event_id']}"
    )
    event_ref = anonymous_ref(event["event_id"])
    if path.is_file():
        record = read_yaml(path)
        if record.get("status") == "retired":
            raise LearningError(
                "retired learning must be superseded, not silently reactivated"
            )
        known_events = set(record.get("ingested_event_ids", []))
        if not known_events:
            event_log = root / "events" / "learning-events.jsonl"
            if event_log.is_file():
                for raw in event_log.read_text(encoding="utf-8").splitlines():
                    try:
                        prior = json.loads(raw)
                    except json.JSONDecodeError:
                        continue
                    if prior.get("learning_id") == identifier and prior.get("event_id"):
                        known_events.add(str(prior["event_id"]))
        is_new_observation = event_ref not in known_events
        known_events.add(event_ref)
        record["ingested_event_ids"] = sorted(known_events)
        observations = set(record.get("observations", []))
        if not observations and int(record.get("observation_count", 0)):
            observations = {
                f"legacy-observation-{index}"
                for index in range(int(record["observation_count"]))
            }
        if is_new_observation:
            observations.add(observation)
        record["observations"] = sorted(observations)
        record["observation_count"] = len(observations)
        record["source_projects"] = sorted(
            set(record.get("source_projects", [])) | {project}
        )
        if is_new_observation:
            record["source_runs"] = sorted(set(record.get("source_runs", [])) | {run})
        if event.get("counterexample") and is_new_observation:
            record["counterexample_challenges"] = (
                int(record.get("counterexample_challenges", 0)) + 1
            )
        record["updated_at"] = now
        if record.get("status") not in {"degraded", "retired"}:
            record["status"] = status_for(record)
    else:
        conflicts = conflicting_records(root, event, identifier)
        record = {
            "schema_version": SCHEMA_VERSION,
            "learning_id": identifier,
            "classification": event["classification"],
            "mechanism": event["mechanism"],
            "strategy": event["strategy"],
            "applicability": event["applicability"],
            "failure_signature": event["failure_signature"],
            "status": "degraded" if conflicts else "observed",
            "observation_count": 1,
            "source_projects": [project],
            "source_runs": [run],
            "observations": [observation],
            "ingested_event_ids": [event_ref],
            "counterexample_challenges": 1 if event.get("counterexample") else 0,
            "created_at": now,
            "updated_at": now,
            "superseded_by": None,
            "conflicts_with": sorted(
                str(item.get("learning_id")) for _path, item in conflicts
            ),
        }
        for conflict_path, conflict in conflicts:
            identifiers = set(conflict.get("conflicts_with", [])) | {identifier}
            conflict["conflicts_with"] = sorted(identifiers)
            conflict["status"] = "degraded"
            conflict["updated_at"] = now
            atomic_write_yaml(conflict_path, conflict)
            append_jsonl(
                root / "events" / "learning-events.jsonl",
                {
                    "schema_version": SCHEMA_VERSION,
                    "event": "conflict-detected",
                    "learning_id": str(conflict["learning_id"]),
                    "conflicts_with": identifier,
                    "recorded_at": now,
                },
            )
    atomic_write_yaml(path, record)
    append_jsonl(
        root / "events" / "learning-events.jsonl",
        {
            "schema_version": SCHEMA_VERSION,
            "event": "ingested",
            "event_id": anonymous_ref(event["event_id"]),
            "learning_id": identifier,
            "project_ref": project,
            "run_ref": run,
            "recorded_at": now,
        },
    )
    rebuild(root)
    return public_projection(record)


def find_record(root: Path, identifier: str) -> tuple[Path, dict[str, Any]]:
    path = record_path(root, identifier)
    if not path.is_file():
        raise LearningError(f"unknown learning_id: {identifier}")
    return path, read_yaml(path)


def command_transition(args: argparse.Namespace) -> dict[str, Any]:
    root = learning_root(args.learning_root)
    path, record = find_record(root, args.learning_id)
    if record.get("status") == "retired" and args.status != "retired":
        raise LearningError("retired learning cannot be reactivated")
    if args.status in {"corroborated", "generalized"}:
        eligible = status_for(record)
        allowed = (
            {"corroborated", "generalized"}
            if args.status == "corroborated"
            else {"generalized"}
        )
        if eligible not in allowed:
            raise LearningError(
                f"{args.status} transition lacks independent observations"
            )
        if record.get("conflicts_with"):
            raise LearningError(
                f"{args.status} transition requires conflicts to be resolved"
            )
    prior = record["status"]
    record["status"] = args.status
    record["updated_at"] = utc_now()
    record["last_transition"] = {
        "from": prior,
        "to": args.status,
        "reason": args.reason,
        "at": utc_now(),
    }
    if args.status == "retired":
        tombstone = {
            "schema_version": SCHEMA_VERSION,
            "learning_id": args.learning_id,
            "retired_at": utc_now(),
            "reason": args.reason,
        }
        atomic_write_yaml(root / "tombstones" / f"{args.learning_id}.yaml", tombstone)
        records_root = root / "records"
        if records_root.is_dir():
            for other_path in records_root.glob("*.yaml"):
                if other_path == path:
                    continue
                other = read_yaml(other_path)
                conflicts = set(other.get("conflicts_with", []))
                if args.learning_id not in conflicts:
                    continue
                conflicts.remove(args.learning_id)
                other["conflicts_with"] = sorted(conflicts)
                counts = other.get("feedback_counts", {})
                contradicted = (
                    int(counts.get("contradicted", 0))
                    if isinstance(counts, dict)
                    else 0
                )
                not_applicable = (
                    int(counts.get("not-applicable", 0))
                    if isinstance(counts, dict)
                    else 0
                )
                if not conflicts and contradicted == 0 and not_applicable == 0:
                    other["status"] = status_for(other)
                other["updated_at"] = utc_now()
                atomic_write_yaml(other_path, other)
    atomic_write_yaml(path, record)
    rebuild(root)
    return public_projection(record)


def command_feedback(args: argparse.Namespace) -> dict[str, Any]:
    root = learning_root(args.learning_root)
    feedback = read_json(Path(args.feedback).resolve())
    validate_feedback(feedback)
    path, record = find_record(root, str(feedback["learning_id"]))
    if record.get("status") == "retired":
        raise LearningError("retired learning cannot receive runtime feedback")
    feedback_ref = anonymous_ref(str(feedback["feedback_id"]))
    known = set(record.get("feedback_ids", []))
    if feedback_ref in known:
        return public_projection(record)
    known.add(feedback_ref)
    record["feedback_ids"] = sorted(known)
    outcome = str(feedback["outcome"])
    counts = record.setdefault(
        "feedback_counts",
        {"supported": 0, "contradicted": 0, "not-applicable": 0},
    )
    for name in ("supported", "contradicted", "not-applicable"):
        counts.setdefault(name, 0)
    counts[outcome] = int(counts[outcome]) + 1
    evidence_hashes = [anonymous_ref(str(item)) for item in feedback["evidence_refs"]]
    history = record.setdefault("feedback_history", [])
    history.append(
        {
            "feedback_id": feedback_ref,
            "project_ref": anonymous_ref(str(feedback["project_ref"])),
            "run_ref": anonymous_ref(
                f"{feedback['project_ref']}:{feedback['run_ref']}"
            ),
            "outcome": outcome,
            "applicability_note": feedback["applicability_note"],
            "evidence_refs": evidence_hashes,
            "recorded_at": utc_now(),
        }
    )
    if outcome in {"contradicted", "not-applicable"}:
        record["status"] = "degraded"
    if outcome == "not-applicable":
        exclusions = record.setdefault("applicability_exclusions", [])
        if feedback["applicability_note"] not in exclusions:
            exclusions.append(feedback["applicability_note"])
    record["updated_at"] = utc_now()
    atomic_write_yaml(path, record)
    append_jsonl(
        root / "events" / "learning-events.jsonl",
        {
            "schema_version": SCHEMA_VERSION,
            "event": "feedback",
            "feedback_id": feedback_ref,
            "learning_id": record["learning_id"],
            "outcome": outcome,
            "project_ref": anonymous_ref(str(feedback["project_ref"])),
            "run_ref": anonymous_ref(
                f"{feedback['project_ref']}:{feedback['run_ref']}"
            ),
            "recorded_at": utc_now(),
        },
    )
    rebuild(root)
    return public_projection(record)


def command_search(args: argparse.Namespace) -> dict[str, Any]:
    root = learning_root(args.learning_root)
    terms = [term for term in args.query.lower().split() if term]
    matches: list[tuple[int, dict[str, Any]]] = []
    records_root = root / "records"
    if records_root.is_dir():
        for path in records_root.glob("*.yaml"):
            record = read_yaml(path)
            if record.get("status") == "retired" and not args.include_retired:
                continue
            text = json.dumps(record, ensure_ascii=False, sort_keys=True).lower()
            score = sum(text.count(term) for term in terms)
            if score:
                matches.append((score, public_projection(record)))
    matches.sort(key=lambda item: (-item[0], item[1]["learning_id"]))
    return {
        "query": args.query,
        "matches": [{"score": score, **item} for score, item in matches],
    }


def command_rebuild(args: argparse.Namespace) -> dict[str, Any]:
    index = rebuild(learning_root(args.learning_root))
    return {"valid": True, "record_count": len(index["records"])}


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(
        description="Manage the shared test learning library."
    )
    commands = root.add_subparsers(dest="command", required=True)
    ingest = commands.add_parser("ingest")
    ingest.add_argument("--learning-root")
    ingest.add_argument("--event", required=True)
    search = commands.add_parser("search")
    search.add_argument("--learning-root")
    search.add_argument("--query", required=True)
    search.add_argument("--include-retired", action="store_true")
    transition = commands.add_parser("transition")
    transition.add_argument("--learning-root")
    transition.add_argument("--learning-id", required=True)
    transition.add_argument("--status", choices=sorted(STATUSES), required=True)
    transition.add_argument("--reason", required=True)
    feedback = commands.add_parser("feedback")
    feedback.add_argument("--learning-root")
    feedback.add_argument("--feedback", required=True)
    rebuild_command = commands.add_parser("rebuild")
    rebuild_command.add_argument("--learning-root")
    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        commands = {
            "ingest": command_ingest,
            "search": command_search,
            "transition": command_transition,
            "feedback": command_feedback,
            "rebuild": command_rebuild,
        }
        value = commands[args.command](args)
        print(json.dumps(value, ensure_ascii=False, indent=2))
        return 0
    except LearningError as exc:
        print(f"ERROR {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
