from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml


SCHEMA_VERSION = "vnext-2"
ASSET_DIRS = {
    "dom-map": "dom-maps",
    "automation": "automation-assets",
    "data-recipe": "data-recipes",
    "regression": "regression-assets",
}
STATUSES = {"candidate", "verified", "stable", "degraded", "retired"}
COMMON_FIELDS = {
    "schema_version",
    "asset_type",
    "asset_id",
    "version",
    "status",
    "semantic_name",
    "source_runs",
    "evidence_refs",
    "validation_history",
}
TYPE_FIELDS = {
    "dom-map": {"route_pattern", "framework", "page_fingerprint", "elements"},
    "automation": {
        "code_path",
        "code_digest",
        "case_ids",
        "oracle_refs",
        "actor_refs",
        "data_contract_refs",
        "dom_asset_refs",
        "operation_asset_refs",
        "validation_runs",
        "unknown_effects",
        "cleanup_failures",
        "secret_findings",
    },
    "data-recipe": {
        "contract_id",
        "provision_channel",
        "verify_steps",
        "cleanup_steps",
        "reconcile_steps",
        "actor_refs",
    },
    "regression": {
        "defect_ref",
        "condition_refs",
        "reproduction",
        "expected",
        "actual",
        "verification_requirements",
    },
}
DOM_ELEMENT_FIELDS = {
    "element_id",
    "name",
    "component_type",
    "container",
    "primary_locator",
    "fallback_locators",
    "readiness",
    "dependencies",
}
SECRET_PATTERNS = (
    re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]{12,}", re.IGNORECASE),
    # Value must be quoted or contain a token-ish char; bare Python
    # identifiers (e.g. `password = require_credentials`) are false positives.
    re.compile(
        r"(?i)['\"]?\b(password|passwd|token|secret|authorization|api[_-]?key)\b"
        r"['\"]?\s*[:=]\s*(?:"
        r"['\"]([^'\"]{12,})['\"]"
        r"|([A-Za-z0-9._~+/=-]{12,}[~+/=-][A-Za-z0-9._~+/=-]*)"
        r")"
    ),
)
SECRET_SCAN_SUFFIXES = {".py", ".json", ".ini", ".yaml", ".yml", ".toml", ".md"}


class AssetError(RuntimeError):
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


