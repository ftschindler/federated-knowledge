# TODOs

## For Felix

- [ ] **Prose pass on the 6 `fkb-*` SKILL.md files** — voice/clarity review
      _(depends on: my factual pass below landing first)_
  - fkb-query: do not install, simply offer
- [ ] **Read/check the verbatim AGENTS.md block** in `install-glue` — it lands in
      every user's agent instructions, so the voice should be yours
      _(DECISIONS.md open question 4)_
  - hardcoded workspace yml in the block?
- [ ] **Decide the launcher scope** — currently option-2-lite (copied script at
      `~/.config/.../manifest.py`, invoked via `uv run`); no PATH shim / `fkb`
      command. Confirm that's enough, or ask for a real PATH binary
      _(DECISIONS.md open question 2)_

## For me (agent)

### Corrections uncovered this session

- [x] **Serve the OKF v0.2 reference with the skills** — add shared references under
      `skills/fkb/references/` so agents do not rely on memory or web access for
      conformance decisions.
  - [x] add `okf-v0.2.md` (normative parts we rely on)
  - [x] add `okf-minimal-bundle.md` (the exact minimal bundle shape `create-bundle`
        writes)
- [x] **Make `create-bundle` write a minimal conformant OKF bundle** — write a
      bundle-root `index.md` with `okf_version: "0.2"` and a reserved `log.md`,
      update tests, and keep the README line 290 wording truthful.
- [x] **Factual pass on the 4 path-migrated SKILL.md** (`fkb-ingest`,
      `fkb-query`, `fkb-lint`, `fkb-promote`) — verify every invocation, exit
      code, and output-format claim matches what `manifest.py` and the commands
      actually do _(unblocks Felix's prose pass)_
- [ ] **Drop `$FKB_WORKSPACE`** — it overlaps `XDG_CONFIG_HOME` (whole-home
      relocation) and `--manifest` (explicit targeting). Remove the branch in
      `manifest_location`, update docstring + not-found error, migrate the test
      usages to `--manifest` or a tmp `XDG_CONFIG_HOME`. Precedence becomes
      `--manifest` > XDG path.
- [ ] **Make skill invocations honor `XDG_CONFIG_HOME`** — `install-glue` copies
      scripts to `$XDG_CONFIG_HOME/federated-knowledge`, but the skills hardcode
      `~/.config/...`, which breaks for users with a custom `XDG_CONFIG_HOME`.
      Switch to `${XDG_CONFIG_HOME:-$HOME/.config}/federated-knowledge/...` across
      the 6 SKILL.md files, the AGENTS.md block in `install-glue`, and the README.

### Test coverage (current `test_skills.py` is a 3-test smoke layer only)

- [ ] **Wire `stjbrown/agent-knowledge` as the test fixture** — public repo with
      a known entry (`knowledge/references/karpathy_llm_wiki.md`) to anchor
      content assertions. Doubles as the feature in the item below.
  - [ ] **Deterministic onboarding e2e (scripts only, no LLM — fast, CI-safe)**
        — drive install-glue → clone-bundle agent-knowledge → query, assert the
        known karpathy entry surfaces. Verifies the README's onboarding mechanics.
        _(depends on: the fixture above)_
    - [ ] cover the **remote clone** path (`clone-bundle` of agent-knowledge)
    - [ ] cover the **existing local checkout** path (`add-bundle` in place)
  - [ ] **Agent-driven e2e in the slow `skills` layer (LLM + network)** — verifies
        the SKILL.md prose actually leads the agent correctly
        _(depends on: the fixture, and my factual SKILL.md pass)_
    - [ ] `fkb-init` full interactive onboarding
    - [ ] `fkb-ingest` capture into the right tier
    - [ ] `fkb-query` fan-out + bundle-qualified citation
    - [ ] `fkb-lint` cross-bundle leak check
    - [ ] `fkb-promote` human-gated disclosure move
  - [ ] **AGENTS.md block placement e2e** — block prints clean via
        `--print-agents-block`; agent can place it into its instructions

### Features (pre-existing)

- [ ] **Offer to add `stjbrown/agent-knowledge` as a public read-only bundle** —
      same artifact as the test fixture above; ship both together
- [ ] add an update mechanism so invoking the skills discovers if there is an
      update to the skills
- [ ] add pull/push convenience, or at least update detection for remote bundles
