"""Behavior lock for the fkb bundle commands (add-bundle, create-bundle, clone-bundle).

Drives each command as a subprocess with a fresh workspace in an isolated config
home. Prompts are suppressed by closing stdin (non-interactive => fail-closed
defaults or passed flags), which is exactly how the fkb-init skill drives them.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.python_scripts

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = REPO_ROOT / "skills" / "fkb" / "scripts"
INSTALL_GLUE = SCRIPTS / "install-glue"


def _base_env(manifest_path: Path) -> dict[str, str]:
    return {
        "PATH": subprocess.os.environ["PATH"],
        "HOME": subprocess.os.environ["HOME"],
        "FKB_WORKSPACE": str(manifest_path),
    }


def _setup(tmp_path: Path, root: Path) -> Path:
    xdg = tmp_path / "xdg"
    subprocess.run(
        ["uv", "run", "--quiet", str(INSTALL_GLUE), "--root", str(root)],
        capture_output=True,
        text=True,
        check=True,
        env={
            "PATH": subprocess.os.environ["PATH"],
            "HOME": subprocess.os.environ["HOME"],
            "XDG_CONFIG_HOME": str(xdg),
        },
    )
    return xdg / "federated-knowledge" / "workspace.okf.yaml"


def _run(manifest_path: Path, script: str, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["uv", "run", "--quiet", str(SCRIPTS / script), *args],
        capture_output=True,
        text=True,
        check=False,
        stdin=subprocess.DEVNULL,
        env=_base_env(manifest_path),
    )


def _manifest_text(manifest_path: Path) -> str:
    return manifest_path.read_text()


# --- add-bundle ------------------------------------------------------------


def test_add_bundle_registers_in_place(tmp_path: Path) -> None:
    manifest_path = _setup(tmp_path, tmp_path / "kb")
    existing = tmp_path / "elsewhere" / "docs"
    existing.mkdir(parents=True)
    (existing / "index.md").write_text("# x\n", encoding="utf-8")
    r = _run(manifest_path, "add-bundle", "acme", str(existing), "[team]")
    assert r.returncode == 0
    text = _manifest_text(manifest_path)
    assert f"path: {existing}" in text
    assert "writable: false" in text  # fail-closed when not asked


def test_add_bundle_writable_flag(tmp_path: Path) -> None:
    manifest_path = _setup(tmp_path, tmp_path / "kb")
    d = tmp_path / "d"
    d.mkdir()
    r = _run(manifest_path, "add-bundle", "b", str(d), "*", "--writable")
    assert r.returncode == 0
    assert "writable: true" in _manifest_text(manifest_path)


def test_add_bundle_duplicate_fails(tmp_path: Path) -> None:
    manifest_path = _setup(tmp_path, tmp_path / "kb")
    d = tmp_path / "d"
    d.mkdir()
    assert _run(manifest_path, "add-bundle", "b", str(d)).returncode == 0
    assert _run(manifest_path, "add-bundle", "b", str(d)).returncode != 0


# --- create-bundle ---------------------------------------------------------


def test_create_bundle_scaffolds_and_registers(tmp_path: Path) -> None:
    root = tmp_path / "kb"
    manifest_path = _setup(tmp_path, root)
    r = _run(manifest_path, "create-bundle", "notes", "[]")
    assert r.returncode == 0
    assert (root / "notes" / "index.md").is_file()
    assert (root / "notes" / "log.md").is_file()
    text = _manifest_text(manifest_path)
    assert "notes: {path: notes" in text
    assert "writable: true" in text  # a bundle you author into defaults writable


# --- clone-bundle ----------------------------------------------------------


def _make_remote(tmp_path: Path, *, in_docs_subdir: bool) -> Path:
    remote = tmp_path / "remote"
    content = remote / "docs" if in_docs_subdir else remote
    content.mkdir(parents=True)
    (content / "index.md").write_text("# remote\n", encoding="utf-8")
    (content / "log.md").write_text("# Log\n", encoding="utf-8")
    for cmd in (["init", "-q"], ["add", "-A"]):
        subprocess.run(["git", *cmd], cwd=remote, check=True, capture_output=True)
    subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "init"],
        cwd=remote,
        check=True,
        capture_output=True,
    )
    return remote


def test_clone_bundle_discovers_docs_subdir(tmp_path: Path) -> None:
    root = tmp_path / "kb"
    manifest_path = _setup(tmp_path, root)
    remote = _make_remote(tmp_path, in_docs_subdir=True)
    r = _run(manifest_path, "clone-bundle", f"file://{remote}", "upstream", "*")
    assert r.returncode == 0, r.stderr
    assert (root / "upstream" / "docs" / "index.md").is_file()
    assert "path: upstream/docs" in _manifest_text(manifest_path)
    assert "writable: false" in _manifest_text(manifest_path)  # cloned = source, fail-closed


def test_clone_bundle_root_level_index(tmp_path: Path) -> None:
    root = tmp_path / "kb"
    manifest_path = _setup(tmp_path, root)
    remote = _make_remote(tmp_path, in_docs_subdir=False)
    r = _run(manifest_path, "clone-bundle", f"file://{remote}", "up2")
    assert r.returncode == 0, r.stderr
    assert "path: up2" in _manifest_text(manifest_path)


def test_clone_bundle_existing_dir_fails(tmp_path: Path) -> None:
    root = tmp_path / "kb"
    manifest_path = _setup(tmp_path, root)
    (root / "taken").mkdir(parents=True)
    remote = _make_remote(tmp_path, in_docs_subdir=True)
    r = _run(manifest_path, "clone-bundle", f"file://{remote}", "taken")
    assert r.returncode != 0
