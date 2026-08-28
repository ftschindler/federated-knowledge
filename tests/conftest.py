"""Shared fixtures for the federated-knowledge test suite.

The `skills` tests are true end-to-end tests: they build an isolated fake HOME,
install a pinned opencode into it, place the fkb skills (and, for most tests, the
real kb skills) under `~/.agents/skills` exactly as a user would, then drive
`opencode run` and inspect the artifacts and output.

Everything is redirected into a temp dir (HOME + XDG_*), so nothing touches the
developer's real machine or config.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

import pytest

# Pinned so the e2e behaviour is reproducible; bump deliberately like our other
# frozen tool versions.
OPENCODE_VERSION = "1.18.25"

# The upstream kb skills the fkb layer delegates to.
KB_REPO = "stjbrown/agent-knowledge"

REPO_ROOT = Path(__file__).resolve().parent.parent
FKB_SKILLS_DIR = REPO_ROOT / "skills"


def _have(cmd: str) -> bool:
    return shutil.which(cmd) is not None


# A single gate for the whole e2e layer: skip cleanly when the machine cannot
# run it (offline, no node/npm), so `make test` still passes offline.
requires_e2e = pytest.mark.skipif(
    not (_have("node") and _have("npm") and _have("npx")),
    reason="e2e skill tests need node/npm/npx available",
)


@dataclass
class FakeHome:
    """An isolated opencode environment rooted at a temp HOME."""

    home: Path
    opencode_bin: Path
    env: dict[str, str] = field(default_factory=dict)

    @property
    def agents_skills(self) -> Path:
        return self.home / ".agents" / "skills"

    def install_fkb(self) -> None:
        """Place the repo's fkb skills under ~/.agents/skills (as a user would)."""
        self.agents_skills.mkdir(parents=True, exist_ok=True)
        for skill in FKB_SKILLS_DIR.iterdir():
            if skill.is_dir():
                shutil.copytree(skill, self.agents_skills / skill.name, dirs_exist_ok=True)

    def install_kb(self) -> None:
        """Install the real kb skills into ~/.agents/skills only, via skills.sh."""
        subprocess.run(
            [
                "npx",
                "--yes",
                "skills",
                "add",
                KB_REPO,
                "--skill",
                "*",
                "-a",
                "opencode",
                "-g",
                "-y",
                "--copy",
            ],
            check=True,
            env=self.env,
            cwd=self.home,
            capture_output=True,
            text=True,
            timeout=300,
        )

    def run(self, message: str, *, cwd: Path | None = None, timeout: int = 180) -> OpencodeResult:
        """Drive `opencode run` non-interactively and capture parsed JSON events."""
        workdir = cwd or (self.home / "work")
        workdir.mkdir(parents=True, exist_ok=True)
        proc = subprocess.run(
            [str(self.opencode_bin), "run", "--format", "json", message],
            env=self.env,
            cwd=workdir,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return OpencodeResult.parse(proc.stdout, proc.stderr, proc.returncode, workdir)


@dataclass
class OpencodeResult:
    events: list[dict]
    stdout: str
    stderr: str
    returncode: int
    workdir: Path

    @classmethod
    def parse(cls, stdout: str, stderr: str, rc: int, workdir: Path) -> OpencodeResult:
        events = []
        for line in stdout.splitlines():
            line = line.strip()
            if not line.startswith("{"):
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return cls(events=events, stdout=stdout, stderr=stderr, returncode=rc, workdir=workdir)

    @property
    def text(self) -> str:
        """Concatenated assistant text output across all events."""
        chunks = []
        for ev in self.events:
            part = ev.get("part", {})
            if ev.get("type") == "text" and "text" in part:
                chunks.append(part["text"])
        return "\n".join(chunks)


def _build_fake_home(tmp_path: Path) -> FakeHome:
    home = tmp_path / "home"
    home.mkdir(parents=True, exist_ok=True)
    env = {
        **os.environ,
        "HOME": str(home),
        "XDG_CONFIG_HOME": str(home / ".config"),
        "XDG_DATA_HOME": str(home / ".local" / "share"),
        "XDG_CACHE_HOME": str(home / ".cache"),
        "XDG_STATE_HOME": str(home / ".local" / "state"),
    }

    npm_prefix = home / ".npm"
    npm_prefix.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["npm", "install", f"opencode-ai@{OPENCODE_VERSION}", "--prefix", str(npm_prefix)],
        check=True,
        env=env,
        capture_output=True,
        text=True,
        timeout=300,
    )
    # The npm package pulls a per-platform binary; locate the real ELF, not the
    # .exe symlink shim.
    candidates = sorted(npm_prefix.glob("node_modules/opencode-*/bin/opencode"))
    binaries = [c for c in candidates if c.is_file() and "baseline" not in c.parent.parent.name]
    opencode_bin = binaries[0] if binaries else candidates[0]

    return FakeHome(home=home, opencode_bin=opencode_bin, env=env)


@pytest.fixture
def kb_absent_home(tmp_path: Path) -> FakeHome:
    """Fake home with ONLY the fkb skills — kb is deliberately not installed."""
    fake = _build_fake_home(tmp_path)
    fake.install_fkb()
    return fake


@pytest.fixture
def kb_present_home(tmp_path: Path) -> FakeHome:
    """Fake home with fkb skills AND the real kb skills installed (happy path)."""
    fake = _build_fake_home(tmp_path)
    fake.install_kb()
    fake.install_fkb()
    return fake
