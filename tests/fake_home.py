"""Build an isolated fake HOME with opencode and a set of skills installed.

Shared by the pytest fixtures (tests/conftest.py) and the convenience script
(.scripts/fake-home.py) so there is exactly one definition of "how a fake home is
built". Nothing here touches the developer's real machine: HOME and all XDG_* are
redirected into the given root directory.

The harness knows nothing about which skills it installs: `install_skills` takes a
directory and copies whatever skill directories it finds. That keeps it usable
across a rewrite of the skills themselves, which is exactly what it survived.
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

# One allowance for every agent run. A run is an LLM driving tools, so its duration
# swings with the tool path it picks: tests that take ~60s locally have twice blown
# a 300s cap on a CI runner. A genuinely stuck run is caught by the job timeout.
AGENT_RUN_TIMEOUT = 600

REPO_ROOT = Path(__file__).resolve().parent.parent

# Where this repo's own skills live once there are any. Absent during the design
# stage, which `install_skills` tolerates rather than failing on.
REPO_SKILLS_DIR = REPO_ROOT / "skills"


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


class OpencodeTimeoutError(AssertionError):
    """An `opencode run` that outlived its allowance, carrying its partial transcript."""


def _timeout_report(partial: OpencodeResult, timeout: int) -> str:
    return (
        f"opencode run exceeded {timeout}s and was killed.\n"
        f"--- assistant transcript so far ---\n{partial.text.strip() or '(none)'}\n"
        f"--- stderr ---\n{partial.stderr.strip() or '(empty)'}"
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

    @property
    def work(self) -> Path:
        return self.home / "work"

    def install_skills(self, source: Path) -> list[str]:
        """Copy every skill directory under `source` into ~/.agents/skills.

        A skill is any subdirectory holding a SKILL.md, which is what the Agent
        Skills spec makes discoverable. Returns the names installed; a missing or
        empty `source` installs nothing and is not an error.
        """
        self.agents_skills.mkdir(parents=True, exist_ok=True)
        if not source.is_dir():
            return []
        installed = []
        for skill in sorted(source.iterdir()):
            if not (skill / "SKILL.md").is_file():
                continue
            shutil.copytree(skill, self.agents_skills / skill.name, dirs_exist_ok=True)
            installed.append(skill.name)
        return installed

    def install_from_registry(self, repo: str) -> None:
        """Install a published skill set into ~/.agents/skills via skills.sh."""
        subprocess.run(
            ["npx", "--yes", "skills", "add", repo, "--skill", "*", "-a", "opencode", "-g", "-y", "--copy"],
            check=True,
            env=self.env,
            cwd=self.home,
            capture_output=True,
            text=True,
            timeout=300,
        )

    def run(self, message: str, *, cwd: Path | None = None, timeout: int = AGENT_RUN_TIMEOUT) -> OpencodeResult:
        """Drive `opencode run` non-interactively and capture parsed JSON events."""
        workdir = cwd or self.work
        workdir.mkdir(parents=True, exist_ok=True)
        proc = subprocess.Popen(
            [str(self.opencode_bin), "run", "--format", "json", message],
            env=self.env,
            cwd=workdir,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        try:
            stdout, stderr = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            stdout, stderr = proc.communicate()
            raise OpencodeTimeoutError(
                _timeout_report(OpencodeResult.parse(stdout, stderr, -9, workdir), timeout)
            ) from None
        return OpencodeResult.parse(stdout, stderr, proc.returncode, workdir)

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


def _write_opencode_config(home: Path) -> None:
    """Let the agent reach the fake home outside its working directory.

    `opencode run` is non-interactive, so any permission prompt is auto-rejected.
    The fkb skills live in `~/.agents/skills` and their glue in `~/.config`, both
    outside the workdir, so without this every run dies on an `external_directory`
    prompt before the skill can do — or refuse — anything. A real user grants this
    once interactively; here we grant it up front.
    """
    config_dir = home / ".config" / "opencode"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "opencode.json").write_text(
        json.dumps(
            {
                "$schema": "https://opencode.ai/config.json",
                "permission": {"external_directory": "allow"},
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def build_fake_home(root: Path, *, skills_dir: Path | None = REPO_SKILLS_DIR) -> FakeHome:
    """Build a fake home under `root`: install opencode, then the given skills.

    `root` must be a directory the caller owns; everything lives under `root/home`.
    `skills_dir` defaults to this repo's own skills and may be absent.
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

    _write_opencode_config(home)

    fake = FakeHome(home=home, opencode_bin=opencode_bin, env=env)
    if skills_dir is not None:
        fake.install_skills(skills_dir)
    fake.work.mkdir(parents=True, exist_ok=True)
    return fake
