#!/usr/bin/env -S uv run --quiet --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["ruamel.yaml>=0.18"]
# ///
"""manifest.py — deterministic core for the fkb (federated knowledge bundle) skill layer.

Responsibilities (the manifest-aware concerns; all bundle MUTATION is delegated to kb*):
  1. Locate & load workspace.okf.yaml (the sole coupling point between bundles).
  2. Resolve name -> {path, referenceable_by, writable, publish} with fail-closed defaults.
  3. Resolve each bundle's path: ~-expand, absolute as-is, else join under workspace_root.
  4. Enforce the leak rule:  A may reference B  iff  A == B  OR  A in B.referenceable_by.
  5. Preflight the toolchain: uv present + the kb* skills installed. fkb delegates to kb in
     prose, so if a dependency is missing there is nothing to throw — we make it LOUD here.

The manifest lives at a fixed location (single workspace per machine):
    $FKB_WORKSPACE            (override, points at a manifest file)
    $XDG_CONFIG_HOME/federated-knowledge/workspace.okf.yaml
    ~/.config/federated-knowledge/workspace.okf.yaml   (XDG default)
There is deliberately NO upward-from-cwd search: cwd never affects resolution.

Usage:
  manifest.py list                          # resolved bundles, one per line
  manifest.py resolve <name>                # JSON for one bundle (exit 3 if unknown)
  manifest.py can-reference <from> <to>     # exit 0 = allowed, exit 1 = denied
  manifest.py check-deps [kb-skill ...]     # exit 0 = uv + kb present, exit 4 = missing
  manifest.py validate                      # exit 0 = manifest well-formed, exit 2 = not

Global flags:
  --manifest <path>   override manifest location (highest precedence)
  --json              machine-readable output where applicable
"""

from __future__ import annotations

import json
import os
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap, CommentedSeq
from ruamel.yaml.error import YAMLError

# ---------------------------------------------------------------------------
# exit codes (stable contract, tested)
# ---------------------------------------------------------------------------


class Exit:
    OK = 0
    DENIED = 1  # can-reference: not allowed
    BAD_MANIFEST = 2  # manifest missing / malformed / fails validation
    UNKNOWN_BUNDLE = 3  # resolve/can-reference: name not in manifest
    MISSING_DEP = 4  # check-deps: uv or a required kb skill is not installed
    USAGE = 64  # bad CLI usage


# The kb skills this fkb layer delegates to. kb-promote is intentionally absent
# upstream — it is net-new in THIS repo (fkb-promote), so it is never preflighted.
KB_SKILLS = ["kb", "kb-init", "kb-ingest", "kb-query", "kb-lint"]

# Fail-closed defaults: an unconfigured axis is sealed and read-only.
DEFAULT_REFERENCEABLE_BY: list[str] = []  # no one may point at me
DEFAULT_WRITABLE = False  # no one may author into me here
DEFAULT_PUBLISH = None  # not published; keep links local

WILDCARD = "*"  # referenceable_by: anyone

_CAN_REFERENCE_ARGC = 2  # can-reference takes exactly <from> <to>
_ADD_BUNDLE_ARGC = 2  # add-bundle takes at least <name> <path>


class ManifestError(Exception):
    """Raised when the manifest is missing, malformed, or fails validation."""


# ---------------------------------------------------------------------------
# location
# ---------------------------------------------------------------------------


def config_dir() -> Path:
    """The fixed fkb config directory: $XDG_CONFIG_HOME/federated-knowledge or ~/.config/..."""
    xdg = os.environ.get("XDG_CONFIG_HOME")
    base = Path(xdg) if xdg else Path.home() / ".config"
    return base / "federated-knowledge"


def manifest_location(override: str | None = None) -> Path:
    """Resolve the manifest path. Precedence: --manifest > $FKB_WORKSPACE > XDG path.

    No upward-from-cwd search — the workspace is single and fixed per machine.
    """
    if override:
        return Path(override).expanduser().resolve()
    env = os.environ.get("FKB_WORKSPACE")
    if env:
        return Path(env).expanduser().resolve()
    return config_dir() / "workspace.okf.yaml"


# ---------------------------------------------------------------------------
# path resolution
# ---------------------------------------------------------------------------


def resolve_path(raw: str, workspace_root: str | None) -> Path:
    """Resolve a bundle's raw path to an absolute path.

    ~-expand first; an absolute path is used as-is (onboard-in-place); a relative
    path is joined under workspace_root; a relative path with no workspace_root is
    a manifest error.
    """
    expanded = Path(raw).expanduser()
    if expanded.is_absolute():
        return expanded
    if workspace_root is None:
        raise ManifestError(
            f"bundle path {raw!r} is relative but no top-level 'workspace_root' is set — "
            f"make the path absolute or add a workspace_root"
        )
    root = Path(workspace_root).expanduser()
    return (root / expanded).resolve() if root.is_absolute() else root / expanded


