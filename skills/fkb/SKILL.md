---
name: fkb
description: >-
  Federated OKF knowledge across multiple privacy-tiered bundles. Use when knowledge is split
  across more than one OKF bundle (e.g. public, team, private, or a read-only upstream) bound by a
  workspace.okf.yaml manifest, and you want to ingest, query, lint, promote, or scaffold across them
  while respecting who-may-reference-whom. Routes to the fkb-* skills; wraps and delegates all bundle
  mutation to the kb-* skills from stjbrown/agent-knowledge.
version: 0.1.0
tags: [knowledge, okf, federation, fkb, hub]
---

# fkb — federated OKF knowledge bundles

A thin **federation layer** over the single-bundle `kb-*` skills. `kb-*` operates on one bundle and
is manifest-oblivious; `fkb-*` reads the **workspace manifest**, decides *which bundle and whether
allowed*, then **delegates the actual write to `kb-*`**. This split is the whole design: every `fkb`
responsibility needs the manifest; every `kb` responsibility is single-bundle and does not.

## Prerequisites (check before anything)

fkb delegates in prose to the `kb-*` skills — there is no code import, so a missing kb skill fails
silently unless you check. **Every fkb skill's FIRST act is a preflight:**

```bash
node <fkb-skills-dir>/fkb/scripts/manifest.mjs check-kb
```

- exit 0 → all required kb skills (`kb`, `kb-init`, `kb-ingest`, `kb-query`, `kb-lint`) are installed.
- exit 4 → STOP. Tell the user to run `npx skills add stjbrown/agent-knowledge`. **Do NOT hand-roll
  the operation** — bypassing kb also bypasses OKF conformance.

You also need a `workspace.okf.yaml` at the workspace root (copy `workspace.okf.yaml.example`).
`manifest.mjs` searches upward for it.

## The manifest is the single source of truth

`workspace.okf.yaml` assigns each bundle four fields (`path`, `referenceable_by`, `writable`,
`publish`); both security axes fail closed (sealed + read-only). Never parse it by hand — always go
through the deterministic helper:

```bash
node .../fkb/scripts/manifest.mjs list                      # resolved bundles
node .../fkb/scripts/manifest.mjs resolve <bundle>          # one bundle as JSON
node .../fkb/scripts/manifest.mjs can-reference <from> <to> # exit 0 allow / 1 deny
node .../fkb/scripts/manifest.mjs validate                  # manifest well-formed?
```

## The reference rule (leak control)

> A concept in bundle **A** may reference a concept in bundle **B**
> **iff** A === B **or** A ∈ B.`referenceable_by`.

`referenceable_by` is **inbound-only** — it controls who may point *at* a bundle, which is exactly
the disclosure axis. `"*"` = anyone (public foundation); `[]` = no one (sealed private). It is a
plain allow-list: no ranks, no ordering, so mutual peers (`peer ↔ team`) list each other. One
`can-reference` call enforces it.

## Route to the right skill

| You want to… | Use | What it adds over kb |
|  -- -  |  - --  | --- |
| Scaffold a new bundle + register it | **fkb-init** | runs `kb-init`, then adds the manifest line |
| Capture/ingest a source into the right tier | **fkb-ingest** | classify → fail-closed → disclosure gate → delegate to `kb-ingest` |
| Answer a question across all bundles | **fkb-query** | fan `kb-query` across bundles (read-all), merge, cite bundle-qualified |
| Health-check conformance + cross-bundle leaks | **fkb-lint** | per-bundle `kb-lint` **plus** the `referenceable_by` + dangling-ref checks kb cannot do |
| Move a concept to a more-open tier | **fkb-promote** | net-new; human-gated because disclosure is irreversible |

## Delegation discipline (do not violate)

`fkb` decides **which bundle and whether allowed**; it must **never** edit a concept body, `index.md`,
or `log.md` directly — always via `kb`. If you edit bundle content yourself, the layering rots and
you lose OKF conformance, the trust model, and free upstream `kb` improvements.

## Read-all, write-one

Reading across bundles is unrestricted (fan-out queries, cross-references for context). **Writing** is
gated to one target bundle at a time, and that target must be `writable`. Placing content into a
**more-open** bundle than the fail-closed default is irreversible disclosure and needs human sign-off
(see fkb-ingest, fkb-promote).

## Not enforced here

The manifest + these skills provide **convenience and correctness**, not the security boundary. Direct
misuse of `kb-ingest` bypasses fkb entirely. The real leak guard is each publishing bundle's own
**pre-commit hook + secret scanner + CI publish-gate**, which run on the commit regardless of which
skill authored it. Those live in each bundle's repo, not here.
