"""Shared fixtures for the end-to-end test harness.

The `skills` tests are true end-to-end tests: they build an isolated fake HOME
(see tests/fake_home.py), install a pinned opencode into it, place skills under
`~/.agents/skills` exactly as a user would, then drive `opencode run` and inspect
the artifacts and output.

On failure, the fake home is preserved and a copy-pasteable command to enter it
is printed, so a run can be inspected by hand.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fake_home import FakeHome, build_fake_home


@pytest.fixture
def empty_home(tmp_path: Path) -> FakeHome:
    """A fake home with opencode installed and no skills at all."""
    # pytest keeps the last few `tmp_path` roots on disk by default, so a failing
    # run's fake home survives long enough to inspect (path is printed on failure).
    return build_fake_home(tmp_path, skills_dir=None)


@pytest.fixture
def home_factory(tmp_path: Path):
    """Build a fake home with skills taken from a caller-supplied directory.

    Lets a test author a skill on the fly and install it, so the harness can be
    exercised without depending on whichever skills this repo currently ships.
    """
    built: list[FakeHome] = []

    def _build(skills_dir: Path | None) -> FakeHome:
        home = build_fake_home(tmp_path / f"home{len(built)}", skills_dir=skills_dir)
        built.append(home)
        return home

    _build.built = built  # type: ignore[attr-defined]
    return _build


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    """On failure of a test that used a fake home, print how to enter it."""
    outcome = yield
    report = outcome.get_result()
    if report.when != "call" or not report.failed:
        return
    funcargs = getattr(item, "funcargs", {}) or {}
    candidates: list[FakeHome] = [v for v in funcargs.values() if isinstance(v, FakeHome)]
    factory = funcargs.get("home_factory")
    candidates.extend(getattr(factory, "built", []))
    for fake in candidates:
        report.sections.append(
            (
                "Fake home (inspect it)",
                fake.enter_hint(reason=f"Test {item.name!r} failed."),
            )
        )
        break