def read_yaml(path: Path) -> dict[str, Any]:
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise AssetError(f"cannot read YAML {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise AssetError(f"YAML root must be an object: {path}")
    return value


def inside(base: Path, candidate: Path) -> Path:
    base = base.resolve()
    candidate = candidate.resolve()
    try:
        candidate.relative_to(base)
    except ValueError as exc:
        raise AssetError(f"path escapes {base}: {candidate}") from exc
    return candidate


def project_context(project_root: Path) -> Path:
    return project_root.resolve() / "project-context"


def iter_assets(project_root: Path) -> list[tuple[Path, dict[str, Any]]]:
    assets: list[tuple[Path, dict[str, Any]]] = []
    context = project_context(project_root)
    for directory in ASSET_DIRS.values():
        root = context / directory
        if not root.is_dir():
            continue
        for path in sorted(root.glob("*.yaml")):
            assets.append((path, read_yaml(path)))
    return assets


def non_empty_string_list(
    value: Any, field: str, errors: list[str], *, allow_empty: bool = False
) -> None:
    if (
        not isinstance(value, list)
        or (not allow_empty and not value)
        or any(not isinstance(item, str) or not item.strip() for item in value)
    ):
        errors.append(f"{field} must be a list of non-empty strings")


def validate_dom_elements(value: Any, errors: list[str]) -> None:
    if not isinstance(value, list) or not value:
        errors.append("elements must be a non-empty list")
        return
    seen: set[str] = set()
    for index, element in enumerate(value):
        if not isinstance(element, dict):
            errors.append(f"elements[{index}] must be an object")
            continue
        missing = sorted(DOM_ELEMENT_FIELDS - element.keys())
        if missing:
            errors.append(f"elements[{index}] missing fields {missing}")
        element_id = element.get("element_id")
        if not isinstance(element_id, str) or not element_id:
            errors.append(f"elements[{index}].element_id must be non-empty")
        elif element_id in seen:
            errors.append(f"duplicate element_id: {element_id}")
        else:
            seen.add(element_id)
        non_empty_string_list(
            element.get("fallback_locators"),
            f"elements[{index}].fallback_locators",
            errors,
            allow_empty=True,
        )
        non_empty_string_list(
            element.get("readiness"), f"elements[{index}].readiness", errors
        )
        non_empty_string_list(
            element.get("dependencies"),
            f"elements[{index}].dependencies",
            errors,
            allow_empty=True,
        )


def validate_automation(asset: dict[str, Any], errors: list[str]) -> None:
    code_path = asset.get("code_path")
    if not isinstance(code_path, str) or not code_path.strip():
        errors.append("code_path must be a non-empty project-relative path")
    else:
        candidate = Path(code_path)
        if (
            candidate.is_absolute()
            or ".." in candidate.parts
            or candidate.parts[0] != "automation"
        ):
            errors.append("code_path must stay inside the project automation directory")
    if not isinstance(asset.get("code_digest"), str) or not re.fullmatch(
        r"sha256:[0-9a-f]{64}", str(asset.get("code_digest"))
    ):
        errors.append("code_digest must be a sha256 digest")
    for field in (
        "case_ids",
        "oracle_refs",
        "actor_refs",
        "data_contract_refs",
        "dom_asset_refs",
        "operation_asset_refs",
        "source_runs",
        "evidence_refs",
    ):
        non_empty_string_list(asset.get(field), field, errors)
    for field in (
        "validation_runs",
        "unknown_effects",
        "cleanup_failures",
        "secret_findings",
        "validation_history",
    ):
        if not isinstance(asset.get(field), list):
            errors.append(f"{field} must be a list")


def validate_asset(path: Path, asset: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    asset_id = str(asset.get("asset_id", path.stem))
    asset_type = asset.get("asset_type")
    if asset.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION}")
    if asset_type not in ASSET_DIRS:
        errors.append(f"unsupported asset_type: {asset_type}")
        return [f"{asset_id}: {error}" for error in errors]
    missing = sorted((COMMON_FIELDS | TYPE_FIELDS[str(asset_type)]) - asset.keys())
    if missing:
        errors.append(f"missing fields {missing}")
    if path.stem != asset_id:
        errors.append("file stem must equal asset_id")
    if asset.get("status") not in STATUSES:
        errors.append(f"unsupported status: {asset.get('status')}")
    if not isinstance(asset.get("version"), int) or asset.get("version", 0) < 1:
        errors.append("version must be a positive integer")
    for field in ("source_runs", "evidence_refs"):
        non_empty_string_list(asset.get(field), field, errors)
    if not isinstance(asset.get("validation_history"), list):
        errors.append("validation_history must be a list")
    if asset_type == "dom-map":
        if not isinstance(asset.get("page_fingerprint"), dict):
            errors.append("page_fingerprint must be an object")
        validate_dom_elements(asset.get("elements"), errors)
    elif asset_type == "automation":
        validate_automation(asset, errors)
    elif asset_type == "data-recipe":
        if asset.get("provision_channel") not in {"api", "ui-fallback"}:
            errors.append("provision_channel must be api or ui-fallback")
        for field in ("verify_steps", "cleanup_steps", "reconcile_steps", "actor_refs"):
            non_empty_string_list(asset.get(field), field, errors)
    elif asset_type == "regression":
        for field in ("condition_refs", "verification_requirements"):
            non_empty_string_list(asset.get(field), field, errors)
    serialized = yaml.safe_dump(asset, allow_unicode=True)
    if any(pattern.search(serialized) for pattern in SECRET_PATTERNS):
        errors.append("possible plaintext secret")
    return [f"{asset_id}: {error}" for error in errors]


def validate_all(
    project_root: Path,
) -> tuple[list[tuple[Path, dict[str, Any]]], list[str]]:
    assets = iter_assets(project_root)
    errors: list[str] = []
    seen: set[str] = set()
    for path, asset in assets:
        errors.extend(validate_asset(path, asset))
        asset_id = str(asset.get("asset_id"))
        if asset_id in seen:
            errors.append(f"duplicate asset_id: {asset_id}")
        seen.add(asset_id)
    asset_by_id = {
        str(asset.get("asset_id")): asset
        for _path, asset in assets
        if isinstance(asset.get("asset_id"), str)
    }
    for _path, asset in assets:
        if asset.get("asset_type") == "automation":
            errors.extend(
                validate_automation_dependencies(project_root, asset, asset_by_id)
            )
            code_path = asset.get("code_path")
            if isinstance(code_path, str):
                code_root = project_root.resolve() / code_path
                if code_root.is_dir():
                    try:
                        observed = automation_code_digest(code_root)
                    except AssetError as exc:
                        errors.append(str(exc))
                    else:
                        if observed != asset.get("code_digest"):
                            errors.append(
                                f"{asset.get('asset_id')}: code_digest differs from "
                                "the installed automation code"
                            )
    return assets, errors


def versioned_ref(value: Any, field: str) -> tuple[str, int]:
    if not isinstance(value, str):
        raise AssetError(f"{field} must be a versioned asset reference")
    match = re.fullmatch(r"(.+)@(\d+)", value)
    if not match:
        raise AssetError(f"{field} must use asset-id@version")
    return match.group(1), int(match.group(2))


def operation_asset_versions(project_root: Path) -> dict[str, tuple[int, str]]:
    root = project_context(project_root) / "operation-assets"
    result: dict[str, tuple[int, str]] = {}
    if not root.is_dir():
        return result
    for path in root.glob("*.md"):
        text = path.read_text(encoding="utf-8")
        match = re.match(r"\A---\s*\n(.*?)\n---\s*\n", text, re.DOTALL)
        if match is None:
            continue
        try:
            value = yaml.safe_load(match.group(1))
        except yaml.YAMLError:
            continue
        if (
            isinstance(value, dict)
            and isinstance(value.get("asset_id"), str)
            and isinstance(value.get("version"), int)
        ):
            result[value["asset_id"]] = (
                int(value["version"]),
                str(value.get("status") or "unknown"),
            )
    return result


def validate_automation_dependencies(
    project_root: Path,
    asset: dict[str, Any],
    asset_by_id: dict[str, dict[str, Any]] | None = None,
) -> list[str]:
    errors: list[str] = []
    if asset_by_id is None:
        asset_by_id = {
            str(item.get("asset_id")): item
            for _path, item in iter_assets(project_root)
            if isinstance(item.get("asset_id"), str)
        }
    asset_id = str(asset.get("asset_id") or "automation")
    for index, reference in enumerate(asset.get("dom_asset_refs", [])):
        try:
            dependency_id, version = versioned_ref(
                reference, f"{asset_id}.dom_asset_refs[{index}]"
            )
        except AssetError as exc:
            errors.append(str(exc))
            continue
        dependency = asset_by_id.get(dependency_id)
        if (
            not dependency
            or dependency.get("asset_type") != "dom-map"
            or dependency.get("version") != version
            or dependency.get("status") == "retired"
        ):
            errors.append(
                f"{asset_id}: DOM dependency is missing, stale, or retired: {reference}"
            )
    operations = operation_asset_versions(project_root)
    for index, reference in enumerate(asset.get("operation_asset_refs", [])):
        try:
            dependency_id, version = versioned_ref(
                reference, f"{asset_id}.operation_asset_refs[{index}]"
            )
        except AssetError as exc:
            errors.append(str(exc))
            continue
        observed = operations.get(dependency_id)
        if not observed or observed[0] != version or observed[1] == "retired":
            errors.append(
                f"{asset_id}: operation dependency is missing, stale, or retired: "
                f"{reference}"
            )
    return errors


def projection(path: Path, asset: dict[str, Any]) -> dict[str, Any]:
    return {
        "asset_id": asset.get("asset_id"),
        "asset_type": asset.get("asset_type"),
        "semantic_name": asset.get("semantic_name"),
        "version": asset.get("version"),
        "status": asset.get("status"),
        "path": str(path.resolve()),
        "digest": hashlib.sha256(path.read_bytes()).hexdigest(),
        "source_runs": asset.get("source_runs", []),
    }


def require_valid(project_root: Path) -> list[tuple[Path, dict[str, Any]]]:
    assets, errors = validate_all(project_root)
    if errors:
        raise AssetError("; ".join(errors))
    return assets


def command_validate(args: argparse.Namespace) -> dict[str, Any]:
    assets = require_valid(Path(args.project_root))
    return {"valid": True, "asset_count": len(assets), "schema_version": SCHEMA_VERSION}


def command_rebuild(args: argparse.Namespace) -> dict[str, Any]:
    project_root = Path(args.project_root).resolve()
    return rebuild_index(project_root)


def rebuild_index(project_root: Path) -> dict[str, Any]:
    assets = require_valid(project_root)
    value = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": utc_now(),
        "assets": [projection(path, asset) for path, asset in assets],
    }
    path = project_context(project_root) / "asset-index.json"
    atomic_write_json(path, value)
    return {"valid": True, "asset_count": len(assets), "index": str(path)}


