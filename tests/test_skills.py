"""End-to-end tests: drive opencode against the fkb skills in a fake home.

Slow (installs opencode, runs an LLM) and non-deterministic by nature, so these
assert on STRUCTURAL outcomes (did a file land in the right bundle? did the loud
failure guidance appear?) rather than exact prose.
"""

from __future__ import annotations

import subprocess

import pytest
from fake_home import FakeHome

pytestmark = pytest.mark.skills


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
    assert "npx skills add stjbrown/agent-knowledge" in combined or "check-kb" in combined
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


def test_check_kb_preflight_passes_when_kb_present(kb_present_home: FakeHome) -> None:
    """The deterministic half: check-kb must pass once kb is installed alongside."""
    manifest = kb_present_home.agents_skills / "fkb" / "scripts" / "manifest.mjs"
    proc = subprocess.run(
        ["node", str(manifest), "check-kb"],
        env=kb_present_home.env,
        cwd=kb_present_home.home,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
