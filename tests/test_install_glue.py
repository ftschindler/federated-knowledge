"""Behavior lock for install-glue (skills/fkb/scripts/install-glue).

Drives the script as a subprocess in an isolated XDG config home, so nothing
touches the developer's real ~/.config.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.python_scripts

REPO_ROOT = Path(__file__).resolve().parent.parent
INSTALL_GLUE = REPO_ROOT / "skills" / "fkb" / "scripts" / "install-glue"


def _run(xdg: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = {
        "PATH": subprocess.os.environ["PATH"],
        "HOME": subprocess.os.environ["HOME"],
        "XDG_CONFIG_HOME": str(xdg),
    }
    return subprocess.run(
        ["uv", "run", "--quiet", str(INSTALL_GLUE), *args],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )


def _cfg(xdg: Path) -> Path:
    return xdg / "federated-knowledge"


def test_creates_config_dir_and_starter_manifest(tmp_path: Path) -> None:
    xdg = tmp_path / "xdg"
    r = _run(xdg, "--root", "~/mykb")
    assert r.returncode == 0
    manifest = _cfg(xdg) / "workspace.okf.yaml"
    assert manifest.is_file()
    text = manifest.read_text()
    assert "workspace_root: ~/mykb" in text
    assert "bundles:" in text


def test_copies_helper_scripts(tmp_path: Path) -> None:
    xdg = tmp_path / "xdg"
    _run(xdg)
    cfg = _cfg(xdg)
    assert (cfg / "manifest.py").is_file()
    assert (cfg / "install-glue").is_file()


def test_default_workspace_root(tmp_path: Path) -> None:
    xdg = tmp_path / "xdg"
    _run(xdg)
    text = (_cfg(xdg) / "workspace.okf.yaml").read_text()
    assert "workspace_root: ~/.agents/knowledge" in text


def test_rerun_keeps_existing_manifest(tmp_path: Path) -> None:
    xdg = tmp_path / "xdg"
    _run(xdg)
    manifest = _cfg(xdg) / "workspace.okf.yaml"
    manifest.write_text(manifest.read_text() + "\n# user edit\n", encoding="utf-8")
    r = _run(xdg)
    assert r.returncode == 0
    assert "# user edit" in manifest.read_text()


def test_print_agents_block_is_marker_wrapped(tmp_path: Path) -> None:
    xdg = tmp_path / "xdg"
    r = _run(xdg, "--print-agents-block")
    assert r.returncode == 0
    assert r.stdout.startswith("<!-- BEGIN fkb")
    assert r.stdout.rstrip().endswith("<!-- END fkb -->")
    assert "fkb-query" in r.stdout
    assert "referenceable_by" in r.stdout


def test_print_agents_block_does_not_touch_disk(tmp_path: Path) -> None:
    xdg = tmp_path / "xdg"
    _run(xdg, "--print-agents-block")
    assert not _cfg(xdg).exists()


def test_copied_core_runs_from_config_dir(tmp_path: Path) -> None:
    xdg = tmp_path / "xdg"
    _run(xdg)
    cfg = _cfg(xdg)
    env = {
        "PATH": subprocess.os.environ["PATH"],
        "HOME": subprocess.os.environ["HOME"],
        "XDG_CONFIG_HOME": str(xdg),
    }
    r = subprocess.run(
        ["uv", "run", "--quiet", str(cfg / "manifest.py"), "validate"],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    assert r.returncode == 0
    assert "0 bundle(s)" in r.stdout


def test_scripts_resolve_via_xdg_shell_form(tmp_path: Path) -> None:
    xdg = tmp_path / "custom-xdg"
    _run(xdg)
    env = {
        "PATH": subprocess.os.environ["PATH"],
        "HOME": subprocess.os.environ["HOME"],
        "XDG_CONFIG_HOME": str(xdg),
    }
    r = subprocess.run(
        'uv run "${XDG_CONFIG_HOME:-$HOME/.config}/federated-knowledge/manifest.py" validate',
        shell=True,
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    assert r.returncode == 0, r.stderr


def test_starter_manifest_emits_literal_xdg_form(tmp_path: Path) -> None:
    xdg = tmp_path / "xdg"
    _run(xdg)
    text = (_cfg(xdg) / "workspace.okf.yaml").read_text()
    assert '"${XDG_CONFIG_HOME:-$HOME/.config}/federated-knowledge/clone-bundle"' in text