def searchable_text(asset: dict[str, Any]) -> str:
    return json.dumps(asset, ensure_ascii=False, sort_keys=True).lower()


def command_search(args: argparse.Namespace) -> dict[str, Any]:
    assets = require_valid(Path(args.project_root))
    terms = [term for term in args.query.lower().split() if term]
    matches: list[tuple[int, dict[str, Any]]] = []
    for path, asset in assets:
        if asset.get("status") == "retired" and not args.include_retired:
            continue
        text = searchable_text(asset)
        score = sum(text.count(term) for term in terms)
        if score:
            matches.append((score, projection(path, asset)))
    matches.sort(key=lambda item: (-item[0], str(item[1]["asset_id"])))
    return {
        "query": args.query,
        "matches": [{"score": score, **item} for score, item in matches],
    }


def find_asset(project_root: Path, asset_id: str) -> tuple[Path, dict[str, Any]]:
    matches = [
        (path, asset)
        for path, asset in iter_assets(project_root)
        if asset.get("asset_id") == asset_id
    ]
    if len(matches) != 1:
        raise AssetError(f"asset id does not identify exactly one asset: {asset_id}")
    return matches[0]


def command_transition(args: argparse.Namespace) -> dict[str, Any]:
    project_root = Path(args.project_root).resolve()
    path, asset = find_asset(project_root, args.asset_id)
    if args.status not in STATUSES:
        raise AssetError(f"unsupported status: {args.status}")
    if asset.get("status") == "retired" and args.status != "retired":
        raise AssetError("retired assets cannot be reactivated; create a successor")
    prior = asset.get("status")
    asset["status"] = args.status
    asset["version"] = int(asset.get("version", 0)) + 1
    asset.setdefault("validation_history", []).append(
        {
            "at": utc_now(),
            "event": "transition",
            "from": prior,
            "to": args.status,
            "reason": args.reason,
        }
    )
    if args.status == "retired":
        asset["tombstone"] = {"retired_at": utc_now(), "reason": args.reason}
    errors = validate_asset(path, asset)
    if errors:
        raise AssetError("; ".join(errors))
    atomic_write_yaml(path, asset)
    rebuild_index(project_root)
    return projection(path, asset)


