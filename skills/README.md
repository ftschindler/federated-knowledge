# The fkb skills

A thin **federation layer** over the single-bundle `kb-*` skills from
[stjbrown/agent-knowledge](https://github.com/stjbrown/agent-knowledge). Each `fkb-*` skill reads the
workspace manifest, decides *which bundle and whether allowed*, then delegates the actual bundle
mutation to `kb-*`. See the [top-level README](../README.md) for how the pieces fit together.

| Skill | What it does |
| --- | --- |
| `fkb` | Hub. Documents the manifest, the reference rule, and delegation discipline; routes to the others. |
| `fkb-init` | Sets up the federation interactively: builds the workspace if absent, then walks you through adding bundles (clone, add-existing, or create). |
| `fkb-ingest` | Classifies a source to the right tier (fail-closed), gates disclosure, delegates the write to `kb-ingest`. |
| `fkb-query` | Fans `kb-query` across every bundle, merges, and cites bundle-qualified. |
| `fkb-lint` | Runs per-bundle `kb-lint` plus the cross-bundle `referenceable_by` and dangling-reference checks. |
| `fkb-promote` | Moves a concept to a more-open tier. Human-gated, because disclosure is irreversible. |

Every `fkb-*` skill's first act is a preflight (`manifest.mjs check-kb`): if the `kb-*` skills are
missing, it stops and tells you to run `npx skills add stjbrown/agent-knowledge` rather than
hand-rolling the operation.