# ---------------------------------------------------------------------------
# load + validate + resolve
# ---------------------------------------------------------------------------


@dataclass
class Bundle:
    name: str
    path: str  # raw path, as written in the manifest (for round-tripping)
    resolved_path: Path  # absolute, path-resolved
    referenceable_by: str | list[str]  # "*" sentinel or a list of names
    writable: bool
    publish: str | None

    def as_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "path": self.path,
            "resolved_path": str(self.resolved_path),
            "referenceable_by": self.referenceable_by,
            "writable": self.writable,
            "publish": self.publish,
        }


@dataclass
class Workspace:
    manifest_path: Path
    workspace_root: str | None
    bundles: dict[str, Bundle]


@dataclass
class BundlePolicy:
    referenceable_by: str | list[str] | None = None
    writable: bool = DEFAULT_WRITABLE
    publish: str | None = DEFAULT_PUBLISH


def _yaml() -> YAML:
    y = YAML()  # round-trip mode: preserves comments + flow style on write
    y.preserve_quotes = True
    y.width = 4096  # keep each flow-style bundle entry on one line, never wrap
    return y


def _normalize_bundle(name: str, raw: object, workspace_root: str | None) -> Bundle:
    if not isinstance(raw, dict):
        raise ManifestError(f"bundle {name!r} must be a map")

    path = raw.get("path")
    if not isinstance(path, str) or path.strip() == "":
        raise ManifestError(f"bundle {name!r}: 'path' is required and must be a string")

    ref = raw.get("referenceable_by", DEFAULT_REFERENCEABLE_BY)
    if ref == WILDCARD:
        referenceable_by: str | list[str] = WILDCARD
    elif isinstance(ref, list):
        if not all(isinstance(x, str) for x in ref):
            raise ManifestError(f"bundle {name!r}: 'referenceable_by' list must be strings")
        referenceable_by = [str(x) for x in ref]
    else:
        raise ManifestError(f"bundle {name!r}: 'referenceable_by' must be '*' or a list")

    writable = raw.get("writable", DEFAULT_WRITABLE)
    if not isinstance(writable, bool):
        raise ManifestError(f"bundle {name!r}: 'writable' must be true/false")

    publish = raw.get("publish", DEFAULT_PUBLISH)
    if publish is not None and not isinstance(publish, str):
        raise ManifestError(f"bundle {name!r}: 'publish' must be a URL string or null")

    return Bundle(
        name=name,
        path=path,
        resolved_path=resolve_path(path, workspace_root),
        referenceable_by=referenceable_by,
        writable=writable,
        publish=publish,
    )


def load_workspace(manifest_path: Path | None = None) -> Workspace:
    """Load, validate, and resolve the workspace manifest."""
    path = manifest_path or manifest_location()
    if not path.exists():
        raise ManifestError(f"no workspace configured at {path} — run install-glue (or set $FKB_WORKSPACE)")

    try:
        data = _yaml().load(path.read_text(encoding="utf-8"))
    except YAMLError as exc:  # malformed YAML
        raise ManifestError(f"could not parse {path}: {exc}") from exc

    if not isinstance(data, dict) or "bundles" not in data:
        raise ManifestError("manifest has no 'bundles:' key")

    # An empty `bundles:` (parsed as None or {}) is a valid, freshly-initialized
    # federation — empty but usable once the first bundle is added.
    raw_bundles = data["bundles"] or {}
    if not isinstance(raw_bundles, dict):
        raise ManifestError("'bundles:' must be a map of name -> bundle")

    workspace_root = data.get("workspace_root")
    if workspace_root is not None and not isinstance(workspace_root, str):
        raise ManifestError("'workspace_root' must be a string or absent")

    bundles = {name: _normalize_bundle(name, raw, workspace_root) for name, raw in raw_bundles.items()}
    return Workspace(manifest_path=path, workspace_root=workspace_root, bundles=bundles)


def can_reference(ws: Workspace, source: str, target: str) -> bool:
    """The leak rule: A may reference B iff A == B OR A in B.referenceable_by ('*' = anyone)."""
    if target not in ws.bundles:
        raise ManifestError(f"unknown bundle: {target!r}")
    if source not in ws.bundles:
        raise ManifestError(f"unknown bundle: {source!r}")
    if source == target:
        return True
    ref = ws.bundles[target].referenceable_by
    if ref == WILDCARD:
        return True
    return source in ref


