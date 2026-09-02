# federated-knowledge

This is an implementation of the [LLM wiki](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f)
idea that builds on federation (for [sharing and access control](#trust-model-and-data-leaks))
and the [agent-knowledge](https://github.com/stjbrown/agent-knowledge/) skills
to bind any number of independent, privacy-tiered [OKF](https://github.com/GoogleCloudPlatform/open-knowledge-format)\
knowledge bundles into one agent-first, human-friendly personal knowledge base.

## Getting started

Assume, you want your agent to be able to gain knowledge from, and file knowledge into any combination of:

1. a set of OKF bundles as git repos (read or writable)
2. a set of OKF bundles you already have (perhaps unknowingly) checked out locally
3. a set of OKF bundles you want to create from scratch (to share, or for private notes)

### Prerequisites

With [Node.js](https://nodejs.org) available,
install the [agent-knowledge](https://github.com/stjbrown/agent-knowledge/) skills we depend on
as well as these federated-knowledge (`fkb`) skills using your favourite shell:

```bash
npx skills add stjbrown/agent-knowledge
npx skills add ftschindler/federated-knowledge
```

> This installs the skills and helper scripts to ~/.agents/skills.
> Your agent or harness should discover these by default, you can also ask it directly to install these skills.

### Building the workspace

Managing the federation requires a central workspace that ties all bundles together and defines access.
Ask your agent to invoke the provided `fkb-init` skill, which will interactively walk you through
[building the workspace](#building-a-workspace-manually) and [adding knowledge bundles](#adding-knowledge-bundles).

## The skills

Six `fkb-*` skills wrap and delegate to the single-bundle `kb-*` skills: `fkb` (hub), `fkb-init`
(interactive setup), `fkb-ingest`, `fkb-query`, `fkb-lint`, and `fkb-promote`. See
[skills/README.md](skills/README.md) for what each one does.

## How this works

Five components, and an action that threads through all of them. You ask your agent a question; it
reaches for fkb because its standing instructions say to; fkb reads the manifest to route; the skills
read or write a bundle. Nothing here runs on its own — the agent is the actor, and everything else is
the map it acts on.

```text
        you ──ask──▶ ┌─────────┐
                      │  agent  │
                      └────┬────┘
             reads standing instructions
                          │
                 ┌────────▼──────────┐
                 │ global AGENTS.md  │  "fkb exists here: query to read,
                 │   (fkb block)     │   ingest to capture, obey the
                 └────────┬──────────┘   reference rule"
                          │ route
                 ┌────────▼──────────┐   delegate
                 │   fkb-* skills    │──── writes ───▶ kb-* skills
                 └────────┬──────────┘
                    read  │  the sole coupling point between bundles
        ┌─────────────────▼─────────────────────────────┐
        │  workspace.okf.yaml   (~/.config/…)           │
        │  path · referenceable_by · writable · publish │
        └─────────────────┬─────────────────────────────┘
                resolve   │  path → local checkout
       ┌──────────┬───────┼────────┬───────────────┐
       ▼          ▼       ▼        ▼               ▼
    public      team    peer    private     upstream (r/o)
 └─────────── the bundles (independent OKF repos) ──────────┘
```

### The two coupling points

The stack has exactly two places where otherwise-independent things are bound together, at two
different layers:

- **The manifest binds the skills to the bundles.** `workspace.okf.yaml` is the only artifact that
  knows your bundles are related — the data-layer glue detailed below.
- **The global `AGENTS.md` block binds the agent to the skills.** A managed block in your agent's
  instructions tells it that fkb exists on this machine and when to reach for it — query to read,
  ingest to capture, obey the reference rule. Without it the skills are installed but dormant: present
  on disk, but nothing tells the agent to use them. This is the agent-layer glue.

`install-glue` writes both in one step, because a working setup needs both — bundles that know their
policy, and an agent that knows the bundles exist.

### The manifest

Each bundle is a standalone OKF repo that does not know the others exist. One file couples them: the
manifest at `~/.config/federated-knowledge/workspace.okf.yaml`. It is the only artifact aware that
your bundles are related, and it assigns each one four fields.

| field | question it answers | default |
| --- | --- | --- |
| `path` | where the bundle is checked out locally | (required) |
| `referenceable_by` | who may point *at* me - the leak rule | `[]` (no one) |
| `writable` | may an agent author into me here | `false` |
| `publish` | my published URL base, if any | `null` |

The defaults are the safe ones: a new bundle can't be referenced and can't be written to until you
change its properties in the manifest. Why that prevents accidental leaks — and what it does not
guarantee — is the [trust model](#trust-model-and-data-leaks) below.

An optional top-level `workspace_root` sets where relatively-pathed bundles resolve. A bundle with an
absolute path ignores it and stays where it is - this is how you onboard a checkout that already lives
somewhere on disk without moving it. With no `workspace_root`, every bundle must give an absolute
path.

The `fkb-*` skills read this manifest and decide **which bundle and whether allowed**; they delegate
every actual write to the single-bundle `kb-*` skills. `fkb` never edits a concept body, `index.md`,
or `log.md` itself. Reads fan out across all bundles; writes target one bundle at a time.

### The reference rule

> A concept in bundle **A** may reference a concept in bundle **B**
> **iff** A = B **or** A ∈ B.`referenceable_by`.

`referenceable_by` is inbound-only: it lists who may point *at* a bundle, which is exactly the
disclosure axis. `"*"` means anyone (a public foundation); `[]` means no one (a sealed private tier).
Two bundles that may cite each other list each other - a symmetric, unranked permission. One
`manifest.py can-reference A B` call decides it.

### Trust model and data leaks

The whole point of separating bundles by tier is that private knowledge must not surface where it may
not be seen. Two rules do the work, and they are deliberately asymmetric:

- **Reading is unrestricted.** Any bundle may be read to answer a question — tier is preserved by
  citing every hit bundle-qualified, not by hiding it.
- **Writing is gated.** A capture targets one `writable` bundle; placing anything into a more-open
  bundle than the sealed default is irreversible disclosure and needs human sign-off. Authoring a
  cross-bundle link obeys the reference rule above.

Sealed-by-default is what makes this safe to forget: a new bundle leaks nothing until you open it on
purpose.

**What this does not guarantee.** These gates live in the skills, and the skills are carried out by an
agent — so this is a discipline the agent follows, not a mechanism that cannot be bypassed. The real,
enforceable guards live in each publishing bundle's own repo: the `fkb-lint` cross-bundle check, and
each bundle's pre-commit hooks and pre-publish review (see
[Why this works](#why-this-works)). `fkb` makes the right thing easy; the bundle's own hooks make the
wrong thing fail.

### How knowledge flows in and out

The two everyday operations are asymmetric. Reading fans out across every bundle; writing targets one
bundle and passes through the gates. In both, `fkb` decides *which bundle and whether allowed* and
`kb` does the actual work.

**Insertion** — `fkb-ingest` captures a source into one bundle, chosen by sensitivity:

```text
  source (note / PDF / web page / transcript)
        │
        ▼
  ┌──────────────────────────  fkb-ingest  ─────────────────────────┐
  │  classify   read source → pick bundle by sensitivity            │
  │             └─ in doubt → most-private writable  (fail closed)  │
  │  gate       writable? ──────────────── no  → reject             │
  │             more open than sealed? ─── yes → human sign-off !   |
  │  cross-link can-reference <target> <B>  → drop link or emit URL │
  └───────────────────────────────┬─────────────────────────────────┘
                                  │  target.resolved_path, hand off the write
                                  ▼
                             ┌───────────┐
                             │ kb-ingest │  writes concept + index.md + log.md
                             └─────┬─────┘
                                   ▼
                         one target bundle  (writable, chosen tier)
```

**Extraction** — `fkb-query` reads every bundle, because the leak rule governs authoring links, not
reading:

```text
                      question
                          │
        ┌─────────────  fkb-query  ─────────-───┐
        │  fan kb-query across every bundle     │
        └──────────────────┬────────────────────┘
                           │  read-all
        ┌────────┬─────────┼─────────┬──────────────┐
        ▼        ▼         ▼         ▼              ▼
     public    team      peer     private     upstream (r/o)
        └────────┴────┬────┴─────────┴──────────────┘
                      ▼  merge + rank (dedupe, flag conflicts)
              one answer, every hit cited bundle-qualified
              (public:… / private:… / URL)
```

This read-all / write-one split is the [trust model](#trust-model-and-data-leaks) in action. A query
that the user asks to file back hands off to `fkb-ingest` — it never writes directly.

## Why this works

**One coupling point, not many.** The alternative - cross-bundle links by published URL, no manifest -
smears the local-to-URL mapping across every link and every ingest. Centralizing it in one file's
`path` and `publish` fields keeps each bundle standalone: it clones, publishes, and lints on its own,
unaware it is part of a federation.

**Inbound allow-lists express the real topology.** A ranked sensitivity lattice cannot state "these
two peers may cite each other but neither is above the other." A per-bundle `referenceable_by`
allow-list can, and reduces the whole leak check to one dictionary lookup. Sealed-by-default means a
new bundle leaks nothing until you say otherwise.

**The skills are convenience; the boundary lives in the bundles.** A direct `kb-ingest` bypasses
`fkb` entirely, so the manifest cannot be the security boundary. The real guard is each publishing
bundle's own pre-commit hook, secret scanner, and CI publish-gate - they run on the commit regardless
of which skill authored it. `fkb` makes the right thing easy; the bundle's own hooks make the wrong
thing fail. This keeps the security-critical surface small and lets upstream `kb-*` improvements flow
in for free.

## Requires: the kb skills

The `fkb-*` skills delegate every bundle mutation to `kb-init`, `kb-ingest`, `kb-query`, and
`kb-lint` from [stjbrown/agent-knowledge](https://github.com/stjbrown/agent-knowledge). If they are
missing, every `fkb` skill's preflight (`manifest.py check-deps`) fails loudly with the install
command rather than silently hand-rolling the operation - bypassing `kb` also bypasses OKF
conformance.

## manifest.py - the deterministic core

A zero-install Python helper every `fkb` skill calls, run via `uv` (PEP 723 inline deps). After
`install-glue` it lives under `${XDG_CONFIG_HOME:-$HOME/.config}/federated-knowledge/`; invoke it there.

```bash
uv run "${XDG_CONFIG_HOME:-$HOME/.config}/federated-knowledge/manifest.py" list                      # resolved bundles
uv run "${XDG_CONFIG_HOME:-$HOME/.config}/federated-knowledge/manifest.py" resolve <bundle>          # one bundle as JSON
uv run "${XDG_CONFIG_HOME:-$HOME/.config}/federated-knowledge/manifest.py" can-reference <from> <to> # exit 0 allow / 1 deny
uv run "${XDG_CONFIG_HOME:-$HOME/.config}/federated-knowledge/manifest.py" check-deps                # exit 0 uv+kb present / 4 missing
uv run "${XDG_CONFIG_HOME:-$HOME/.config}/federated-knowledge/manifest.py" validate                  # exit 0 well-formed / 2 malformed
```

Tests and developer setup live in [CONTRIBUTING.md](CONTRIBUTING.md).

## Appendix

### Building a workspace manually

Given the [installed skills](#prerequisites), the basis of the federation is the actual workspace definition.
You can initialise one with:

```bash
uv run ~/.agents/skills/fkb/scripts/install-glue  # optionally with --root ~/some/dir
```

This will:

- create the workspace definition at `~/.config/federated-knowledge/workspace.okf.yaml`
  with a proposed `workspace_root` (defaults to `~/.agents/knowledge`, unless `--root` was specified)
- install a launcher at a fixed path so the skills and you invoke one stable command
- tell you how to make your agent aware of the fkb skills and the workspace

There is no standard location for agent instructions, so `install-glue` does not edit any file it does
not own. Instead it will print instructions on how agents should invoke it to obtain the block
(or humans invoke it for manual copying).

### Adding knowledge bundles

A bundle enters the federation when it gets a line in the workspace manifest. Three convenience
commands cover the three ways a bundle arrives — each clones or scaffolds as needed, asks for the
federation policy it cannot infer (`referenceable_by`, `writable`, `publish`), and writes the manifest
line for you. They map onto the three kinds of bundle you started with.

**`clone-bundle <url>`** — a bundle that lives in a remote git repo you want a local copy of. It
clones the repo under `workspace_root`, then discovers where the OKF content sits inside it: a repo is
often infrastructure at the top with the bundle in a `docs/` subdir, so the command inspects the
checkout for the OKF root and asks you to confirm or pick the subdir when it is ambiguous. It records
that subdir as the bundle's `path`.

```bash
uv run "${XDG_CONFIG_HOME:-$HOME/.config}/federated-knowledge/clone-bundle" <url> <name> [referenceable_by]
```

**`add-bundle <path>`** — a bundle already checked out somewhere on your disk, which you want to
federate without moving. It takes the local path as-is (absolute, so `workspace_root` does not apply),
confirms the OKF root, asks for the policy, and adds the line. Nothing is cloned or relocated.

```bash
uv run "${XDG_CONFIG_HOME:-$HOME/.config}/federated-knowledge/add-bundle" <name> <path> [referenceable_by]
```

**`create-bundle <name>`** — a brand-new bundle you want to author into, whether to share or for
private notes. It scaffolds a minimal conformant OKF bundle under `workspace_root`, defaults it to
`writable: true` and the sealed `referenceable_by: []`, and registers it.

```bash
uv run "${XDG_CONFIG_HOME:-$HOME/.config}/federated-knowledge/create-bundle" <name> [referenceable_by]
```

Each command ends by showing the manifest line it wrote and the resolved policy, so you can see what
entered the federation before using it.