def clean_automation_replays(asset: dict[str, Any]) -> None:
    contexts = {
        str(item.get("context_id"))
        for item in asset.get("validation_runs", [])
        if isinstance(item, dict)
        and item.get("result") == "passed"
        and item.get("repaired") is False
        and item.get("context_id")
    }
    if len(contexts) < 3:
        raise AssetError(
            "automation promotion requires three independent clean contexts"
        )
    passed_scopes = {
        str(item.get("scope"))
        for item in asset.get("validation_runs", [])
        if isinstance(item, dict) and item.get("result") == "passed"
    }
    if not {"affected-module", "full-suite"} <= passed_scopes:
        raise AssetError(
            "automation promotion requires affected-module and full-suite passes"
        )
    for field in ("unknown_effects", "cleanup_failures", "secret_findings"):
        if asset.get(field):
            raise AssetError(f"automation promotion blocked by {field}")


def automation_code_digest(root: Path) -> str:
    allowed = {".py", ".json", ".ini"}
    files = sorted(
        path
        for path in root.rglob("*")
        if path.is_file()
        and path.suffix in allowed
        and path.name != "asset-manifest.json"
        and "__pycache__" not in path.parts
        and ".pytest_cache" not in path.parts
    )
    if not files:
        raise AssetError("staged automation contains no digestible code")
    aggregate = hashlib.sha256()
    for path in files:
        relative = path.relative_to(root).as_posix()
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        aggregate.update(relative.encode("utf-8"))
        aggregate.update(b"\0")
        aggregate.update(digest.encode("ascii"))
        aggregate.update(b"\n")
    return f"sha256:{aggregate.hexdigest()}"


