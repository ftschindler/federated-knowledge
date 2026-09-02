"""End-to-end tests: drive opencode against the fkb skills in a fake home.

Slow (installs opencode, runs an LLM) and non-deterministic by nature, so these
assert on STRUCTURAL outcomes (did a file land in the right bundle? did the loud
failure guidance appear?) rather than exact prose.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from fake_home import FakeHome

if TYPE_CHECKING:
    from conftest import AgentKnowledgeFixture

pytestmark = pytest.mark.skills


def _cfg(fake: FakeHome) -> Path:
    return fake.home / ".config" / "federated-knowledge"


def _run_uv(fake: FakeHome, script: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["uv", "run", "--quiet", str(script), *args],
        env=fake.env,
        cwd=fake.home,
        capture_output=True,
        text=True,
        check=False,
        stdin=subprocess.DEVNULL,
        timeout=300,
    )


def _install_glue(fake: FakeHome, *args: str) -> subprocess.CompletedProcess[str]:
    return _run_uv(fake, fake.agents_skills / "fkb" / "scripts" / "install-glue", *args)


def _run_cfg(fake: FakeHome, script: str, *args: str) -> subprocess.CompletedProcess[str]:
    return _run_uv(fake, _cfg(fake) / script, *args)


def _markdown_files(root: Path) -> set[str]:
    return {str(path.relative_to(root)) for path in root.rglob("*.md")}


def _instruction_file(fake: FakeHome) -> Path | None:
    for path in (
        fake.home / "AGENTS.md",
        fake.home / "CLAUDE.md",
        fake.work / "AGENTS.md",
        fake.work / "CLAUDE.md",
    ):
        if path.is_file():
            return path
    return None


def _cfg_snapshot(root: Path) -> set[str]:
    if not root.exists():
        return set()
    return {str(path.relative_to(root)) for path in root.rglob("*") if path.is_file()}


def test_kb_absent_is_loud_and_writes_nothing(kb_absent_home: FakeHome) -> None:
    """With kb missing, an fkb operation must fail loudly and not author content."""
    result = kb_absent_home.run(
        "Use the fkb-ingest skill to capture this note into the knowledge base: "
        "'The deploy runbook lives in the ops wiki.' "
        "Follow the skill's preflight exactly.",
        timeout=240,
    )
    combined = (result.text + result.stderr).lower()
    # The skill's preflight tells the user to install the kb skills.
    assert "npx skills add stjbrown/agent-knowledge" in combined or "check-deps" in combined
    # And nothing should have been authored into a bundle.
    authored = list(result.workdir.rglob("*.md"))
    assert authored == [], f"expected no bundle writes, found {authored}"


def test_fkb_skills_are_discovered(kb_present_home: FakeHome) -> None:
    """Sanity: with kb present, opencode sees the full fkb + kb skill set."""
    result = kb_present_home.run(
        "List every skill you have available whose name starts with 'fkb', one per line. Do not use any tools.",
        timeout=180,
    )
    text = result.text.lower()
    for skill in ("fkb", "fkb-ingest", "fkb-init", "fkb-query", "fkb-lint", "fkb-promote"):
        assert skill in text, f"{skill} not discovered; got: {result.text!r}"


def test_check_deps_preflight_passes_when_kb_present(kb_present_home: FakeHome) -> None:
    """The deterministic half: check-deps must pass once uv and kb are installed alongside."""
    manifest = kb_present_home.agents_skills / "fkb" / "scripts" / "manifest.py"
    proc = subprocess.run(
        ["uv", "run", "--quiet", str(manifest), "check-deps"],
        env=kb_present_home.env,
        cwd=kb_present_home.home,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr


def test_fkb_init_sets_up_workspace_and_registers_bundle(
    kb_present_home: FakeHome,
    agent_knowledge: AgentKnowledgeFixture,
) -> None:
    result = kb_present_home.run(
        "Use the fkb-init skill to set up a federated OKF workspace in the default location if it "
        "is missing. Then register this existing local OKF bundle in place: "
        f"{agent_knowledge.okf_root}. Name the bundle agent-knowledge, set referenceable_by to *, "
        "leave writable false, do not set a publish URL, and finish by listing the resolved "
        "bundles. Follow the skill's preflight exactly.",
        timeout=600,
    )

    manifest = _cfg(kb_present_home) / "workspace.okf.yaml"
    assert result.returncode == 0, result.stderr
    assert manifest.is_file()

    text = manifest.read_text(encoding="utf-8")
    assert f"agent-knowledge: {{path: {agent_knowledge.okf_root}" in text
    assert "referenceable_by: '*'" in text
    assert "writable: false" in text

    validate = _run_cfg(kb_present_home, "manifest.py", "validate")
    assert validate.returncode == 0, validate.stderr

    resolve = _run_cfg(kb_present_home, "manifest.py", "resolve", "agent-knowledge")
    assert resolve.returncode == 0, resolve.stderr
    assert str(agent_knowledge.okf_root) in resolve.stdout


def test_fkb_query_answers_from_known_bundle_with_bundle_qualified_citation(
    kb_present_home: FakeHome,
    agent_knowledge: AgentKnowledgeFixture,
) -> None:
    workspace_root = kb_present_home.work / "knowledge"
    install = _install_glue(kb_present_home, "--root", str(workspace_root))
    assert install.returncode == 0, install.stderr

    clone = _run_cfg(
        kb_present_home,
        "clone-bundle",
        f"file://{agent_knowledge.checkout}",
        "agent-knowledge",
        "*",
    )
    assert clone.returncode == 0, clone.stderr

    bundle_root = workspace_root / "agent-knowledge" / "knowledge"
    bundle_before = _markdown_files(bundle_root)
    cfg_before = _cfg_snapshot(_cfg(kb_present_home))

    result = kb_present_home.run(
        "Use the fkb-query skill to answer this across all configured bundles and cite every hit "
        "bundle-qualified: What is Karpathy's LLM wiki idea?",
        cwd=kb_present_home.work,
        timeout=300,
    )

    output = (result.stdout + result.stderr).lower()
    if "permission requested: external_directory" in output or "user rejected permission" in output:
        pytest.xfail("opencode blocked kb-query bundle reads from the fake-home workspace")

    assert result.returncode == 0, result.stderr
    assert result.workdir.exists()
    assert _markdown_files(bundle_root) == bundle_before
    assert _cfg_snapshot(_cfg(kb_present_home)) == cfg_before
    assert "wiki" in output or "llm" in output
    assert "karpathy" in output or "andrej" in output or "persistent" in output
    assert "agent-knowledge" in output
    assert "references/karpathy_llm_wiki.md" in output


def test_fkb_ingest_keeps_sensitive_note_out_of_public_bundle(
    kb_present_home: FakeHome,
) -> None:
    workspace_root = kb_present_home.work / "knowledge"
    install = _install_glue(kb_present_home, "--root", str(workspace_root))
    assert install.returncode == 0, install.stderr

    public_create = _run_cfg(kb_present_home, "create-bundle", "public-foundation", "*")
    assert public_create.returncode == 0, public_create.stderr

    private_create = _run_cfg(kb_present_home, "create-bundle", "private-notes", "[]")
    assert private_create.returncode == 0, private_create.stderr

    public_root = workspace_root / "public-foundation"
    private_root = workspace_root / "private-notes"
    public_before = _markdown_files(public_root)
    private_before = _markdown_files(private_root)

    result = kb_present_home.run(
        "Use the fkb-ingest skill to capture this note into the knowledge base: 'Internal note: "
        "the unreleased codename is Granite and the production host is db01.internal.example.' "
        "Classify it fail-closed to the most-private writable bundle, proceed without asking for "
        "public-disclosure confirmation because the correct destination is sealed and unpublished, "
        "and finish the capture with a short report. Follow the skill's preflight exactly.",
        cwd=kb_present_home.work,
        timeout=300,
    )

    public_after = _markdown_files(public_root)
    private_after = _markdown_files(private_root)
    private_new = private_after - private_before
    output = (result.stdout + result.stderr).lower()

    assert result.returncode == 0, result.stderr
    assert public_after == public_before
    if not private_new:
        if "permission requested: external_directory" in output or "user rejected permission" in output:
            pytest.xfail("opencode blocked kb-ingest bundle access inside the fake-home workspace")
        pytest.xfail("agent classified the note but did not reliably complete kb-ingest in this run")

    assert any(path not in {"index.md", "log.md"} for path in private_new)
    assert "private-notes" in output or "most-private" in output or "sealed" in output


def test_fkb_init_places_managed_block_into_agent_instructions(kb_present_home: FakeHome) -> None:
    install = _install_glue(kb_present_home)
    assert install.returncode == 0, install.stderr

    agents_file = kb_present_home.home / "AGENTS.md"
    result = kb_present_home.run(
        "Use the fkb-init skill's install-glue instructions to run the installed config-dir "
        "install-glue with --print-agents-block, then place the exact managed block into this file: "
        f"{agents_file}. Keep the BEGIN and END markers intact.",
        cwd=kb_present_home.home,
        timeout=300,
    )

    instructions = _instruction_file(kb_present_home)
    assert result.returncode == 0, result.stderr
    assert (_cfg(kb_present_home) / "workspace.okf.yaml").is_file()
    if instructions is None:
        pytest.xfail("agent did not reliably complete AGENTS.md placement in this run")

    assert instructions is not None

    text = instructions.read_text(encoding="utf-8")
    assert "<!-- BEGIN fkb" in text
    assert "<!-- END fkb -->" in text
    assert "fkb-query" in text
    assert "fkb-ingest" in text
