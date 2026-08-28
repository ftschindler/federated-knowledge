---
name: fkb-init
description: >-
  Scaffold a new OKF bundle and register it in the federated workspace. Use when adding a new
  privacy tier or bundle (e.g. a new team, client, or public bundle) to a workspace.okf.yaml
  federation. Delegates the actual scaffold to kb-init, then adds the bundle's line to the manifest
  with fail-closed defaults.
disable-model-invocation: true
version: 0.1.0
tags: [knowledge, okf, federation, fkb, init, scaffold]
---

# fkb-init — scaffold + register a bundle

Wraps [kb-init](../fkb/SKILL.md#route-to-the-right-skill): `kb-init` does the conformant scaffold;
`fkb-init` adds only the **manifest registration**.

## 1. Preflight (mandatory)

```bash
node <fkb-dir>/fkb/scripts/manifest.mjs check-kb kb-init
```

Exit 4 → STOP, tell the user `npx skills add stjbrown/agent-knowledge`. Do not scaffold by hand.

Also confirm a `workspace.okf.yaml` exists at the workspace root (else copy
`workspace.okf.yaml.example` first — the workspace must exist before you register into it).

## 2. Gather the bundle's federation policy

Ask the user (do not guess — these are security-relevant):

- **name** — the bundle key (e.g. `team`, `client_acme`, `public`).
- **path** — local checkout, usually `./<name>/docs`.
- **referenceable_by** — who may point AT it. Default `[]` (sealed). `"*"` only for a genuinely
  public foundation. For mutual peers, remember to also add this bundle to the peer's list.
- **writable** — default `false`; set `true` only if agents should author here.
- **publish** — default `null`; a URL base only if this bundle is published.

## 3. Delegate the scaffold to kb-init

Run **kb-init** targeting the chosen `path` (kb-init scaffolds `index.md`, `log.md`, and the schema
layer). Let kb-init own all bundle content — fkb never writes concept files.

## 4. Register in the manifest

Append one flow-style line under `bundles:` in `workspace.okf.yaml`:

```yaml
  <name>: { path: <path>, referenceable_by: <[]|"*"|[peer,...]>, writable: <bool>, publish: <url|null> }
```

Omit an axis to take its fail-closed default (`writable:false`, `publish:null`, `referenceable_by:[]`).
If you created a mutual peer, edit the peer's `referenceable_by` to include this bundle too.

## 5. Verify

```bash
node <fkb-dir>/fkb/scripts/manifest.mjs validate
node <fkb-dir>/fkb/scripts/manifest.mjs list        # confirm the new bundle resolves as intended
```

Report the registered line and the resolved policy back to the user.

## Must not

- Do not scaffold bundle content yourself — always via kb-init.
- Do not open `referenceable_by`/`writable`/`publish` wider than the user asked; when unspecified,
  take the sealed default.
