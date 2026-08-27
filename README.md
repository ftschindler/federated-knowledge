# federated-knowledge

A thin **federation layer** of agent skills that binds any number of independent, privacy-tiered
[OKF](https://github.com/GoogleCloudPlatform/open-knowledge-format) knowledge bundles into one
personal knowledge base — driven by a single `workspace.okf.yaml` manifest.

Each bundle stays its own standalone OKF repo, unaware of the others. All coupling lives in **one
local place** (the manifest). The `fkb-*` skills here wrap and delegate to the single-bundle `kb-*`
skills from [stjbrown/agent-knowledge](https://github.com/stjbrown/agent-knowledge): `fkb` decides
*which bundle and whether allowed*; `kb` does the actual bundle mutation.

## Requires: the kb skills

**This repo depends on [stjbrown/agent-knowledge](https://github.com/stjbrown/agent-knowledge).** The
`fkb-*` skills delegate every bundle mutation to `kb-init`, `kb-ingest`, `kb-query`, and `kb-lint`.
Install both:

```bash
npx skills add stjbrown/agent-knowledge      # the kb-* skills (required)
npx skills add ftschindler/federated-knowledge  # these fkb-* skills
```

If the kb skills are missing, every `fkb` skill's preflight (`manifest.mjs check-kb`) **fails loudly**
with the install command rather than silently hand-rolling — see below.

## Setup

```bash
cp workspace.okf.yaml.example workspace.okf.yaml   # then edit for your bundles
node skills/fkb/scripts/manifest.mjs validate      # confirm it parses
node skills/fkb/scripts/manifest.mjs list          # see resolved policy
```

## The skills

| Skill | Purpose |
|  -- -  |  --- |
| `fkb` | Hub/router. Documents the manifest, the reference rule, and delegation discipline. |
| `fkb-init` | Scaffold a new bundle (via `kb-init`) and register it in the manifest. |
| `fkb-ingest` | Classify a source to the right tier (fail-closed), gate disclosure, delegate the write to `kb-ingest`. |
| `fkb-query` | Fan `kb-query` across all bundles (reading is unrestricted), merge, cite bundle-qualified. |
| `fkb-lint` | Per-bundle `kb-lint` **plus** the cross-bundle `referenceable_by` leak check and dangling-upstream check. |
| `fkb-promote` | Human-gated move of a concept to a more-open bundle (irreversible disclosure). |

## The manifest

`workspace.okf.yaml` is the sole coupling point. Four fields per bundle; **both security axes fail
closed** (an unconfigured bundle is sealed and read-only):

| field | question | default |
|  -- -  |  - --  | --- |
| `path` | where the bundle root is checked out locally | (required) |
| `referenceable_by` | who may point *at* me (the leak rule) | `[]` (no one) |
| `writable` | may an agent author into this bundle here | `false` |
| `publish` | my published URL base, if any | `null` |

### The reference rule (leak control)

> A concept in bundle **A** may reference a concept in bundle **B**
> **iff** A = B **or** A ∈ B.`referenceable_by`.

`referenceable_by` is inbound-only — it controls who may point *at* a bundle, which is exactly the
disclosure axis. `"*"` = anyone (public foundation); `[]` = no one (sealed private). Mutual peers list
each other (`peer ↔ team`). One `manifest.mjs can-reference A B` call enforces it.

## manifest.mjs — the deterministic core

Zero-dependency Node helper every `fkb` skill calls. No `npm install` needed.

```bash
node skills/fkb/scripts/manifest.mjs list                      # resolved bundles
node skills/fkb/scripts/manifest.mjs resolve <bundle>          # one bundle as JSON
node skills/fkb/scripts/manifest.mjs can-reference <from> <to> # exit 0 allow / 1 deny
node skills/fkb/scripts/manifest.mjs check-kb                  # exit 0 all kb present / 4 missing
node skills/fkb/scripts/manifest.mjs validate                  # exit 0 well-formed / 2 malformed
```

Tests: `node skills/fkb/scripts/manifest.test.mjs`.

## What lives elsewhere

These skills provide **convenience and correctness**, not the security boundary. Direct misuse of
`kb-ingest` bypasses `fkb`. The real leak guard is each publishing bundle's own **pre-commit hook +
secret scanner + CI publish-gate**, which run on the commit regardless of which skill authored it —
they belong in each bundle's repo, not here.

## License

[MIT](LICENSE) — matching the MIT-licensed [kb skills](https://github.com/stjbrown/agent-knowledge)
this repo depends on.
