from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml


SCHEMA_VERSION = "vnext-2"
ASSET_RELATIVE = Path("project-context") / "operation-assets"
STATUSES = {"candidate", "verified", "stable", "degraded", "retired"}
ASSET_TYPES = {
    "authentication",
    "navigation",
    "dynamic-configuration",
    "component-interaction",
    "business-mutation",
    "business-verification",
    "data-preparation",
    "cleanup",
}
REQUIRED_FIELDS = {
    "schema_version",
    "asset_id",
    "semantic_name",
    "asset_type",
    "intent",
    "status",
    "version",
    "environments",
    "roles",
    "components",
    "business_states",
    "proof_scope",
    "compatibility_fingerprint",
    "source_runs",
    "last_verified_at",
    "lifecycle_history",
}
REQUIRED_HEADINGS = {
    "Purpose and supported inputs",
    "Applicability",
    "Non-applicability",
    "Dynamic-value resolution",
    "Preconditions",
    "Preferred user-level strategy",
    "Proof scope and evidence",
    "Failure signatures and recovery",
    "Sensitive references",
    "Validation and lifecycle history",
}
SECRET_PATTERNS = (
    re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]{16,}", re.IGNORECASE),
    re.compile(r"\beyJ[A-Za-z0-9_-]{12,}\.[A-Za-z0-9_-]{12,}\.[A-Za-z0-9_-]{12,}\b"),
    re.compile(
        r"""(?ix)
        \b(password|passwd|token|secret|authorization|api[_-]?key)\b
        \s*[:=]\s*
        ["']?[A-Za-z0-9._~+/=-]{16,}["']?
        """
    ),
)


class AssetError(RuntimeError):
    pass


@dataclass(frozen=True)
class Asset:
    path: Path
    frontmatter: dict[str, Any]
    body: str
    digest: str

    def projection(self) -> dict[str, Any]:
        fields = (
            "asset_id",
            "semantic_name",
            "asset_type",
            "intent",
            "status",
            "version",
            "environments",
            "roles",
            "components",
            "business_states",
            "proof_scope",
            "compatibility_fingerprint",
            "source_runs",
            "last_verified_at",
            "lifecycle_history",
        )
        value = {field: self.frontmatter.get(field) for field in fields}
        value["path"] = self.path.name
        value["digest"] = self.digest
        return value


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def atomic_write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def atomic_write_asset(path: Path, frontmatter: dict[str, Any], body: str) -> None:
    rendered = (
        "---\n"
        + yaml.safe_dump(frontmatter, allow_unicode=True, sort_keys=False)
        + "---\n"
        + body
    )
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(rendered, encoding="utf-8")
    os.replace(temporary, path)


def parse_asset(path: Path) -> Asset:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise AssetError(f"cannot read {path}: {exc}") from exc
    match = re.match(r"\A---\s*\n(.*?)\n---\s*\n(.*)\Z", text, re.DOTALL)
    if match is None:
        raise AssetError(f"{path.name}: missing YAML frontmatter")
    try:
        frontmatter = yaml.safe_load(match.group(1))
    except yaml.YAMLError as exc:
        raise AssetError(f"{path.name}: invalid YAML: {exc}") from exc
    if not isinstance(frontmatter, dict):
        raise AssetError(f"{path.name}: frontmatter must be an object")
    return Asset(
        path=path,
        frontmatter=frontmatter,
        body=match.group(2),
        digest=hashlib.sha256(text.encode("utf-8")).hexdigest(),
    )


def asset_root(project_root: Path) -> Path:
    return project_root.resolve() / ASSET_RELATIVE


def load_assets(project_root: Path) -> list[Asset]:
    root = asset_root(project_root)
    if not root.is_dir():
        return []
    assets: list[Asset] = []
    for path in sorted(root.glob("*.md")):
        assets.append(parse_asset(path))
    return assets


def string_list(value: Any, field: str, errors: list[str], asset_id: str) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        errors.append(f"{asset_id}: {field} must be a list of strings")
        return []
    return value