def secret_finding_paths(root: Path) -> list[str]:
    findings: list[str] = []
    for path in root.rglob("*"):
        if (
            not path.is_file()
            or path.suffix.lower() not in SECRET_SCAN_SUFFIXES
            or "__pycache__" in path.parts
            or ".pytest_cache" in path.parts
        ):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if any(pattern.search(text) for pattern in SECRET_PATTERNS):
            findings.append(path.relative_to(root).as_posix())
    return sorted(findings)


def remove_exact(path: Path) -> None:
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
    elif path.exists() or path.is_symlink():
        path.unlink()


def install_automation_code(
    project_root: Path,
    run_dir: Path,
    asset: dict[str, Any],
    current_version: int | None,
) -> tuple[Path, Path, Path | None]:
    staged = inside(
        run_dir,
        run_dir / "automation-staging" / str(asset["asset_id"]),
    )
    if not staged.is_dir():
        raise AssetError(f"staged automation code is missing: {staged}")
    if automation_code_digest(staged) != asset.get("code_digest"):
        raise AssetError("staged automation code digest does not match the asset")
    target = inside(project_root, project_root / str(asset["code_path"]))
    if target == project_root:
        raise AssetError("automation target may not be the project root")
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.promote-{os.getpid()}")
    backup = target.with_name(f".{target.name}.backup-{os.getpid()}")
    if temporary.exists() or backup.exists():
        raise AssetError("stale automation promotion workspace exists")
    shutil.copytree(staged, temporary)
    archive: Path | None = None
    if target.exists():
        archive = (
            project_context(project_root)
            / "automation-history"
            / str(asset["asset_id"])
            / f"v{current_version or 0}"
        )
        if archive.exists():
            remove_exact(temporary)
            raise AssetError(f"automation history already exists: {archive}")
        archive.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(target, archive)
        target.replace(backup)
    try:
        os.replace(temporary, target)
    except Exception as exc:
        remove_exact(temporary)
        if backup.exists():
            backup.replace(target)
        if archive is not None and archive.exists():
            remove_exact(archive)
        raise AssetError(f"cannot install staged automation: {exc}") from exc
    return target, backup, archive


def command_promote(args: argparse.Namespace) -> dict[str, Any]:
    project_root = Path(args.project_root).resolve()
    run_dir = Path(args.run_dir).resolve()
    source = inside(run_dir, Path(args.source))
    asset = read_yaml(source)
    asset_type = asset.get("asset_type")
    if asset_type not in ASSET_DIRS:
        raise AssetError(f"unsupported asset_type: {asset_type}")
    target = (
        project_context(project_root)
        / ASSET_DIRS[str(asset_type)]
        / f"{asset.get('asset_id')}.yaml"
    )
    errors = validate_asset(target, asset)
    if asset_type == "automation":
        errors.extend(validate_automation_dependencies(project_root, asset))
    if errors:
        raise AssetError("; ".join(errors))
    if asset_type == "automation":
        clean_automation_replays(asset)
        staged = inside(
            run_dir,
            run_dir / "automation-staging" / str(asset.get("asset_id")),
        )
        secret_findings = secret_finding_paths(staged)
        if secret_findings:
            raise AssetError(
                "automation promotion blocked by possible plaintext secrets in: "
                + ", ".join(secret_findings)
            )
        asset["status"] = "verified"
    current_version: int | None = None
    if target.is_file():
        current = read_yaml(target)
        if asset.get("base_version") != current.get("version"):
            raise AssetError("asset base_version conflicts with current project asset")
        current_version = int(current["version"])
        asset["version"] = current_version + 1
    asset.setdefault("validation_history", []).append(
        {"at": utc_now(), "event": "promoted", "source": str(source)}
    )
    code_target: Path | None = None
    backup: Path | None = None
    archive: Path | None = None
    if asset_type == "automation":
        code_target, backup, archive = install_automation_code(
            project_root, run_dir, asset, current_version
        )
    try:
        atomic_write_yaml(target, asset)
    except Exception as exc:
        if code_target is not None:
            remove_exact(code_target)
            if backup is not None and backup.exists():
                backup.replace(code_target)
            if archive is not None and archive.exists():
                remove_exact(archive)
        raise AssetError(f"cannot write promoted asset: {exc}") from exc
    if backup is not None and backup.exists():
        remove_exact(backup)
    rebuild_index(project_root)
    return projection(target, asset)


