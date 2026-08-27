"""Build an isolated fake HOME with opencode + the fkb/kb skills installed.

Shared by the pytest fixtures (tests/conftest.py) and the convenience script
(.scripts/fake-home.py) so there is exactly one definition of "how a fake home is
built". Nothing here touches the developer's real machine: HOME and all XDG_* are
redirected into the given root directory.
"""

from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

# Pinned so the e2e behaviour is reproducible; bump deliberately like our other
# frozen tool versions.
OPENCODE_VERSION = "1.18.25"

# The upstream kb skills the fkb layer delegates to.
KB_REPO = "stjbrown/agent-knowledge"

REPO_ROOT = Path(__file__).resolve().parent.parent
FKB_SKILLS_DIR = REPO_ROOT / "skills"


def have(cmd: str) -> bool:
    return shutil.which(cmd) is not None


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
        for raw in stdout.splitlines():
            line = raw.strip()
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


@dataclass
class FakeHome:
    """An isolated opencode environment rooted at a temp HOME."""

    home: Path
    opencode_bin: Path
    env: dict[str, str] = field(default_factory=dict)

    @property
    def agents_skills(self) -> Path:
        return self.home / ".agents" / "skills"

    @property
    def work(self) -> Path:
        return self.home / "work"

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
        workdir = cwd or self.work
        workdir.mkdir(parents=True, exist_ok=True)
        proc = subprocess.run(
            [str(self.opencode_bin), "run", "--format", "json", message],
            env=self.env,
            cwd=workdir,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        return OpencodeResult.parse(proc.stdout, proc.stderr, proc.returncode, workdir)

    @property
    def enter_command(self) -> str:
        """A copy-pasteable shell command that drops you into this fake home.

        The redirected env vars are what make opencode see the fake home's skills
        and config instead of the real ones.
        """
        env_pairs = " ".join(
            f"{k}={shlex.quote(self.env[k])}"
            for k in (
                "HOME",
                "XDG_CONFIG_HOME",
                "XDG_DATA_HOME",
                "XDG_CACHE_HOME",
                "XDG_STATE_HOME",
            )
            if k in self.env
        )
        oc = shlex.quote(str(self.opencode_bin))
        return f"cd {shlex.quote(str(self.work))} && env {env_pairs} PATH={shlex.quote(self.env.get('PATH', ''))} bash\n# opencode: {oc}"

    def enter_hint(self, *, reason: str) -> str:
        """A multi-line, human-friendly block explaining how to inspect this home."""
        return (
            f"\n──────────────────────────────────────────────────────────────\n"
            f"{reason}\n"
            f"Fake home preserved at: {self.home}\n"
            f"Enter it for inspection with:\n\n"
            f"    {self.enter_command}\n\n"
            f"Inside, `opencode` sees the skills under {self.agents_skills}\n"
            f"or run the convenience script:  make fakehome\n"
            f"──────────────────────────────────────────────────────────────\n"
        )


def build_fake_home(root: Path, *, with_kb: bool) -> FakeHome:
    """Build a fake home under `root`: install opencode, fkb skills, optionally kb.

    `root` must be a directory the caller owns; everything lives under `root/home`.
    """
    home = root / "home"
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
    # .exe symlink shim, and prefer the non-baseline build.
    candidates = sorted(npm_prefix.glob("node_modules/opencode-*/bin/opencode"))
    binaries = [c for c in candidates if c.is_file() and "baseline" not in c.parent.parent.name]
    opencode_bin = binaries[0] if binaries else candidates[0]

    fake = FakeHome(home=home, opencode_bin=opencode_bin, env=env)
    if with_kb:
        fake.install_kb()
    fake.install_fkb()
    fake.work.mkdir(parents=True, exist_ok=True)
    return fake
