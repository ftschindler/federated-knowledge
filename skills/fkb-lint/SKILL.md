---
name: fkb-lint
description: >-
  Health-check a federated OKF workspace for conformance, drift, and cross-bundle leaks. Use to audit
  a workspace.okf.yaml federation — run each bundle's kb-lint for OKF conformance, then run the checks
  kb cannot do alone: the referenceable_by leak rule on every cross-bundle link, and dangling
  references into read-only upstreams. A pure superset of kb-lint.
disable-model-invocation: true
version: 0.1.0
tags: [knowledge, okf, federation, fkb, lint, conformance]
---

# fkb-lint — per-bundle conformance + cross-bundle leak audit

Wraps [kb-lint](../fkb/SKILL.md#route-to-the-right-skill) and adds the one class of check a
single-bundle linter structurally cannot do: **cross-bundle** rules.

## 1. Preflight (mandatory)

```bash
uv run ~/.config/federated-knowledge/manifest.py check-deps kb-lint
uv run ~/.config/federated-knowledge/manifest.py validate      # manifest itself must be well-formed first
```

check-deps exit 4 → STOP; the message names what is missing — install `uv`, or run
`npx skills add stjbrown/agent-knowledge` for the kb skills.
validate exit 2 → the manifest is malformed; fix it before linting bundles.

## 2. Per-bundle conformance (delegate to kb-lint)

For **each** bundle in the manifest, run kb-lint's deterministic conformance script against its
`resolved_path`:

```bash
node <kb-lint-dir>/scripts/conformance.mjs <bundle.resolved_path>
```

This catches within-bundle drift: frontmatter, reserved-file shape, broken *intra*-bundle links.
Collect each bundle's report.

## 3. Cross-bundle checks (fkb-only — kb cannot see across bundles)

For every markdown link that crosses from bundle A into bundle B:

1. **Leak rule.** Verify the reference is permitted:

   ```bash
   uv run ~/.config/federated-knowledge/manifest.py can-reference A B
   ```

   Exit 1 (DENY) → a **leak violation**: A points at B but B does not list A in `referenceable_by`.
   Report it as an error with the offending concept + link.

2. **Dangling upstream refs.** A cross-link into a `writable:false` upstream cannot be fixed by us
   (we don't own the target). If the target concept is absent, flag it and confirm the reference is
   also recorded as an OKF `sources[]` provenance entry (with the upstream's `publish` URL) so it
   survives a broken live link.

## 4. Report

One consolidated report:

- per-bundle conformance status (from kb-lint),
- cross-bundle leak violations (DENY results) — these are the security-critical findings,
- dangling / unprovenanced upstream references.

Surface leak violations first and most prominently.

## Must not

- Do not "fix" a leak by widening `referenceable_by` yourself — that is a disclosure decision for the
  user. Report it; let them decide.
- Do not edit bundle content to resolve conformance issues directly — delegate fixes to kb-lint's fix
  mode or kb-ingest.
