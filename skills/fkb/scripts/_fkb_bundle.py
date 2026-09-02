"""Shared helpers for the fkb bundle commands (clone-bundle, add-bundle, create-bundle).

Co-located with manifest.py and imported by each command. Keeps the three thin
command scripts free of duplicated manifest-location, prompting, and policy logic.
"""

from __future__ import annotations

import sys
from pathlib import Path

import manifest


def workspace_root_or_die() -> tuple[Path, str | None]:
    """Return (manifest_path, workspace_root). Exit BAD_MANIFEST if no workspace exists."""
    manifest_path = manifest.manifest_location()
    try:
        ws = manifest.load_workspace(manifest_path)
    except manifest.ManifestError as exc:
        sys.stderr.write(f"manifest error: {exc}\n")
        sys.exit(manifest.Exit.BAD_MANIFEST)
    return manifest_path, ws.workspace_root


def _isatty() -> bool:
    return sys.stdin.isatty() and sys.stdout.isatty()


def ask(prompt: str, default: str) -> str:
    """Prompt with a default. Non-interactive (no TTY) returns the default silently."""
    if not _isatty():
        return default
    reply = input(f"{prompt} [{default}]: ").strip()
    return reply or default


def ask_bool(prompt: str, *, default: bool) -> bool:
    d = "Y/n" if default else "y/N"
    reply = ask(f"{prompt} ({d})", "yes" if default else "no").strip().lower()
    return reply in {"y", "yes", "true", "1"}


def ask_policy(
    referenceable_by: str | list[str] | None,
    writable: bool | None,
    publish: str | None,
    *,
    default_writable: bool,
) -> manifest.BundlePolicy:
    """Fill any absent policy field by prompting (or fail-closed default when non-interactive)."""
    if writable is None:
        writable = ask_bool("May agents author into this bundle here?", default=default_writable)
    if publish is None:
        entered = ask("Published URL base (blank = not published)", "")
        publish = entered or None
    return manifest.BundlePolicy(referenceable_by=referenceable_by, writable=writable, publish=publish)


def parse_referenceable_by(raw: str | None) -> str | list[str] | None:
    if raw is None:
        return None
    if raw == manifest.WILDCARD:
        return manifest.WILDCARD
    names = [n.strip() for n in raw.strip().strip("[]").split(",")]
    return [n for n in names if n]


def find_okf_root(checkout: Path) -> Path | None:
    """Return the directory of the top-most (shallowest) index.md, or None if absent.

    index.md is the OKF bundle-root reserved file. Shallowest handles the common
    'infra at top, bundle in docs/' layout. On a tie at the same depth, returns None
    so the caller asks rather than guessing.
    """
    matches = sorted(checkout.rglob("index.md"), key=lambda p: len(p.relative_to(checkout).parts))
    if not matches:
        return None
    shallowest_depth = len(matches[0].relative_to(checkout).parts)
    at_top = [p for p in matches if len(p.relative_to(checkout).parts) == shallowest_depth]
    if len(at_top) != 1:
        return None
    return at_top[0].parent


def report_added(name: str, path: str, policy: manifest.BundlePolicy, manifest_path: Path) -> None:
    ref = policy.referenceable_by if policy.referenceable_by is not None else manifest.DEFAULT_REFERENCEABLE_BY
    ref_str = manifest.WILDCARD if ref == manifest.WILDCARD else f"[{','.join(ref)}]"
    sys.stdout.write(
        f"registered bundle {name!r} in {manifest_path}\n"
        f"  path={path}  writable={str(policy.writable).lower()}  "
        f"referenceable_by={ref_str}  publish={policy.publish or 'null'}\n"
    )
