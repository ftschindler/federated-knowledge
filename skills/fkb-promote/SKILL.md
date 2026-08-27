---
name: fkb-promote
description: >-
  Move a concept from a more-private bundle to a more-open one in a federated OKF workspace. Use when
  knowledge captured privately should now be shared more widely (e.g. private → team, or team →
  public). This is irreversible disclosure — git history keeps the target forever — so it is always
  human-gated. Delegates the re-write of the concept into the target bundle to kb-ingest.
disable-model-invocation: true
version: 0.1.0
tags: [knowledge, okf, federation, fkb, promote, disclosure]
---

# fkb-promote — human-gated disclosure move

Net-new in the federation layer (no `kb-promote` upstream). Promotion is **one-directional and
irreversible**: once a concept lands in a more-open bundle and is committed, its git history keeps it
forever — demotion cannot un-leak it. This is exactly why ingest fails closed to the sealed bundle,
and why promotion is a deliberate, gated act.

## 1. Preflight (mandatory)

```bash
node <fkb-dir>/fkb/scripts/manifest.mjs check-kb kb-ingest
```

Exit 4 → STOP; user runs `npx skills add stjbrown/agent-knowledge`.

Resolve source and target policy:

```bash
node <fkb-dir>/fkb/scripts/manifest.mjs resolve <source-bundle>
node <fkb-dir>/fkb/scripts/manifest.mjs resolve <target-bundle>
```

## 2. Gate — require explicit human sign-off

Promotion ALWAYS requires the user to confirm, because it is irreversible disclosure. Before doing
anything, state plainly and wait for an explicit yes:

> "Promoting `<source>:<concept path>` → `<target>`. `<target>` is
> [published at `<url>` | referenceable by `<who>`]. This is irreversible — git history in `<target>`
> will keep this content permanently. Confirm promotion?"

Also verify the target is `writable: true`; a read-only upstream can never be a promotion target.

## 3. Confidentiality review of the content itself

Before the write, review the concept prose for anything that must NOT reach the target's audience:
client/employer names, internal hostnames, codenames, secrets. `manifest.mjs` enforces the *link*
rule mechanically, but the semantic "is this prose safe to disclose" judgment is human. If anything
is borderline, redact it in the promoted copy or abort and report.

## 4. Delegate the re-write to kb-ingest

`cd` into `target.path` and invoke **kb-ingest** to author the concept into the target bundle
(concept file + that bundle's `index.md` / `log.md`). Re-resolve any cross-links for the new home:
each must satisfy `can-reference <target> <B>`; drop or re-point links the target is not allowed to
make.

## 5. Decide the source copy

Ask the user whether to:

- **keep** the source copy (knowledge now exists in both tiers), or
- **remove** it from the source bundle via kb (deduplicate).

Do not silently delete source content.

## 6. Report

State: promoted concept, source → target, whether content was redacted, how cross-links were
re-resolved, and the fate of the source copy.

## Must not

- Never promote without explicit human confirmation.
- Never promote into a `writable:false` bundle.
- Never carry a cross-link into the target that `can-reference` denies.
- Never author the promoted concept directly — always via kb-ingest.