# ---------------------------------------------------------------------------
# writer: append a bundle line (round-trip; duplicate = error; append last)
# ---------------------------------------------------------------------------


def _flow_entry(path: str, policy: BundlePolicy) -> CommentedMap:
    ref = DEFAULT_REFERENCEABLE_BY if policy.referenceable_by is None else policy.referenceable_by
    entry = CommentedMap()
    entry["path"] = path
    if ref == WILDCARD:
        entry["referenceable_by"] = WILDCARD
    else:
        seq = CommentedSeq(ref)
        seq.fa.set_flow_style()
        entry["referenceable_by"] = seq
    entry["writable"] = policy.writable
    entry["publish"] = policy.publish
    entry.fa.set_flow_style()
    return entry


def add_bundle(manifest_path: Path, name: str, path: str, policy: BundlePolicy) -> None:
    """Append a bundle to the manifest's ``bundles:`` map, preserving comments and order.

    Raises ManifestError on a duplicate name (never overwrite — a silent widen is a
    disclosure risk) or a malformed manifest. New bundles always append last, so the
    user's own hand-sorting of the list survives.
    """
    if not manifest_path.exists():
        raise ManifestError(f"no workspace configured at {manifest_path} — run install-glue first")

    yaml = _yaml()
    try:
        data = yaml.load(manifest_path.read_text(encoding="utf-8"))
    except YAMLError as exc:
        raise ManifestError(f"could not parse {manifest_path}: {exc}") from exc

    if not isinstance(data, dict) or "bundles" not in data:
        raise ManifestError("manifest has no 'bundles:' key to append to")

    # An empty `bundles:` parses as None; seed a fresh map so the first bundle appends.
    if data["bundles"] is None:
        data["bundles"] = CommentedMap()
    if not isinstance(data["bundles"], dict):
        raise ManifestError("'bundles:' must be a map of name -> bundle")

    bundles = data["bundles"]
    if name in bundles:
        raise ManifestError(f"bundle {name!r} already exists — pick another name or edit the manifest")

    bundles[name] = _flow_entry(path, policy)  # dict insertion order = append last

    with manifest_path.open("w", encoding="utf-8") as handle:
        yaml.dump(data, handle)


# ---------------------------------------------------------------------------
# dependency preflight (uv + kb skills)
# ---------------------------------------------------------------------------


def skill_search_dirs(cwd: Path | None = None) -> list[Path]:
    """Where skills.sh installs skills (project + global, OpenCode + Claude Code)."""
    here = cwd or Path.cwd()
    home = Path.home()
    return [
        here / ".agents" / "skills",
        here / ".claude" / "skills",
        home / ".config" / "opencode" / "skills",
        home / ".claude" / "skills",
        home / ".agents" / "skills",
    ]


def is_kb_installed(skill: str, cwd: Path | None = None) -> bool:
    return any((d / skill / "SKILL.md").is_file() for d in skill_search_dirs(cwd))


def check_deps(skills: list[str], cwd: Path | None = None) -> tuple[bool, list[str]]:
    """Return (ok, missing). 'uv' is checked as a dependency alongside the kb skills."""
    missing: list[str] = []
    if shutil.which("uv") is None:
        missing.append("uv")
    missing.extend(s for s in skills if not is_kb_installed(s, cwd))
    return (len(missing) == 0, missing)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _die(code: int, msg: str) -> None:
    sys.stderr.write(msg + "\n")
    sys.exit(code)


def _parse_args(argv: list[str]) -> tuple[dict[str, object], list[str]]:
    flags: dict[str, object] = {"manifest": None, "json": False, "writable": False}
    value_flags = {"--manifest": "manifest", "--referenceable-by": "referenceable_by", "--publish": "publish"}
    rest: list[str] = []
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg in value_flags:
            i += 1
            flags[value_flags[arg]] = argv[i] if i < len(argv) else None
        elif arg == "--json":
            flags["json"] = True
        elif arg == "--writable":
            flags["writable"] = True
        else:
            rest.append(arg)
        i += 1
    return flags, rest


def _cmd_check_deps(args: list[str], as_json: bool) -> None:
    skills = args or KB_SKILLS
    ok, missing = check_deps(skills)
    if ok:
        if as_json:
            sys.stdout.write(json.dumps({"ok": True, "missing": []}) + "\n")
        sys.exit(Exit.OK)
    hints = []
    if "uv" in missing:
        hints.append("install uv:  https://docs.astral.sh/uv/getting-started/installation/")
    if any(m != "uv" for m in missing):
        hints.append("install the kb skills:  npx skills add stjbrown/agent-knowledge")
    _die(
        Exit.MISSING_DEP,
        f"missing dependency(ies): {', '.join(missing)}\n"
        + "\n".join(hints)
        + "\n(fkb delegates all bundle mutation to kb; it will not hand-roll the operation)",
    )


