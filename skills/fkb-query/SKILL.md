---
name: fkb-query
description: >-
  Answer a question across all bundles of a federated OKF workspace. Use when the user asks what
  they or the project know about something and the knowledge may live in any bundle of a
  workspace.okf.yaml federation (public, team, private, or a read-only upstream). Fans kb-query
  across every bundle (reading is unrestricted), merges and ranks the hits, and cites each by a
  bundle-qualified path or URL.
version: 0.1.0
tags: [knowledge, okf, federation, fkb, query, retrieval]
---

# fkb-query — fan out, merge, cite

Wraps [kb-query](../fkb/SKILL.md#route-to-the-right-skill). **Reading is unrestricted** across the
federation — the `referenceable_by` leak rule governs *authoring* cross-links, not reading. So query
fans out to every bundle; only writing is gated (see fkb-ingest).

## 1. Preflight (mandatory)

```bash
uv run ~/.config/federated-knowledge/manifest.py check-deps kb-query
```

Exit 4 → STOP; user runs `npx skills add stjbrown/agent-knowledge`.

Load the bundle set:

```bash
uv run ~/.config/federated-knowledge/manifest.py list
```

## 2. Fan kb-query across bundles

For **each** bundle in the manifest (writable or not — reading is allowed everywhere), `cd` into its
`path` and run **kb-query** for the user's question. Collect each bundle's answer with its source
concept paths.

## 3. Merge and rank

Combine the per-bundle answers into one response:

- De-duplicate overlapping facts; prefer the most-specific / most-recently-updated source.
- Note genuine conflicts between bundles rather than silently picking one.
- If different tiers disagree, surface both and label by bundle.

## 4. Cite bundle-qualified

Every citation must name **which bundle** it came from, so tier is always visible:

- Published bundle → its `publish` URL + concept path (no `docs/` segment — MkDocs strips it).
- Unpublished bundle → `bundle:concept/path.md`, e.g. `private:decisions/pricing.md`.

Use `manifest.py resolve <bundle>` to get the `publish` base when formatting a URL citation.

## Must not

- Do not write anything. fkb-query is read-only unless the user explicitly asks to file the answer
  back — in which case hand off to **fkb-ingest** (which re-applies classification + gates), never
  write directly.
- Do not hide which bundle a fact came from — bundle-qualified citation is mandatory.
