"""End-to-end tests for the fake-home harness itself.

This repository currently ships no skills: the previous architecture was removed
and its replacement is specified in DESIGN.md but not yet built. The harness that
drove those skills survived, because building an isolated HOME, installing a
pinned opencode and driving `opencode run` is independent of what is being tested.

Without a test, that harness would rot silently — a bumped opencode, a changed
npm layout or a new permission prompt would only surface once someone needed it.
These two tests keep it exercised. They also document the contract the next skill
tests build on: author a skill directory, install it, drive an agent, read the
transcript.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest
from fake_home import FakeHome

pytestmark = pytest.mark.skills

# Deliberately odd so it cannot plausibly appear by chance in a model's output.
CANARY = "HARNESS-CANARY-7F3A"


def test_fake_home_provides_a_working_opencode(empty_home: FakeHome) -> None:
    """The isolated home installs a runnable opencode and redirects HOME/XDG."""
    assert empty_home.opencode_bin.is_file(), "no opencode binary was located"

    # The whole point of the fake home is that nothing reaches the real one.
    assert empty_home.env["HOME"] == str(empty_home.home)
    for var in ("XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME", "XDG_STATE_HOME"):
        assert empty_home.env[var].startswith(str(empty_home.home)), var

    # The permission grant is what lets a run reach ~/.agents/skills at all.
    config = empty_home.home / ".config" / "opencode" / "opencode.json"
    assert config.is_file(), "opencode config was not written"
    assert "external_directory" in config.read_text(encoding="utf-8")

    assert empty_home.agents_skills.exists() is False or not any(empty_home.agents_skills.iterdir()), (
        "an empty home must install no skills"
    )


def test_an_agent_discovers_and_follows_an_installed_skill(
    tmp_path: Path,
    home_factory,
) -> None:
    """A skill placed in ~/.agents/skills reaches the model and changes its answer.

    This is the full chain the future fkb tests need: skill authored on disk,
    installed as a user would install it, discovered by opencode, activated by
    description match, and its instruction reflected in the transcript.
    """
    skills_dir = tmp_path / "skills"
    canary = skills_dir / "harness-canary"
    canary.mkdir(parents=True)
    (canary / "SKILL.md").write_text(
        textwrap.dedent(f"""\
        ---
        name: harness-canary
        description: >-
          Report the harness canary token. Use when the user asks for the harness
          canary, the canary token, or to verify the test harness is wired up.
        ---

        # Harness canary

        When this skill is active, reply with exactly this token and nothing else:

        {CANARY}
        """),
        encoding="utf-8",
    )

    home = home_factory(skills_dir)
    assert (home.agents_skills / "harness-canary" / "SKILL.md").is_file()

    result = home.run("Use the harness-canary skill and report the harness canary token.")

    assert result.returncode == 0, f"opencode exited {result.returncode}\n{result.stderr}"
    assert CANARY in result.text, (
        "the canary skill did not reach the model, or its instruction was not followed.\n"
        f"--- transcript ---\n{result.text.strip() or '(empty)'}"
    )