def validate_asset(asset: Asset) -> list[str]:
    errors: list[str] = []
    data = asset.frontmatter
    asset_id = str(data.get("asset_id", asset.path.stem))
    missing = sorted(REQUIRED_FIELDS - data.keys())
    if missing:
        errors.append(f"{asset_id}: missing fields {missing}")
    if data.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"{asset_id}: schema_version must be {SCHEMA_VERSION}")
    if data.get("asset_id") != asset.path.stem:
        errors.append(f"{asset_id}: file stem must equal asset_id")
    if data.get("status") not in STATUSES:
        errors.append(f"{asset_id}: unsupported status {data.get('status')!r}")
    if data.get("asset_type") not in ASSET_TYPES:
        errors.append(f"{asset_id}: unsupported asset_type {data.get('asset_type')!r}")
    if not isinstance(data.get("version"), int) or data.get("version", 0) < 1:
        errors.append(f"{asset_id}: version must be a positive integer")
    if not isinstance(data.get("lifecycle_history"), list):
        errors.append(f"{asset_id}: lifecycle_history must be a list")
    for field in (
        "environments",
        "roles",
        "components",
        "business_states",
        "proof_scope",
        "source_runs",
    ):
        string_list(data.get(field), field, errors, asset_id)
    if not isinstance(data.get("compatibility_fingerprint"), dict):
        errors.append(f"{asset_id}: compatibility_fingerprint must be an object")
    headings = set(re.findall(r"^##\s+(.+?)\s*$", asset.body, re.MULTILINE))
    missing_headings = sorted(REQUIRED_HEADINGS - headings)
    if missing_headings:
        errors.append(f"{asset_id}: missing headings {missing_headings}")
    if any(pattern.search(asset.body) for pattern in SECRET_PATTERNS):
        errors.append(f"{asset_id}: possible plaintext secret in body")
    serialized = json.dumps(data, ensure_ascii=False)
    if any(pattern.search(serialized) for pattern in SECRET_PATTERNS):
        errors.append(f"{asset_id}: possible plaintext secret in frontmatter")
    return errors


def validate_all(project_root: Path) -> tuple[list[Asset], list[str]]:
    try:
        assets = load_assets(project_root)
    except AssetError as exc:
        return [], [str(exc)]
    errors: list[str] = []
    seen: set[str] = set()
    for asset in assets:
        errors.extend(validate_asset(asset))
        asset_id = str(asset.frontmatter.get("asset_id"))
        if asset_id in seen:
            errors.append(f"duplicate asset_id: {asset_id}")
        seen.add(asset_id)
    return assets, errors


def command_validate(project_root: Path) -> dict[str, Any]:
    assets, errors = validate_all(project_root)
    if errors:
        raise AssetError("; ".join(errors))
    return {"valid": True, "asset_count": len(assets)}


def command_rebuild(project_root: Path) -> dict[str, Any]:
    assets, errors = validate_all(project_root)
    if errors:
        raise AssetError("; ".join(errors))
    projection = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": utc_now(),
        "assets": [asset.projection() for asset in assets],
    }
    atomic_write_json(asset_root(project_root) / "index.json", projection)
    return {
        "rebuilt": True,
        "asset_count": len(assets),
        "index": str((asset_root(project_root) / "index.json").resolve()),
    }


def contains(value: Any, query: str) -> bool:
    if not query:
        return True
    if isinstance(value, list):
        return any(query in str(item).lower() for item in value)
    return query in str(value).lower()


def search_score(asset: Asset, intent: str) -> int:
    query = intent.strip().lower()
    if not query:
        return 0
    data = asset.frontmatter
    score = 0
    if query == str(data.get("intent", "")).lower():
        score += 10
    for field, weight in (
        ("semantic_name", 6),
        ("intent", 5),
        ("asset_type", 3),
        ("proof_scope", 2),
    ):
        if contains(data.get(field), query):
            score += weight
    if query in asset.body.lower():
        score += 1
    return score


