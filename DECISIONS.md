# DECISIONS — overnight implementation retro

A record of what got built, the KISS calls I made where the design left a gap,
and open questions for you. Written for a morning read-through. Nothing here
blocks — everything is implemented, tested, and committed; this is where I ask
for a sanity check on the judgement calls.

## What shipped (7 commits, all green)

The full foundation + bundle layer from the settled design:

1. **`manifest.py`** — the Python core (replaces `manifest.mjs`). PEP 723 inline
   deps (`ruamel.yaml`), run via `uv`. Fixed XDG workspace location
   (`$FKB_WORKSPACE` > `~/.config/federated-knowledge/workspace.okf.yaml`, no
   upward-search). `workspace_root` + path resolution (`~`-expand, absolute
   as-is, relative under root, relative-without-root is an error). Preflight
   broadened to `uv` + kb skills (`check-deps`). 5 read-only subcommands.
2. **The writer** — `add_bundle()`: round-trip append preserving comments +
   flow-style, duplicate = hard error, append-last so hand-sorting survives.
3. **`install-glue`** — creates the config dir + starter manifest (proposed
   `workspace_root`), copies the helper scripts to the config dir,
   `--print-agents-block` emits the marker-wrapped agent block.
4. **Three bundle commands** — `clone-bundle` (git clone + OKF-root discovery),
   `add-bundle` (register in place), `create-bundle` (scaffold + register),
   over a shared `_fkb_bundle.py`.
5. **Skill migration** — `fkb-init` rewritten as the interactive orchestrator;
   all 6 SKILL.md invocations point at `uv run ~/.config/.../manifest.py`;
   `manifest.mjs` + its test deleted; README migrated.

**Tests:** 56 pytest cases (unit + subprocess CLI + install-glue + bundle
commands driven as a real user drives them). Full `prek --all-files` green.
**Manual e2e verified:** install → create public/peer/team/private → clone an
upstream (docs/ auto-discovered) → add an existing checkout → leak rule correct
across all six bundles.

## KISS fill-ins (gaps the design left; I picked the simplest correct option)

These are the decisions you did NOT explicitly make — flag any you'd do differently:

- **`check-kb` renamed to `check-deps`** — it now verifies `uv` too, so the old
  name was wrong. Exit 4 preserved.
- **Empty `bundles:` is now valid** — a freshly-installed workspace has zero
  bundles. I relaxed the core so an empty (or `None`) `bundles:` is a valid
  empty federation, not an error; a *missing* `bundles:` key stays an error. The
  original "empty is error" test was inverted to lock the new contract.
- **`create-bundle` scaffolds a minimal bundle directly** (index.md + log.md),
  NOT via `kb-init`. Reason: `kb-init` is a skill (prose for an agent), not a
  callable binary — a plain script cannot invoke it. The script writes a minimal
  OKF stub; the `fkb-init` skill prose is where an agent would drive real
  `kb-init` for full conformance. **This is the biggest divergence from the
  README** (which still says "scaffolds a conformant OKF bundle (via kb-init)").
  See open questions.
- **Bundle commands are flag-driven, ask-if-absent, TTY-gated** — they prompt
  only when stdin is a TTY; non-interactive (tests, or the skill passing flags)
  takes the fail-closed default. This is how the `fkb-init` skill drives them.
- **`_fkb_bundle.py` shared helper** — the three commands share manifest-location,
  prompting, policy, and OKF-root-discovery logic rather than duplicating it.
  `install-glue` copies it alongside the commands.
- **OKF-root discovery** = shallowest `index.md`; on a tie at the same depth,
  ask rather than guess (as designed).
- **YAML width raised to 4096** so each flow-style bundle entry stays on one
  line (ruamel wraps at ~80 by default, which was ugly). Cosmetic: ruamel also
  drops the inner `{ x }` spaces to `{x}` — valid YAML, not worth fighting.
- **Dropped the `test_node_scripts` Makefile target** — no `.mjs` tests remain.

## Bug caught by end-to-end QA (worth noting for the retro)

The unit tests passed while the actual user flow crashed: the bundle commands
`import _fkb_bundle`, but `install-glue` did not copy that helper into the
config dir — so every command failed with `ModuleNotFoundError` when run from
where a real user runs them. The tests masked it by running the commands from
the repo dir (helper beside them). Fix: copy the helper, AND harden the tests to
drive the *installed* copies. Lesson reaffirmed: real usage is the gate, not a
green unit suite.

## Open questions for you

1. **`create-bundle` vs `kb-init` (most important).** The script scaffolds a
   minimal stub, not a kb-init-conformant bundle, because a script can't call a
   skill. Options: (a) leave as-is — the stub is enough to register, and the
   `fkb-init` skill drives real kb-init when an agent runs it; (b) have
   `create-bundle` shell out to some kb-init CLI if one exists (I did not find
   one); (c) drop `create-bundle`'s scaffolding entirely and make bundle
   creation skill-only. I chose (a). The README's "via kb-init" wording should
   change to match whichever you pick.

2. **The launcher (`~/.config/.../manifest.py` invoked via `uv run`).** I did
   NOT build a separate PATH shim or symlink — the "launcher" is just the copied
   script at the fixed path, invoked `uv run ~/.config/federated-knowledge/…`.
   That is option-2-lite: one stable path, no PATH pollution. If you wanted an
   actual `fkb` command on PATH, that's not done.

3. **`--from .` dev-loop flag** is implemented in install-glue (copies scripts
   from a repo checkout) but I did NOT wire the symlink-your-checkout dev flow
   from the README's "Work on the skills" section into anything automated — it
   stays the documented manual `ln -s` loop.

4. **AGENTS.md block content** — I wrote the verbatim block (query-first,
   ingest-to-capture, reference rule, promote-is-gated, preflight, graceful
   skip). Give it a read in `install-glue`; it's the prose that lands in every
   user's agent instructions, so your voice matters most there.

5. **`fkb-lint` / `fkb-promote` / `fkb-ingest` / `fkb-query` SKILL.md** were only
   migrated (invocation paths), NOT re-examined against the new Python core's
   exact output formats. They reference `manifest.py resolve`/`can-reference`/
   `list` which all work, but a close read for prose drift is worth doing.

## What I deliberately did NOT touch

- Your in-progress `README.md` ASCII-alignment edit — committed alongside the
  README migration since it was the same file, but I made no other changes to
  your wording.
- The e2e `skills` test layer (`test_skills.py`) — updated its two `manifest.py`
  references but did NOT run it (needs network + opencode install; slow).