def asset_reference_locations(
    project_root: Path, asset_path: Path, asset: dict[str, Any]
) -> list[str]:
    asset_id = str(asset.get("asset_id") or "")
    if not asset_id:
        return []
    token = re.compile(
        rf"(?<![A-Za-z0-9_.-]){re.escape(asset_id)}(?:@\d+)?"
        r"(?![A-Za-z0-9_.-])"
    )
    roots = [project_context(project_root), project_root / "work" / "test-runs"]
    allowed = {".json", ".jsonl", ".yaml", ".yml", ".md"}
    ignored = {
        asset_path.resolve(),
        (project_context(project_root) / "asset-index.json").resolve(),
    }
    locations: list[str] = []
    for root in roots:
        if not root.is_dir():
            continue
        for candidate in root.rglob("*"):
            if (
                not candidate.is_file()
                or candidate.suffix.lower() not in allowed
                or candidate.resolve() in ignored
            ):
                continue
            try:
                text = candidate.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            if token.search(text):
                try:
                    locations.append(candidate.relative_to(project_root).as_posix())
                except ValueError:
                    locations.append(str(candidate.resolve()))
    return sorted(set(locations))


def command_delete(args: argparse.Namespace) -> dict[str, Any]:
    project_root = Path(args.project_root).resolve()
    path, asset = find_asset(project_root, args.asset_id)
    if not args.hard:
        args.status = "retired"
        return command_transition(args)
    references = asset_reference_locations(project_root, path, asset)
    if (
        asset.get("status") != "candidate"
        or asset.get("referenced_by")
        or asset.get("validation_history")
        or asset.get("validation_runs")
        or references
    ):
        raise AssetError("hard delete is allowed only for unreferenced candidates")
    tombstone = {
        "schema_version": SCHEMA_VERSION,
        "asset_id": asset["asset_id"],
        "asset_type": asset["asset_type"],
        "deleted_at": utc_now(),
        "reason": args.reason,
        "physical_delete": True,
        "prior_path": str(path.relative_to(project_root).as_posix()),
    }
    path.unlink()
    tombstone_path = (
        project_context(project_root) / "tombstones" / f"{args.asset_id}.yaml"
    )
    atomic_write_yaml(tombstone_path, tombstone)
    rebuild_index(project_root)
    return {
        "deleted": True,
        "asset_id": args.asset_id,
        "recoverable": False,
        "tombstone": str(tombstone_path),
    }


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description="Manage vnext-2 project test assets.")
    commands = root.add_subparsers(dest="command", required=True)
    for name in ("validate", "rebuild"):
        command = commands.add_parser(name)
        command.add_argument("--project-root", required=True)
    search = commands.add_parser("search")
    search.add_argument("--project-root", required=True)
    search.add_argument("--query", required=True)
    search.add_argument("--include-retired", action="store_true")
    transition = commands.add_parser("transition")
    transition.add_argument("--project-root", required=True)
    transition.add_argument("--asset-id", required=True)
    transition.add_argument("--status", choices=sorted(STATUSES), required=True)
    transition.add_argument("--reason", required=True)
    promote = commands.add_parser("promote")
    promote.add_argument("--project-root", required=True)
    promote.add_argument("--run-dir", required=True)
    promote.add_argument("--source", required=True)
    delete = commands.add_parser("delete")
    delete.add_argument("--project-root", required=True)
    delete.add_argument("--asset-id", required=True)
    delete.add_argument("--reason", required=True)
    delete.add_argument("--hard", action="store_true")
    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        commands = {
            "validate": command_validate,
            "rebuild": command_rebuild,
            "search": command_search,
            "transition": command_transition,
            "promote": command_promote,
            "delete": command_delete,
        }
        value = commands[args.command](args)
        print(json.dumps(value, ensure_ascii=False, indent=2))
        return 0
    except AssetError as exc:
        print(f"ERROR {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
