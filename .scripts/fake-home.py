#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# ///
"""Build a fake opencode home and drop into a shell inside it — for deliberate
hands-on inspection of how opencode behaves with a set of skills.

Usage:
  .scripts/fake-home.py                 # install this repo's skills/, enter shell
  .scripts/fake-home.py --skills DIR    # install skill directories from DIR
  .scripts/fake-home.py --no-skills     # opencode only, nothing installed
  .scripts/fake-home.py --keep          # build, print enter command, but do NOT spawn a shell
  .scripts/fake-home.py --dir DIR       # build under DIR instead of a fresh mktemp

Inside the spawned shell, `opencode` sees only the fake home's skills/config.
Type `exit` to leave; the directory is left on disk so you can re-enter with the
printed command.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

# Import the shared builder from tests/ (single source of truth).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tests"))
from fake_home import REPO_SKILLS_DIR, build_fake_home, have


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--skills", type=Path, help="install skill directories from here")
    source.add_argument("--no-skills", action="store_true", help="install opencode only, no skills")
    parser.add_argument("--keep", action="store_true", help="don't spawn a shell, just build + print")
    parser.add_argument("--dir", type=Path, help="build under this directory instead of mktemp")
    args = parser.parse_args()

    for tool in ("node", "npm", "npx"):
        if not have(tool):
            print(f"error: '{tool}' is required but not found on PATH", file=sys.stderr)
            return 1

    skills_dir = None if args.no_skills else (args.skills or REPO_SKILLS_DIR)
    if skills_dir is not None and not skills_dir.is_dir():
        print(
            f"note: no skills at {skills_dir} — building an opencode-only home.\n"
            "      This repo ships no skills yet; see DESIGN.md.",
            file=sys.stderr,
        )

    root = args.dir or Path(tempfile.mkdtemp(prefix="fkb-fakehome-"))
    root.mkdir(parents=True, exist_ok=True)
    print(f"Building fake home under {root} (skills={skills_dir or 'none'})…", file=sys.stderr)

    fake = build_fake_home(root, skills_dir=skills_dir)

    print(fake.enter_hint(reason="Fake home ready."), file=sys.stderr)

    if args.keep:
        return 0

    # Spawn an interactive shell with the redirected environment.
    return subprocess.run(["bash"], cwd=fake.work, env=fake.env, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
