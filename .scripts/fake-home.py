#!/usr/bin/env python3
"""Build a fake opencode home with the fkb (and optionally kb) skills, then drop
into a shell inside it — for deliberate hands-on inspection of how opencode
behaves with the skills.

Usage:
  .scripts/fake-home.py            # fkb + kb installed (happy path), enter shell
  .scripts/fake-home.py --no-kb    # only fkb (loud-failure scenario)
  .scripts/fake-home.py --keep     # build, print enter command, but do NOT spawn a shell
  .scripts/fake-home.py --dir DIR  # build under DIR instead of a fresh mktemp

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
from fake_home import build_fake_home, have  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    kb = parser.add_mutually_exclusive_group()
    kb.add_argument("--kb", dest="kb", action="store_true", help="install kb skills (default)")
    kb.add_argument(
        "--no-kb", dest="kb", action="store_false", help="omit kb (loud-failure scenario)"
    )
    parser.set_defaults(kb=True)
    parser.add_argument(
        "--keep", action="store_true", help="don't spawn a shell, just build + print"
    )
    parser.add_argument("--dir", type=Path, help="build under this directory instead of mktemp")
    args = parser.parse_args()

    for tool in ("node", "npm", "npx"):
        if not have(tool):
            print(f"error: '{tool}' is required but not found on PATH", file=sys.stderr)
            return 1

    root = args.dir or Path(tempfile.mkdtemp(prefix="fkb-fakehome-"))
    root.mkdir(parents=True, exist_ok=True)
    print(f"Building fake home under {root} (kb={'yes' if args.kb else 'no'})…", file=sys.stderr)

    fake = build_fake_home(root, with_kb=args.kb)

    print(fake.enter_hint(reason="Fake home ready."), file=sys.stderr)

    if args.keep:
        return 0

    # Spawn an interactive shell with the redirected environment.
    return subprocess.run(["bash"], cwd=fake.work, env=fake.env).returncode


if __name__ == "__main__":
    raise SystemExit(main())
