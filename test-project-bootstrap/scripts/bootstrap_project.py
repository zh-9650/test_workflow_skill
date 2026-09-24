"""Install the repository's managed testing entrypoint in one selected project."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import runpy
import tempfile
from datetime import datetime, timezone
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = SKILL_ROOT.parent
ASSETS = SKILL_ROOT / "assets"
WORKFLOW_VERSION = runpy.run_path(
    str(REPO_ROOT / "clarify-before-testing/scripts/workflow_versions.py")
)["WORKFLOW_VERSION"]
START = "<!-- TEST-WORKFLOW:START -->"
END = "<!-- TEST-WORKFLOW:END -->"
BLOCK_PATTERN = re.compile(re.escape(START) + r".*?" + re.escape(END), re.DOTALL)
SKIP_DIRS = {
    ".git", ".claude", ".test-workflow", ".venv", "venv", "node_modules",
    "dist", "build", "coverage", "work", "__pycache__", ".pytest_cache",
}
DOC_NAME = re.compile(
    r"readme|prd|requirement|需求|原型|业务|接口|api|database|数据库|设计|spec",
    re.IGNORECASE,
)
CONFIG_NAMES = {"package.json", "pyproject.toml", "go.mod", "Cargo.toml", "requirements.txt"}
TEST_NAME = re.compile(r"(^test_.*\.py$|.*\.(spec|test)\.[cm]?[jt]sx?$)", re.IGNORECASE)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def managed_parts(text: str) -> tuple[str, str | None]:
    start_count = text.count(START)
    end_count = text.count(END)
    if start_count != end_count or start_count > 1:
        raise ValueError("CLAUDE.md has incomplete or duplicate TEST-WORKFLOW markers")
    if start_count == 0:
        return text.rstrip("\r\n"), None
    match = BLOCK_PATTERN.search(text)
    if match is None:
        raise ValueError("CLAUDE.md TEST-WORKFLOW marker order is invalid")
    outside = (text[: match.start()] + text[match.end() :]).rstrip("\r\n")
    return outside, match.group()


def desired_claude(text: str, block: str) -> str:
    _, existing = managed_parts(text)
    newline = "\r\n" if "\r\n" in text else "\n"
    block = block.replace("\n", newline).rstrip("\r\n")
    if existing is not None:
        return BLOCK_PATTERN.sub(lambda _: block, text, count=1)
    if not text:
        return block + newline
    separator = "" if text.endswith(("\n", "\r")) else newline
    return text + separator + newline + block + newline


def safe_destination(project: Path, relative: str) -> Path:
    dest = project / relative
    current = project
    parts = Path(relative).parts
    for index, part in enumerate(parts):
        current = current / part
        is_junction = getattr(current, "is_junction", None)
        if current.is_symlink() or (callable(is_junction) and is_junction()):
            raise ValueError(
                f"managed path contains a symlink or junction: {relative}"
            )
        if index < len(parts) - 1 and current.exists() and not current.is_dir():
            raise ValueError(
                f"managed path has a non-directory parent: {relative}"
            )
    try:
        dest.resolve().relative_to(project.resolve())
    except ValueError as exc:
        raise ValueError(f"managed path escapes selected project: {dest}") from exc
    return dest


def write_if_changed(path: Path, content: bytes, check: bool, changed: list[str], project: Path) -> None:
    if path.exists() and path.read_bytes() == content:
        return
    changed.append(path.relative_to(project).as_posix())
    if check:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="wb", prefix=f".{path.name}.", suffix=".tmp", dir=path.parent, delete=False
    ) as handle:
        temp = Path(handle.name)
        handle.write(content)
    try:
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def source_files(project: Path) -> list[Path]:
    found: list[Path] = []
    for base, dirs, files in os.walk(project):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS)
        parent = Path(base)
        if len(parent.relative_to(project).parts) > 3:
            dirs[:] = []
            continue
        for name in sorted(files):
            path = parent / name
            if path.is_symlink() or path == project / "CLAUDE.md":
                continue
            if name in CONFIG_NAMES or DOC_NAME.search(name) or TEST_NAME.match(name):
                found.append(path)
            if len(found) >= 200:
                return found
    return found


def source_hashes(project: Path, claude_text: str, files: list[Path]) -> dict[str, str]:
    outside, _ = managed_parts(claude_text)
    hashes = {"CLAUDE.md (outside managed block)": sha256_bytes(outside.encode("utf-8"))}
    for path in files:
        hashes[path.relative_to(project).as_posix()] = sha256_file(path)
    return dict(sorted(hashes.items()))


def bullet_paths(paths: list[str]) -> str:
    return "\n".join(f"- `{path}`" for path in paths) if paths else "- 暂未发现；需人工补充。"


def project_metadata(project: Path, files: list[Path]) -> dict[str, str]:
    rels = [p.relative_to(project).as_posix() for p in files]
    config = [p for p in files if p.name in CONFIG_NAMES]
    docs = [p for p in rels if DOC_NAME.search(Path(p).name)]
    tests = [
        p for p in rels
        if TEST_NAME.match(Path(p).name) or "test" in p.lower() or "测试" in p
    ]
    source_dirs = [name for name in ("src", "app", "frontend", "backend", "server", "client") if (project / name).is_dir()]
    stack: list[str] = []
    commands: list[str] = []
    for path in config:
        if path.name == "package.json":
            stack.append("Node.js / TypeScript 或 JavaScript")
            try:
                package = json.loads(path.read_text(encoding="utf-8"))
                for name in package.get("scripts", {}):
                    commands.append(f"- `{path.parent.relative_to(project).as_posix() or '.'}`: `npm run {name}`")
            except (ValueError, OSError):
                commands.append(f"- `{path.relative_to(project).as_posix()}` 无法解析，需人工核对命令。")
        elif path.name in {"pyproject.toml", "requirements.txt"}:
            stack.append("Python")
        elif path.name == "go.mod":
            stack.append("Go")
        elif path.name == "Cargo.toml":
            stack.append("Rust")
    secret_refs = [p for p in (".test-secrets.env", ".env", ".env.example", ".env.sample") if (project / p).exists()]
    source_line = bullet_paths(docs + [p for p in rels if p in {"package.json", "pyproject.toml", "go.mod", "Cargo.toml"}])
    return {
        "tech_stack": "、".join(dict.fromkeys(stack)) or "待核对",
        "source_index": source_line,
        "existing_tests": bullet_paths(tests),
        "commands": "\n".join(commands) if commands else "- 尚未识别；需人工补充启动、构建、Lint、类型检查和测试命令。",
        "environments": f"- Web/API 地址与环境标识：待确认。\n- 秘密文件引用：{', '.join(f'`{p}`' for p in secret_refs) if secret_refs else '待确认'}。\n- 账号角色：待确认；此处不记录凭据。",
        "business_index": bullet_paths(docs + source_dirs),
        "risk_notes": "- 删除、审批、支付、发布等不可逆动作：需结合项目资料人工核对。",
        "missing_items": "- 环境入口、账号角色、业务状态/流程资料和高风险操作需逐项确认。",
    }


def render_index(project: Path, files: list[Path], hashes: dict[str, str], updated_at: str) -> str:
    template = (ASSETS / "PROJECT_TESTING_INDEX.template.md").read_text(encoding="utf-8")
    metadata = project_metadata(project, files)
    return template.format(
        project_name=project.name,
        project_root=project.as_posix(),
        workflow_version=WORKFLOW_VERSION,
        updated_at=updated_at,
        source_hashes="\n".join(f"- `{p}`: `{digest}`" for p, digest in hashes.items()),
        **metadata,
    )


def managed_assets() -> dict[str, Path]:
    result = {
        ".claude/agents/test-execution-worker.md": ASSETS / "claude-agents/test-execution-worker.md",
        ".claude/agents/test-result-reviewer.md": ASSETS / "claude-agents/test-result-reviewer.md",
    }
    for path in sorted((ASSETS / "typescript-runtime").rglob("*")):
        if path.is_file():
            rel = path.relative_to(ASSETS / "typescript-runtime").as_posix()
            result[f"work/test-automation/{rel}"] = path
    return result


def check_managed_asset_conflicts(
    project: Path, assets: dict[str, Path], old_profile: dict | None
) -> None:
    previously_managed = (
        old_profile.get("managed_files_sha256", {})
        if isinstance(old_profile, dict)
        else {}
    )
    for relative, asset in assets.items():
        dest = safe_destination(project, relative)
        if dest.is_symlink():
            raise ValueError(
                f"refusing to replace a symlink at a managed project path: {relative}"
            )
        if not dest.exists():
            continue
        if not dest.is_file():
            raise ValueError(
                f"refusing to replace a non-file at a managed project path: {relative}"
            )
        current_hash = sha256_file(dest)
        desired_hash = sha256_file(asset)
        prior_hash = previously_managed.get(relative)
        if current_hash in {desired_hash, prior_hash}:
            continue
        raise ValueError(
            "refusing to overwrite an existing unmanaged or locally modified "
            f"project file: {relative}; preserve or move it, then rerun Bootstrap"
        )


def check_metadata_conflicts(
    index_path: Path,
    profile_path: Path,
    old_profile: dict | None,
) -> None:
    if profile_path.is_symlink() or index_path.is_symlink():
        raise ValueError("refusing to replace a symlink at a managed .test-workflow path")
    if profile_path.exists():
        if not profile_path.is_file() or not isinstance(old_profile, dict):
            raise ValueError(
                "refusing to overwrite an existing unmanaged project file: "
                ".test-workflow/project-profile.json"
            )
        hash_pattern = re.compile(r"^[0-9a-f]{64}$")
        managed_hashes = old_profile.get("managed_files_sha256")
        owner_marker = old_profile.get("managed_by")
        profile_is_managed = (
            owner_marker == "test-project-bootstrap"
            and bool(managed_hashes)
            and isinstance(old_profile.get("source_hashes"), dict)
            and bool(old_profile.get("source_hashes"))
            and isinstance(old_profile.get("workflow_version"), str)
            and bool(old_profile.get("workflow_version"))
            and isinstance(old_profile.get("managed_block_sha256"), str)
            and hash_pattern.fullmatch(old_profile["managed_block_sha256"]) is not None
            and isinstance(old_profile.get("index_sha256"), str)
            and hash_pattern.fullmatch(old_profile["index_sha256"]) is not None
            and isinstance(managed_hashes, dict)
            and all(
                isinstance(path, str)
                and isinstance(digest, str)
                and hash_pattern.fullmatch(digest) is not None
                for path, digest in managed_hashes.items()
            )
            and isinstance(old_profile.get("source_hashes"), dict)
            and isinstance(old_profile.get("updated_at"), str)
            and bool(old_profile.get("updated_at"))
        )
        if not profile_is_managed:
            raise ValueError(
                "refusing to overwrite an unrecognized Bootstrap profile: "
                ".test-workflow/project-profile.json"
            )
    if index_path.exists():
        if not index_path.is_file():
            raise ValueError(
                "refusing to overwrite a non-file at a managed project path: "
                ".test-workflow/PROJECT_TESTING_INDEX.md"
            )
        recorded_hash = old_profile.get("index_sha256") if isinstance(old_profile, dict) else None
        if not recorded_hash or sha256_file(index_path) != recorded_hash:
            raise ValueError(
                "refusing to overwrite an unmanaged or locally modified project file: "
                ".test-workflow/PROJECT_TESTING_INDEX.md"
            )


def bootstrap(project_root: str | Path, check: bool = False) -> dict:
    project = Path(project_root).resolve()
    if not project.is_dir():
        raise ValueError(f"project root is not a directory: {project}")
    claude_path = safe_destination(project, "CLAUDE.md")
    profile_path = safe_destination(project, ".test-workflow/project-profile.json")
    index_path = safe_destination(project, ".test-workflow/PROJECT_TESTING_INDEX.md")
    if claude_path.exists() and not claude_path.is_file():
        raise ValueError("refusing to replace a non-file at managed project path: CLAUDE.md")
    claude_text = claude_path.read_text(encoding="utf-8") if claude_path.exists() else ""
    outside, actual_block = managed_parts(claude_text)
    del outside
    block = (ASSETS / "CLAUDE.testing-block.md").read_text(encoding="utf-8")
    desired = desired_claude(claude_text, block)
    _, desired_block = managed_parts(desired)
    assert desired_block is not None
    old_profile = None
    if profile_path.exists():
        try:
            old_profile = json.loads(profile_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            old_profile = None
    files = source_files(project)
    hashes = source_hashes(project, claude_text, files)
    assets = managed_assets()
    managed_hashes = {relative: sha256_file(asset) for relative, asset in assets.items()}
    # Preflight every destination before writing CLAUDE.md, an asset, or profile.
    # Existing user files must never be silently replaced, including on upgrades.
    check_managed_asset_conflicts(project, assets, old_profile)
    check_metadata_conflicts(index_path, profile_path, old_profile)
    asset_stale = (
        not isinstance(old_profile, dict)
        or old_profile.get("managed_files_sha256") != managed_hashes
        or any(
            not safe_destination(project, relative).is_file()
            or sha256_file(safe_destination(project, relative)) != digest
            for relative, digest in managed_hashes.items()
        )
    )
    version_stale = not isinstance(old_profile, dict) or old_profile.get("workflow_version") != WORKFLOW_VERSION
    source_stale = not isinstance(old_profile, dict) or old_profile.get("source_hashes") != hashes
    block_stale = actual_block != desired_block
    profile_block_stale = not isinstance(old_profile, dict) or old_profile.get("managed_block_sha256") != sha256_bytes(desired_block.encode("utf-8"))
    index_stale = not index_path.is_file()
    if index_path.is_file() and isinstance(old_profile, dict):
        index_stale = old_profile.get("index_sha256") != sha256_file(index_path)
    refresh_index = version_stale or source_stale or block_stale or profile_block_stale or index_stale or asset_stale
    changed: list[str] = []
    write_if_changed(claude_path, desired.encode("utf-8"), check, changed, project)
    for relative, asset in assets.items():
        dest = safe_destination(project, relative)
        write_if_changed(dest, asset.read_bytes(), check, changed, project)
    if refresh_index:
        timestamp = now()
        index = render_index(project, files, hashes, timestamp)
        write_if_changed(index_path, index.encode("utf-8"), check, changed, project)
        profile = {
            "managed_by": "test-project-bootstrap",
            "workflow_version": WORKFLOW_VERSION,
            "managed_block_sha256": sha256_bytes(desired_block.encode("utf-8")),
            "index_sha256": sha256_bytes(index.encode("utf-8")),
            "managed_files_sha256": managed_hashes,
            "source_hashes": hashes,
            "updated_at": timestamp,
        }
        write_if_changed(
            profile_path,
            (json.dumps(profile, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8"),
            check,
            changed,
            project,
        )
    return {
        "ok": not (check and changed),
        "project_root": str(project),
        "workflow_version": WORKFLOW_VERSION,
        "changed": changed,
        "index_ref": ".test-workflow/PROJECT_TESTING_INDEX.md",
        "profile_ref": ".test-workflow/project-profile.json",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--check", action="store_true", help="Report drift without writing")
    args = parser.parse_args()
    result = bootstrap(args.project_root, check=args.check)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if not result["ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
