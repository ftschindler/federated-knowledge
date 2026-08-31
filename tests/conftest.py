"""Shared fixtures for the federated-knowledge test suite.

The `skills` tests are true end-to-end tests: they build an isolated fake HOME
(see tests/fake_home.py), install a pinned opencode into it, place the fkb skills
(and, for most tests, the real kb skills) under `~/.agents/skills` exactly as a
user would, then drive `opencode run` and inspect the artifacts and output.

On failure, the fake home is preserved and a copy-pasteable command to enter it
is printed, so a run can be inspected by hand.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest
from fake_home import FakeHome, build_fake_home

# The public bundle used as a deterministic content anchor for e2e tests. Its
# knowledge/ subdir is a conformant OKF bundle whose OKF root is auto-discovered
# by clone-bundle, and it carries a known entry we can assert a query surfaces.
AGENT_KNOWLEDGE_URL = "https://github.com/stjbrown/agent-knowledge"
AGENT_KNOWLEDGE_OKF_SUBDIR = "knowledge"
AGENT_KNOWLEDGE_KNOWN_ENTRY = "references/karpathy_llm_wiki.md"


@dataclass(frozen=True)
class AgentKnowledgeFixture:
    """A once-cloned agent-knowledge checkout, shared read-only across e2e tests."""

    repo_url: str
    checkout: Path
    okf_subdir: str
    known_entry: str

    @property
    def okf_root(self) -> Path:
        return self.checkout / self.okf_subdir

    @property
    def known_entry_path(self) -> Path:
        return self.okf_root / self.known_entry


@pytest.fixture(scope="session")
def agent_knowledge(tmp_path_factory: pytest.TempPathFactory) -> AgentKnowledgeFixture:
    checkout = tmp_path_factory.mktemp("agent-knowledge") / "repo"
    subprocess.run(
        ["git", "clone", "--depth", "1", "--quiet", AGENT_KNOWLEDGE_URL, str(checkout)],
        check=True,
        capture_output=True,
        text=True,
        timeout=300,
    )
    fixture = AgentKnowledgeFixture(
        repo_url=AGENT_KNOWLEDGE_URL,
        checkout=checkout,
        okf_subdir=AGENT_KNOWLEDGE_OKF_SUBDIR,
        known_entry=AGENT_KNOWLEDGE_KNOWN_ENTRY,
    )
    if not fixture.known_entry_path.is_file():
        pytest.fail(f"expected known entry missing: {fixture.known_entry_path}")
    return fixture


def _make_home(tmp_path, *, with_kb: bool) -> FakeHome:
    # pytest keeps the last few `tmp_path` roots on disk by default, so a failing
    # run's fake home survives long enough to inspect (path is printed on failure).
    return build_fake_home(tmp_path, with_kb=with_kb)


@pytest.fixture
def kb_absent_home(tmp_path) -> FakeHome:
    """Fake home with ONLY the fkb skills — kb is deliberately not installed."""
    return _make_home(tmp_path, with_kb=False)


@pytest.fixture
def kb_present_home(tmp_path) -> FakeHome:
    """Fake home with fkb skills AND the real kb skills installed (happy path)."""
    return _make_home(tmp_path, with_kb=True)


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    """On failure of a test that used a fake home, print how to enter it."""
    outcome = yield
    report = outcome.get_result()
    if report.when != "call" or not report.failed:
        return
    for name in ("kb_absent_home", "kb_present_home"):
        fake = item.funcargs.get(name) if hasattr(item, "funcargs") else None
        if isinstance(fake, FakeHome):
            report.sections.append(
                (
                    "Fake home (inspect it)",
                    fake.enter_hint(reason=f"Test {item.name!r} failed."),
                )
            )
            break