def _cmd_list(ws: Workspace, as_json: bool) -> None:
    if as_json:
        sys.stdout.write(json.dumps({n: b.as_dict() for n, b in ws.bundles.items()}, indent=2) + "\n")
    else:
        for b in ws.bundles.values():
            ref = WILDCARD if b.referenceable_by == WILDCARD else f"[{','.join(b.referenceable_by)}]"
            sys.stdout.write(
                f"{b.name}\tpath={b.resolved_path}\twritable={str(b.writable).lower()}"
                f"\treferenceable_by={ref}\tpublish={b.publish or 'null'}\n"
            )
    sys.exit(Exit.OK)


def _cmd_resolve(ws: Workspace, args: list[str], as_json: bool) -> None:
    if not args:
        _die(Exit.USAGE, "usage: manifest.py resolve <name>")
    name = args[0]
    bundle = ws.bundles.get(name)
    if bundle is None:
        _die(Exit.UNKNOWN_BUNDLE, f"unknown bundle: {name!r}")
    sys.stdout.write(json.dumps(bundle.as_dict(), indent=None if as_json else 2) + "\n")
    sys.exit(Exit.OK)


def _cmd_can_reference(ws: Workspace, args: list[str]) -> None:
    if len(args) < _CAN_REFERENCE_ARGC:
        _die(Exit.USAGE, "usage: manifest.py can-reference <from> <to>")
    source, target = args[0], args[1]
    try:
        allowed = can_reference(ws, source, target)
    except ManifestError as exc:
        _die(Exit.UNKNOWN_BUNDLE, str(exc))
    suffix = "" if allowed else f"  ({target}.referenceable_by does not include {source})"
    sys.stdout.write(f"{'ALLOW' if allowed else 'DENY'} {source} -> {target}{suffix}\n")
    sys.exit(Exit.OK if allowed else Exit.DENIED)


def _parse_referenceable_by(raw: str) -> str | list[str]:
    if raw == WILDCARD:
        return WILDCARD
    names = [n.strip() for n in raw.strip().strip("[]").split(",")]
    return [n for n in names if n]


def _cmd_add_bundle(manifest_path: Path, args: list[str], flags: dict[str, object]) -> None:
    if len(args) < _ADD_BUNDLE_ARGC:
        _die(
            Exit.USAGE,
            "usage: manifest.py add-bundle <name> <path> [--referenceable-by '*'|a,b] [--writable] [--publish URL]",
        )
    name, path = args[0], args[1]
    ref_raw = flags.get("referenceable_by")
    policy = BundlePolicy(
        referenceable_by=_parse_referenceable_by(ref_raw) if isinstance(ref_raw, str) else None,
        writable=bool(flags.get("writable")),
        publish=flags["publish"] if isinstance(flags.get("publish"), str) else None,
    )
    try:
        add_bundle(manifest_path, name, path, policy)
    except ManifestError as exc:
        _die(Exit.BAD_MANIFEST, f"manifest error: {exc}")
    sys.stdout.write(f"added bundle {name!r} to {manifest_path}\n")
    sys.exit(Exit.OK)


def main(argv: list[str]) -> None:
    flags, rest = _parse_args(argv)
    if not rest:
        _die(Exit.USAGE, "usage: manifest.py <list|resolve|can-reference|add-bundle|check-deps|validate>")

    cmd, cmd_args = rest[0], rest[1:]
    as_json = bool(flags["json"])

    if cmd == "check-deps":
        _cmd_check_deps(cmd_args, as_json)
        return

    if cmd == "add-bundle":
        _cmd_add_bundle(manifest_location(flags["manifest"]), cmd_args, flags)  # type: ignore[arg-type]
        return

    manifest_path = manifest_location(flags["manifest"])  # type: ignore[arg-type]
    try:
        ws = load_workspace(manifest_path)
    except ManifestError as exc:
        _die(Exit.BAD_MANIFEST, f"manifest error: {exc}")

    if cmd == "validate":
        sys.stdout.write(f"ok: {len(ws.bundles)} bundle(s) in {ws.manifest_path}\n")
        sys.exit(Exit.OK)
    elif cmd == "list":
        _cmd_list(ws, as_json)
    elif cmd == "resolve":
        _cmd_resolve(ws, cmd_args, as_json)
    elif cmd == "can-reference":
        _cmd_can_reference(ws, cmd_args)
    else:
        _die(Exit.USAGE, f"unknown command: {cmd!r}")


if __name__ == "__main__":
    main(sys.argv[1:])
