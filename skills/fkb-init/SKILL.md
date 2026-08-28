---
name: fkb-init
description: >-
  Set up a federated OKF knowledge workspace interactively. Use for first-time setup or to add
  bundles to an existing workspace.okf.yaml federation. Builds the workspace if absent (via
  install-glue), then walks the user through adding bundles — clone a remote, register an existing
  local checkout, or create a new one — driving the flag-driven helper commands and gathering the
  federation policy for each.
disable-model-invocation: true
version: 0.1.0
tags: [knowledge, okf, federation, fkb, init, setup]
---

# fkb-init — interactive federation setup

The front door. Orchestrates the deterministic helper commands (`install-glue`, `clone-bundle`,
`add-bundle`, `create-bundle`) into a guided setup. `fkb-init` does the **asking**; the helpers do
the **doing** — this skill never writes the manifest or scaffolds a bundle itself.

## 1. Preflight (mandatory)

```bash
uv run ~/.config/federated-knowledge/manifest.py check-deps kb-init
```

Exit 4 → STOP. The message names what is missing — install `uv`, or run
`npx skills add stjbrown/agent-knowledge` for the kb skills. Do not scaffold by hand.

> If `~/.config/federated-knowledge/manifest.py` does not exist yet, the workspace has never been
> initialised — step 2 handles this by running install-glue from the installed skill.

## 2. Build the workspace if absent

Check whether the workspace exists:

```bash
uv run ~/.config/federated-knowledge/manifest.py validate
```

- **Malformed / missing** → build it. Ask the user for a `workspace_root` (default
  `~/.agents/knowledge`), then run install-glue from the installed skill:

  ```bash
  uv run <installed-fkb-skill-dir>/scripts/install-glue --root <workspace_root>
  ```

  Then hand off the agent-instructions block (it is not written automatically):

  ```bash
  uv run ~/.config/federated-knowledge/install-glue --print-agents-block
  ```

  Add its output to the user's agent instruction file (`AGENTS.md` / `CLAUDE.md`), or tell the user
  to paste it. The `<!-- BEGIN fkb -->` / `<!-- END fkb -->` markers make a re-run replace it in place.

- **Valid** → the workspace exists; go straight to adding bundles.

## 3. Add bundles (loop until the user is done)

For each bundle the user wants, ask which of the three kinds it is, then drive the matching command.
Gather the federation policy first (`referenceable_by`, `writable`, `publish`) and pass it as flags so
the command runs non-interactively — you are the one asking, not the script.

- **Remote git repo** → clone and register:

  ```bash
  uv run ~/.config/federated-knowledge/clone-bundle <url> <name> <referenceable_by> [--writable] [--publish <url>]
  ```

  It clones under `workspace_root` and discovers the OKF root (the dir of the top-most `index.md`).
  If discovery is ambiguous it will ask; confirm the subdir with the user. Cloned bundles are a
  **source** — default `writable:false` unless the user will author into it.

- **Existing local checkout** → register in place, never moved:

  ```bash
  uv run ~/.config/federated-knowledge/add-bundle <name> <absolute-path> <referenceable_by> [--writable] [--publish <url>]
  ```

- **New bundle to author into** → scaffold and register:

  ```bash
  uv run ~/.config/federated-knowledge/create-bundle <name> <referenceable_by> [--publish <url>]
  ```

  Defaults `writable:true` (you author into it) and sealed `referenceable_by:[]`.

For **mutual peers**, remember to add each to the other's `referenceable_by`.

## 4. Confirm

```bash
uv run ~/.config/federated-knowledge/manifest.py list
```

Show the resolved bundles and their policy, so the user sees what entered the federation.

## Must not

- Do not write the manifest or scaffold bundle content yourself — always via the helper commands.
- Do not open `referenceable_by`/`writable`/`publish` wider than the user asked; when unspecified,
  the commands take the fail-closed default.
- Do not place content into any bundle here — fkb-init only registers bundles; capture is fkb-ingest.