def command_search(args: argparse.Namespace) -> dict[str, Any]:
    assets, errors = validate_all(Path(args.project_root))
    if errors:
        raise AssetError("; ".join(errors))
    matches: list[tuple[int, Asset]] = []
    for asset in assets:
        data = asset.frontmatter
        if data.get("status") == "retired" and not args.include_retired:
            continue
        if args.status and data.get("status") != args.status:
            continue
        if args.environment and not contains(
            data.get("environments"), args.environment.lower()
        ):
            continue
        if args.role and not contains(data.get("roles"), args.role.lower()):
            continue
        if args.component and not contains(
            data.get("components"), args.component.lower()
        ):
            continue
        score = search_score(asset, args.intent)
        if args.intent and score == 0:
            continue
        matches.append((score, asset))
    matches.sort(
        key=lambda item: (
            -item[0],
            str(item[1].frontmatter.get("last_verified_at") or ""),
            str(item[1].frontmatter.get("asset_id")),
        )
    )
    return {
        "query": {
            "intent": args.intent,
            "environment": args.environment,
            "role": args.role,
            "component": args.component,
            "status": args.status,
        },
        "matches": [{"score": score, **asset.projection()} for score, asset in matches],
    }


def command_transition(args: argparse.Namespace) -> dict[str, Any]:
    project_root = Path(args.project_root).resolve()
    matches = [
        asset
        for asset in load_assets(project_root)
        if asset.frontmatter.get("asset_id") == args.asset_id
    ]
    if len(matches) != 1:
        raise AssetError(
            f"asset id does not identify exactly one operation asset: {args.asset_id}"
        )
    asset = matches[0]
    data = dict(asset.frontmatter)
    prior = str(data.get("status"))
    if prior == "retired" and args.status != "retired":
        raise AssetError("retired operation assets require a successor")
    now = utc_now()
    data["status"] = args.status
    data["version"] = int(data.get("version", 0)) + 1
    data.setdefault("lifecycle_history", []).append(
        {
            "at": now,
            "event": "transition",
            "from": prior,
            "to": args.status,
            "reason": args.reason,
        }
    )
    if args.status in {"verified", "stable"}:
        data["last_verified_at"] = now
    if args.status == "retired":
        data["tombstone"] = {"retired_at": now, "reason": args.reason}
    candidate_text = (
        "---\n"
        + yaml.safe_dump(data, allow_unicode=True, sort_keys=False)
        + "---\n"
        + asset.body
    )
    candidate = Asset(
        path=asset.path,
        frontmatter=data,
        body=asset.body,
        digest=hashlib.sha256(candidate_text.encode("utf-8")).hexdigest(),
    )
    errors = validate_asset(candidate)
    if errors:
        raise AssetError("; ".join(errors))
    atomic_write_asset(asset.path, data, asset.body)
    command_rebuild(project_root)
    return parse_asset(asset.path).projection()


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description="Validate and search operation assets.")
    commands = root.add_subparsers(dest="command", required=True)
    for name in ("validate", "rebuild"):
        command = commands.add_parser(name)
        command.add_argument("--project-root", required=True)
    search = commands.add_parser("search")
    search.add_argument("--project-root", required=True)
    search.add_argument("--intent", default="")
    search.add_argument("--environment", default="")
    search.add_argument("--role", default="")
    search.add_argument("--component", default="")
    search.add_argument("--status", choices=sorted(STATUSES))
    search.add_argument("--include-retired", action="store_true")
    transition = commands.add_parser("transition")
    transition.add_argument("--project-root", required=True)
    transition.add_argument("--asset-id", required=True)
    transition.add_argument("--status", choices=sorted(STATUSES), required=True)
    transition.add_argument("--reason", required=True)
    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        project_root = Path(args.project_root).resolve()
        if args.command == "validate":
            value = command_validate(project_root)
        elif args.command == "rebuild":
            value = command_rebuild(project_root)
        elif args.command == "search":
            value = command_search(args)
        else:
            value = command_transition(args)
        print(json.dumps(value, ensure_ascii=False, indent=2))
        return 0
    except AssetError as exc:
        print(f"ERROR {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
