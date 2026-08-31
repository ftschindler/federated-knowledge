from __future__ import annotations

import subprocess
from pathlib import Path
from typing import TYPE_CHECKING, Final

import pytest

if TYPE_CHECKING:
    from conftest import AgentKnowledgeFixture

pytestmark = pytest.mark.python_scripts

REPO_ROOT: Final = Path(__file__).resolve().parent.parent
SCRIPTS: Final = REPO_ROOT / "skills" / "fkb" / "scripts"
INSTALL_GLUE: Final = SCRIPTS / "install-glue"


def _base_env(cfg: Path) -> dict[str, str]:
    return {
        "PATH": subprocess.os.environ["PATH"],
        "HOME": subprocess.os.environ["HOME"],
        "XDG_CONFIG_HOME": str(cfg.parent),
    }


def _setup(tmp_path: Path, workspace_root: Path) -> Path:
    xdg = tmp_path / "xdg"
    subprocess.run(
        ["uv", "run", "--quiet", str(INSTALL_GLUE), "--root", str(workspace_root)],
        capture_output=True,
        text=True,
        check=True,
        env={
            "PATH": subprocess.os.environ["PATH"],
            "HOME": subprocess.os.environ["HOME"],
            "XDG_CONFIG_HOME": str(xdg),
        },
    )
    return xdg / "federated-knowledge"


def _run(cfg: Path, script: str, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["uv", "run", "--quiet", str(cfg / script), *args],
        capture_output=True,
        text=True,
        check=False,
        stdin=subprocess.DEVNULL,
        env=_base_env(cfg),
    )


def _manifest_text(cfg: Path) -> str:
    return (cfg / "workspace.okf.yaml").read_text(encoding="utf-8")


def test_onboarding_clone_bundle_registers_okf_root_and_known_anchor(
    tmp_path: Path,
    agent_knowledge: AgentKnowledgeFixture,
) -> None:
    workspace_root = tmp_path / "workspace"
    cfg = _setup(tmp_path, workspace_root)

    installed_clone_bundle = cfg / "clone-bundle"
    installed_manifest = cfg / "manifest.py"
    assert installed_clone_bundle.is_file()
    assert installed_manifest.is_file()

    bundle_name = "agent-knowledge-clone"
    clone_result = _run(cfg, "clone-bundle", f"file://{agent_knowledge.checkout}", bundle_name, "*")
    assert clone_result.returncode == 0, clone_result.stderr

    manifest_text = _manifest_text(cfg)
    assert f"{bundle_name}: {{path: {bundle_name}/{agent_knowledge.okf_subdir}" in manifest_text
    assert "referenceable_by: '*'" in manifest_text
    assert "writable: false" in manifest_text

    cloned_checkout = workspace_root / bundle_name
    cloned_okf_root = cloned_checkout / agent_knowledge.okf_subdir
    assert cloned_checkout.is_dir()
    assert cloned_okf_root.is_dir()
    assert (cloned_okf_root / "index.md").is_file()
    assert (cloned_okf_root / agent_knowledge.known_entry).is_file()

    validate_result = _run(cfg, "manifest.py", "validate")
    assert validate_result.returncode == 0, validate_result.stderr


def test_onboarding_add_bundle_in_place_and_enforces_reference_policy(
    tmp_path: Path,
    agent_knowledge: AgentKnowledgeFixture,
) -> None:
    workspace_root = tmp_path / "workspace"
    cfg = _setup(tmp_path, workspace_root)

    clone_name = "public-foundation"
    clone_result = _run(cfg, "clone-bundle", f"file://{agent_knowledge.checkout}", clone_name, "*")
    assert clone_result.returncode == 0, clone_result.stderr

    added_name = "sealed-local"
    add_result = _run(cfg, "add-bundle", added_name, str(agent_knowledge.okf_root), "[]")
    assert add_result.returncode == 0, add_result.stderr

    manifest_text = _manifest_text(cfg)
    assert f"{added_name}: {{path: {agent_knowledge.okf_root}" in manifest_text
    assert f"{clone_name}: {{path: {clone_name}/{agent_knowledge.okf_subdir}" in manifest_text

    cloned_checkout = workspace_root / clone_name
    assert cloned_checkout.is_dir()
    assert agent_knowledge.okf_root.is_dir()
    assert (cloned_checkout / agent_knowledge.okf_subdir / agent_knowledge.known_entry).is_file()
    assert agent_knowledge.known_entry_path.is_file()

    allow_result = _run(cfg, "manifest.py", "can-reference", added_name, clone_name)
    assert allow_result.returncode == 0, allow_result.stderr
    assert allow_result.stdout.strip() == f"ALLOW {added_name} -> {clone_name}"

    deny_result = _run(cfg, "manifest.py", "can-reference", clone_name, added_name)
    assert deny_result.returncode == 1, deny_result.stderr
    assert deny_result.stdout.strip() == (
        f"DENY {clone_name} -> {added_name}  ({added_name}.referenceable_by does not include {clone_name})"
    )

    validate_result = _run(cfg, "manifest.py", "validate")
    assert validate_result.returncode == 0, validate_result.stderr
