from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml


SCHEMA_VERSION = "vnext-2"
CACHE_PARTS = {"__pycache__", ".pytest_cache", ".ruff_cache"}


class ImprovementError(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def atomic_write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    os.replace(temporary, path)


def atomic_write_yaml(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(
        yaml.safe_dump(value, allow_unicode=True, sort_keys=False), encoding="utf-8"
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
        raise ImprovementError(f"cannot read JSON {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ImprovementError(f"JSON root must be an object: {path}")
    return value


def read_yaml(path: Path) -> dict[str, Any]:
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ImprovementError(f"cannot read YAML {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ImprovementError(f"YAML root must be an object: {path}")
    return value


def member_names(skill_group_root: Path) -> list[str]:
    manifest = read_json(
        skill_group_root / "clarify-before-testing" / "references" / "skill-group.json"
    )
    members = manifest.get("members")
    if not isinstance(members, dict) or not members:
        raise ImprovementError("Skill group manifest has no members")
    return sorted(str(name) for name in members)


def skill_group_digest(skill_group_root: Path) -> str:
    root = skill_group_root.resolve()
    files: list[Path] = []
    for name in member_names(root):
        member = root / name
        if not member.is_dir():
            raise ImprovementError(f"Skill group member is missing: {name}")
        files.extend(
            path
            for path in member.rglob("*")
            if path.is_file()
            and path.suffix.lower() in {".py", ".md", ".yaml", ".yml", ".json"}
            and not any(part in CACHE_PARTS for part in path.parts)
        )
    aggregate = hashlib.sha256()
    for path in sorted(set(files)):
        relative = path.relative_to(root).as_posix()
        aggregate.update(relative.encode("utf-8"))
        aggregate.update(b"\0")
        aggregate.update(hashlib.sha256(path.read_bytes()).hexdigest().encode("ascii"))
        aggregate.update(b"\n")
    return f"sha256:{aggregate.hexdigest()}"


def run_process(command: list[str]) -> dict[str, Any]:
    result = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )
    return {
        "command": command,
        "returncode": result.returncode,
        "stdout_tail": result.stdout[-4000:],
        "stderr_tail": result.stderr[-4000:],
    }


def command_regress(args: argparse.Namespace) -> dict[str, Any]:
    group_root = Path(args.skill_group_root).resolve()
    output = Path(args.output).resolve()
    before = skill_group_digest(group_root)
    validator = (
        group_root / "clarify-before-testing" / "scripts" / "validate_skill_group.py"
    )
    validation = run_process(
        [
            sys.executable,
            "-B",
            "-X",
            "utf8",
            str(validator),
            "--group-root",
            str(group_root),
            "--strict-package",
        ]
    )
    test_roots = [
        str(group_root / name / "tests")
        for name in member_names(group_root)
        if (group_root / name / "tests").is_dir()
    ]
    if not test_roots:
        raise ImprovementError("Skill group has no regression tests")
    tests = run_process(
        [
            sys.executable,
            "-B",
            "-X",
            "utf8",
            "-m",
            "pytest",
            "-q",
            "-p",
            "no:cacheprovider",
            *test_roots,
        ]
    )
    after = skill_group_digest(group_root)
    report = {
        "schema_version": SCHEMA_VERSION,
        "report_type": "core-skill-regression-baseline",
        "generated_at": utc_now(),
        "skill_group_digest_before": before,
        "skill_group_digest_after": after,
        "skill_group_unchanged": before == after,
        "validation": validation,
        "tests": tests,
        "passed": validation["returncode"] == 0
        and tests["returncode"] == 0
        and before == after,
    }
    atomic_write_json(output, report)
    if not report["passed"]:
        raise ImprovementError(f"Skill group regression failed; see {output}")
    return report


def generalized_records(
    learning_root: Path, selected_ids: list[str]
) -> list[dict[str, Any]]:
    records_root = learning_root / "records"
    if not records_root.is_dir():
        raise ImprovementError("shared learning library has no records")
    selected = set(selected_ids)
    records: list[dict[str, Any]] = []
    for path in sorted(records_root.glob("*.yaml")):
        value = read_yaml(path)
        identifier = str(value.get("learning_id") or "")
        if selected and identifier not in selected:
            continue
        if value.get("status") == "generalized":
            records.append(value)
        elif identifier in selected:
            raise ImprovementError(
                f"core Skill proposals require generalized learning: {identifier}"
            )
    missing = selected - {str(item.get("learning_id")) for item in records}
    if missing:
        raise ImprovementError(f"unknown selected learning IDs: {sorted(missing)}")
    if not records:
        raise ImprovementError("no generalized shared learning is eligible")
    return records


def command_propose(args: argparse.Namespace) -> dict[str, Any]:
    learning_root = Path(args.learning_root).expanduser().resolve()
    group_root = Path(args.skill_group_root).resolve()
    regression_path = Path(args.regression_report).resolve()
    regression = read_json(regression_path)
    current_digest = skill_group_digest(group_root)
    if (
        regression.get("schema_version") != SCHEMA_VERSION
        or regression.get("report_type") != "core-skill-regression-baseline"
        or regression.get("passed") is not True
        or regression.get("skill_group_unchanged") is not True
        or regression.get("skill_group_digest_after") != current_digest
    ):
        raise ImprovementError(
            "proposal requires a passing regression report for the current Skill group"
        )
    records = generalized_records(learning_root, list(args.learning_id or []))
    learning_ids = sorted(str(item["learning_id"]) for item in records)
    identity = json.dumps(
        {"learning_ids": learning_ids, "skill_group_digest": current_digest},
        sort_keys=True,
    )
    proposal_id = (
        "skill-proposal-" + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:20]
    )
    proposal = {
        "schema_version": SCHEMA_VERSION,
        "proposal_id": proposal_id,
        "status": "pending-human-confirmation",
        "created_at": utc_now(),
        "learning_ids": learning_ids,
        "learning_inputs": [
            {
                "learning_id": item["learning_id"],
                "classification": item["classification"],
                "mechanism": item["mechanism"],
                "strategy": item["strategy"],
                "applicability": item["applicability"],
            }
            for item in records
        ],
        "skill_group_digest": current_digest,
        "regression_report_ref": str(regression_path),
        "required_decision_type": "core-skill-change",
        "required_decision_effect": "grant",
        "publication_performed": False,
        "next_action": (
            "Human reviews scope, wording, safety impact, and regression evidence; "
            "only a granted core-skill-change decision may authorize a separate "
            "implementation and publication task."
        ),
    }
    target = learning_root / "proposals" / f"{proposal_id}.yaml"
    if target.is_file():
        existing = read_yaml(target)
        if existing.get("skill_group_digest") != current_digest:
            raise ImprovementError(
                "existing proposal conflicts with current Skill group"
            )
        return proposal
    atomic_write_yaml(target, proposal)
    append_jsonl(
        learning_root / "events" / "skill-improvement-events.jsonl",
        {
            "schema_version": SCHEMA_VERSION,
            "event": "proposal-created",
            "proposal_id": proposal_id,
            "learning_ids": learning_ids,
            "recorded_at": utc_now(),
        },
    )
    return proposal


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(
        description="Generate regression-bound core Skill improvement proposals."
    )
    commands = root.add_subparsers(dest="command", required=True)
    regress = commands.add_parser("regress")
    regress.add_argument("--skill-group-root", required=True)
    regress.add_argument("--output", required=True)
    propose = commands.add_parser("propose")
    propose.add_argument("--learning-root", required=True)
    propose.add_argument("--skill-group-root", required=True)
    propose.add_argument("--regression-report", required=True)
    propose.add_argument("--learning-id", action="append")
    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        value = (
            command_regress(args)
            if args.command == "regress"
            else command_propose(args)
        )
        print(json.dumps(value, ensure_ascii=False, indent=2))
        return 0
    except ImprovementError as exc:
        print(f"ERROR {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
