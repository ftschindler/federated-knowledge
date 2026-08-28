"""Behavior lock for the fkb manifest core (skills/fkb/scripts/manifest.py).

Fast and deterministic (no LLM, no network). Imports the module directly for unit
tests, and drives it as a subprocess (via `uv run`) for the exit-code contract —
the exit codes are a stable, tested interface every fkb skill relies on.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

pytestmark = pytest.mark.python_scripts

REPO_ROOT = Path(__file__).resolve().parent.parent
MANIFEST_PY = REPO_ROOT / "skills" / "fkb" / "scripts" / "manifest.py"


def _load_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("fkb_manifest", MANIFEST_PY)
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod  # required so @dataclass can resolve cls.__module__
    spec.loader.exec_module(mod)
    return mod


manifest = _load_module()


SAMPLE = """\
# workspace
workspace_root: /ws
bundles:
  public:  { path: public/docs,  referenceable_by: "*",    writable: true,  publish: https://me.example/kb }
  peer:    { path: peer/docs,    referenceable_by: [team], writable: true,  publish: null }
  team:    { path: team/docs,    referenceable_by: [peer], writable: true }
  private: { path: private/docs, referenceable_by: [] }
  upstream: { path: /abs/upstream/docs, referenceable_by: "*", writable: false, publish: https://them.example/kb }
"""


def _write(tmp_path: Path, body: str) -> Path:
    p = tmp_path / "workspace.okf.yaml"
    p.write_text(body, encoding="utf-8")
    return p


# --- parsing & fail-closed defaults ----------------------------------------


def test_loads_all_bundles_and_resolves_fields(tmp_path: Path) -> None:
    ws = manifest.load_workspace(_write(tmp_path, SAMPLE))
    assert sorted(ws.bundles) == ["peer", "private", "public", "team", "upstream"]
    assert ws.bundles["public"].publish == "https://me.example/kb"
    assert ws.bundles["public"].referenceable_by == "*"


def test_fail_closed_defaults(tmp_path: Path) -> None:
    ws = manifest.load_workspace(_write(tmp_path, "workspace_root: /ws\nbundles:\n  x: { path: x/docs }\n"))
    x = ws.bundles["x"]
    assert x.writable is False
    assert x.publish is None
    assert x.referenceable_by == []


def test_omitted_publish_is_null(tmp_path: Path) -> None:
    ws = manifest.load_workspace(_write(tmp_path, SAMPLE))
    assert ws.bundles["team"].publish is None
    assert ws.bundles["upstream"].writable is False


def test_missing_path_is_error(tmp_path: Path) -> None:
    with pytest.raises(manifest.ManifestError, match=r"path.*required"):
        manifest.load_workspace(_write(tmp_path, "workspace_root: /ws\nbundles:\n  broken: { writable: true }\n"))


def test_missing_bundles_key_is_error(tmp_path: Path) -> None:
    with pytest.raises(manifest.ManifestError, match="no 'bundles:' key"):
        manifest.load_workspace(_write(tmp_path, "workspace_root: /ws\n"))


def test_empty_bundles_is_valid_fresh_federation(tmp_path: Path) -> None:
    ws = manifest.load_workspace(_write(tmp_path, "workspace_root: /ws\nbundles:\n"))
    assert ws.bundles == {}


def test_missing_manifest_is_error(tmp_path: Path) -> None:
    with pytest.raises(manifest.ManifestError, match="no workspace configured"):
        manifest.load_workspace(tmp_path / "does-not-exist.yaml")


# --- path resolution -------------------------------------------------------


def test_relative_path_resolves_under_workspace_root(tmp_path: Path) -> None:
    ws = manifest.load_workspace(_write(tmp_path, SAMPLE))
    assert ws.bundles["public"].resolved_path == Path("/ws/public/docs")


def test_absolute_path_used_as_is(tmp_path: Path) -> None:
    ws = manifest.load_workspace(_write(tmp_path, SAMPLE))
    assert ws.bundles["upstream"].resolved_path == Path("/abs/upstream/docs")


def test_tilde_expands_and_counts_as_absolute(tmp_path: Path) -> None:
    ws = manifest.load_workspace(_write(tmp_path, "bundles:\n  h: { path: ~/notes/docs }\n"))
    assert ws.bundles["h"].resolved_path == Path.home() / "notes" / "docs"


def test_relative_path_without_workspace_root_is_error(tmp_path: Path) -> None:
    with pytest.raises(manifest.ManifestError, match="relative but no top-level 'workspace_root'"):
        manifest.load_workspace(_write(tmp_path, "bundles:\n  x: { path: x/docs }\n"))


# --- the leak rule ---------------------------------------------------------


def test_bundle_may_reference_itself(tmp_path: Path) -> None:
    ws = manifest.load_workspace(_write(tmp_path, SAMPLE))
    assert manifest.can_reference(ws, "private", "private") is True


def test_wildcard_means_anyone(tmp_path: Path) -> None:
    ws = manifest.load_workspace(_write(tmp_path, SAMPLE))
    assert manifest.can_reference(ws, "private", "public") is True
    assert manifest.can_reference(ws, "peer", "public") is True


def test_empty_list_means_sealed(tmp_path: Path) -> None:
    ws = manifest.load_workspace(_write(tmp_path, SAMPLE))
    assert manifest.can_reference(ws, "public", "private") is False
    assert manifest.can_reference(ws, "peer", "private") is False


def test_mutual_unranked_peers(tmp_path: Path) -> None:
    ws = manifest.load_workspace(_write(tmp_path, SAMPLE))
    assert manifest.can_reference(ws, "peer", "team") is True
    assert manifest.can_reference(ws, "team", "peer") is True


def test_non_peer_denied(tmp_path: Path) -> None:
    ws = manifest.load_workspace(_write(tmp_path, SAMPLE))
    assert manifest.can_reference(ws, "public", "peer") is False
    assert manifest.can_reference(ws, "team", "private") is False


def test_unknown_bundle_raises(tmp_path: Path) -> None:
    ws = manifest.load_workspace(_write(tmp_path, SAMPLE))
    with pytest.raises(manifest.ManifestError, match="unknown bundle"):
        manifest.can_reference(ws, "public", "ghost")
    with pytest.raises(manifest.ManifestError, match="unknown bundle"):
        manifest.can_reference(ws, "ghost", "public")


# --- dependency preflight --------------------------------------------------


def test_check_deps_reports_missing_kb(tmp_path: Path) -> None:
    ok, missing = manifest.check_deps(["kb-does-not-exist-xyz"], cwd=tmp_path)
    assert ok is False
    assert "kb-does-not-exist-xyz" in missing


def test_check_deps_finds_project_skill(tmp_path: Path) -> None:
    skill = tmp_path / ".agents" / "skills" / "kb-ingest"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text("---\nname: kb-ingest\n---\n", encoding="utf-8")
    assert manifest.is_kb_installed("kb-ingest", cwd=tmp_path) is True


def test_kb_skills_excludes_promote() -> None:
    assert "kb-promote" not in manifest.KB_SKILLS
    assert "kb-ingest" in manifest.KB_SKILLS


# --- location resolution ---------------------------------------------------


def test_manifest_location_prefers_override() -> None:
    assert manifest.manifest_location("/tmp/x.yaml") == Path("/tmp/x.yaml").resolve()


def test_manifest_location_uses_fkb_workspace(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FKB_WORKSPACE", "/tmp/env.yaml")
    assert manifest.manifest_location() == Path("/tmp/env.yaml").resolve()


def test_manifest_location_falls_back_to_xdg(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("FKB_WORKSPACE", raising=False)
    monkeypatch.setenv("XDG_CONFIG_HOME", "/tmp/xdg")
    assert manifest.manifest_location() == Path("/tmp/xdg/federated-knowledge/workspace.okf.yaml")


# --- CLI exit-code contract (subprocess) -----------------------------------


def _run(manifest_path: Path | None, *args: str) -> subprocess.CompletedProcess[str]:
    env = {"PATH": subprocess.os.environ["PATH"], "HOME": subprocess.os.environ["HOME"]}
    if manifest_path is not None:
        env["FKB_WORKSPACE"] = str(manifest_path)
    return subprocess.run(
        ["uv", "run", "--quiet", str(MANIFEST_PY), *args],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )


def test_cli_validate_ok(tmp_path: Path) -> None:
    r = _run(_write(tmp_path, SAMPLE), "validate")
    assert r.returncode == manifest.Exit.OK


def test_cli_can_reference_allow_and_deny(tmp_path: Path) -> None:
    p = _write(tmp_path, SAMPLE)
    assert _run(p, "can-reference", "peer", "team").returncode == manifest.Exit.OK
    assert _run(p, "can-reference", "public", "private").returncode == manifest.Exit.DENIED


def test_cli_resolve_unknown_bundle(tmp_path: Path) -> None:
    r = _run(_write(tmp_path, SAMPLE), "resolve", "ghost")
    assert r.returncode == manifest.Exit.UNKNOWN_BUNDLE


def test_cli_bad_manifest(tmp_path: Path) -> None:
    r = _run(_write(tmp_path, "bundles:\n  x: { path: rel/docs }\n"), "validate")
    assert r.returncode == manifest.Exit.BAD_MANIFEST


def test_cli_usage_error(tmp_path: Path) -> None:
    r = _run(_write(tmp_path, SAMPLE))
    assert r.returncode == manifest.Exit.USAGE


def test_cli_check_deps_missing(tmp_path: Path) -> None:
    r = _run(None, "check-deps", "kb-does-not-exist-xyz")
    assert r.returncode == manifest.Exit.MISSING_DEP


def test_exit_codes_stable() -> None:
    assert (
        manifest.Exit.OK,
        manifest.Exit.DENIED,
        manifest.Exit.BAD_MANIFEST,
        manifest.Exit.UNKNOWN_BUNDLE,
        manifest.Exit.MISSING_DEP,
        manifest.Exit.USAGE,
    ) == (0, 1, 2, 3, 4, 64)


# --- writer: add_bundle ----------------------------------------------------

WRITER_SAMPLE = """\
# workspace root comment
workspace_root: /ws

bundles:
  # the shared public foundation
  public:  { path: public/docs,  referenceable_by: "*", writable: true, publish: https://me.example/kb }
"""


def test_add_bundle_appends_and_preserves_comments(tmp_path: Path) -> None:
    p = _write(tmp_path, WRITER_SAMPLE)
    manifest.add_bundle(p, "team", "team/docs", manifest.BundlePolicy(referenceable_by=["peer"], writable=True))
    text = p.read_text()
    assert "# workspace root comment" in text
    assert "# the shared public foundation" in text
    ws = manifest.load_workspace(p)
    assert list(ws.bundles) == ["public", "team"]  # append last, order preserved
    assert ws.bundles["team"].referenceable_by == ["peer"]
    assert ws.bundles["team"].writable is True


def test_add_bundle_fail_closed_defaults(tmp_path: Path) -> None:
    p = _write(tmp_path, WRITER_SAMPLE)
    manifest.add_bundle(p, "sealed", "sealed/docs", manifest.BundlePolicy())
    ws = manifest.load_workspace(p)
    sealed = ws.bundles["sealed"]
    assert sealed.referenceable_by == []
    assert sealed.writable is False
    assert sealed.publish is None


def test_add_bundle_duplicate_raises(tmp_path: Path) -> None:
    p = _write(tmp_path, WRITER_SAMPLE)
    with pytest.raises(manifest.ManifestError, match="already exists"):
        manifest.add_bundle(p, "public", "other/docs", manifest.BundlePolicy())


def test_add_bundle_missing_manifest_raises(tmp_path: Path) -> None:
    with pytest.raises(manifest.ManifestError, match="no workspace configured"):
        manifest.add_bundle(tmp_path / "nope.yaml", "x", "x/docs", manifest.BundlePolicy())


def test_add_bundle_wildcard_referenceable_by(tmp_path: Path) -> None:
    p = _write(tmp_path, WRITER_SAMPLE)
    manifest.add_bundle(p, "shared", "shared/docs", manifest.BundlePolicy(referenceable_by="*"))
    ws = manifest.load_workspace(p)
    assert ws.bundles["shared"].referenceable_by == "*"


def test_cli_add_bundle_and_reparse(tmp_path: Path) -> None:
    p = _write(tmp_path, WRITER_SAMPLE)
    r = _run(p, "add-bundle", "peer", "peer/docs", "--referenceable-by", "team", "--writable")
    assert r.returncode == manifest.Exit.OK
    assert _run(p, "validate").returncode == manifest.Exit.OK


def test_cli_add_bundle_duplicate_exit(tmp_path: Path) -> None:
    p = _write(tmp_path, WRITER_SAMPLE)
    r = _run(p, "add-bundle", "public", "x/docs")
    assert r.returncode == manifest.Exit.BAD_MANIFEST


def test_add_bundle_into_empty_federation(tmp_path: Path) -> None:
    p = _write(tmp_path, "workspace_root: /ws\nbundles:\n")
    manifest.add_bundle(p, "first", "first/docs", manifest.BundlePolicy(referenceable_by="*"))
    ws = manifest.load_workspace(p)
    assert list(ws.bundles) == ["first"]
    assert "workspace_root" in p.read_text()
