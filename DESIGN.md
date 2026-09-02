# DESIGN — federated knowledge

**Status:** settled direction, not yet implemented. This document is the **sole source of
truth** for the design. Change it here first; `README.md`, `DECISIONS.md` and the current
`skills/` tree describe an earlier architecture until they are rewritten to match.

**Date:** 2026-09-01

---

## 1. What we build

A federated, agent-agnostic, human-friendly system for capturing and sharing knowledge,
following the [LLM Wiki](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f)
pattern.

- Each knowledge bundle is its own git repo, optionally published to GitHub Pages.
- Bundles sit at different privacy tiers: public, team, private, plus read-only upstreams.
- Content is [OKF v0.2](https://github.com/GoogleCloudPlatform/open-knowledge-format)
  markdown — plain files, edited directly in an editor, in Obsidian, or in the GitHub web
  UI.
- Agents read and write it as a first-class consumer, across harnesses.

We do not build a knowledge platform. OKF is a file format; this stays a thin layer over
git. We do not build a security mechanism — access control is git remote permissions and
the CI publish gate, and everything here is an agent guardrail that prevents accidents,
not attackers.

### Open questions

Detail in §9. Nothing here blocks §10.

| # | Question | Blocks |
| --- | --- | --- |
| 9.1 | How `fkb search` ranks once bundles outgrow `rg` | nothing yet |
| 9.2 | Which frontmatter a bundle requires beyond `type`, and where it declares that | `fkb lint` |
| 9.3 | Whether markdown raw sources become `references/` concepts or stay outside the bundle | bundle layout |
| 9.4 | How non-knowledge pages in a bundle satisfy OKF §11 | first migration |
| 9.5 | How a bundle lints standalone, without knowing it is federated | bundle template |

---

## 2. Invariants

These bound every decision below. Each was paid for once already (appendix A).

1. **The knowledge file is the source.** Nothing generates it from a shadow copy. No ingest
   pipeline stands between an agent and the file it means to write.
2. **A skill may instruct an agent to run a deterministic command. A skill never instructs
   an agent to invoke another skill.** Prose to command works; prose to prose does not.
3. **Deterministic behaviour lives in the CLI, never in prose.** The skill body says
   `run fkb list`; it does not describe what the output looks like.
4. **Everything ships self-contained.** No cross-skill dependencies, no post-install
   configuration, no assumption that another package is present.
5. **Every command justifies itself** against "git or an editor already does this clearly".

---

## 3. Architecture

Three layers, each doing one thing.

| Layer | Carries | Loads |
| --- | --- | --- |
| **AGENTS.md block** (~5 lines) | that fkb exists here, and when to reach for it | always |
| **The `fkb` skill** | conventions, workflow, OKF reference, house style | on activation, then on demand |
| **The `fkb` CLI** | bundle resolution, lint, policy checks | on invocation |

The skill is the portable artifact. `~/.agents/skills/` is read natively by Codex, Cursor,
Gemini CLI, Zed and Goose; Claude Code reaches it through a symlink from
`~/.claude/skills/`. Every harness names its instruction file differently, so the block is
the harness-specific part.

The block exists for **activation**. The failure it prevents is an agent that never reaches
for the skill and writes a markdown file wherever it happens to be. It carries the two
triggers an agent does not infer: check fkb before web-searching, and file durable
knowledge when you learn it.

---

## 4. Bundles and the manifest

One file couples otherwise-independent repos: `$XDG_CONFIG_HOME/fkb/workspace.yaml`. Four
fields per bundle.

| field | question it answers | default |
| --- | --- | --- |
| `path` | where the bundle is checked out locally | (required) |
| `referenceable_by` | who may point *at* me | `[]` (no one) |
| `writable` | may an agent author into me here | `false` |
| `publish` | my published URL base, if any | `null` |

Both security-relevant defaults fail closed, so a new bundle discloses nothing until you
open it deliberately.

**The reference rule.** A concept in bundle **A** may reference a concept in bundle **B**
iff `A = B` or `A ∈ B.referenceable_by`. `referenceable_by` is inbound-only, which is the
disclosure axis: it lists who may point at a bundle. Two bundles that may cite each other
list each other.

> Inbound allow-lists express unranked symmetric peers, which a ranked sensitivity lattice
> cannot, and reduce the leak check to one dictionary lookup.

We keep this policy in the manifest rather than in each repo, because `path` and `writable`
are properties of *this machine* and a bundle cannot usefully self-describe them. If bundles
are ever distributed across many independently-administered workspaces, move only
`referenceable_by` into the target bundle, since it is an inbound permission the target
owns.

### Where policy is enforced

| Concern | Enforced by |
| --- | --- |
| Who can read or write a bundle | git remote permissions |
| What reaches the public site | CI publish gate, `mkdocs build --strict` |
| Accidental agent writes | `writable` in the manifest (guardrail) |
| Accidental cross-tier links | `referenceable_by` lint check (guardrail) |

The README says this plainly. The last two are guardrails, not access control: a direct
write bypasses any skill, so the enforceable guards are each bundle's own pre-commit hooks
and its publish gate. `fkb` makes the right thing easy; the bundle's hooks make the wrong
thing fail.

---

## 5. Content model

Three layers, from the LLM Wiki pattern.

### 5.1 The wiki

OKF concept documents, authored directly and edited directly.

**Reading:** the agent reads `index.md` first, then follows links into the concepts it
needs. `fkb search` (§7) covers the case where the right index is not obvious.

**Writing:** there is no `fkb ingest`. An agent has a write tool and knows markdown.

1. `fkb list` — which bundles exist, which are writable, what the tiers are
2. the agent writes the `.md` file directly
3. `fkb lint` — did that violate anything

`fkb` answers *where* and *is this legal*. It never touches a concept body, renders, or
hashes.

### 5.2 Assets

Images, screenshots and Excalidraw sketches — whether clipped or drawn by us — live
**beside the concept that references them**, named after it:

```text
principles/autofix-in-the-hook.md
principles/autofix-in-the-hook-prek-output-20260827.png
```

not in an `assets/` or `images/` subtree. A concept and its pictures move together and read
together, and a relative link survives Obsidian, MkDocs and the GitHub web UI unchanged.

> Neither Git LFS nor OKF argues for a separate directory. LFS matches on extension
> (`*.png filter=lfs`), not location. OKF §11 only ever treats `.md` files as concepts, so a
> `.png` beside a concept is invisible to conformance.

The cost is real and accepted: renaming or moving a concept means moving its assets too.

### 5.3 Raw sources

External artifacts you did not author and cannot change: clipped articles, PDFs,
transcripts, recordings.

**Non-markdown raw sources** (PDFs, images, audio) follow the asset rule above — beside the
concept that draws on them.

**Markdown raw sources** cannot, and this is a spec constraint rather than a preference:
OKF §3.1 makes every non-reserved `.md` in the tree a concept document requiring `type:`. A
clipped article dropped beside a concept becomes a concept. OKF §6.3 anticipates exactly
this and gives it a home:

> A `references/` subdirectory conventionally mirrors external material, run instructions,
> or code **as first-class concepts within the bundle**. […] It is a naming convention, not
> a requirement.

So the spec's answer is not to hide external material from the validator but to admit it as
a concept with its own `type` (`Source`, `Transcript`, `Article`). See §9.3, which is the
one part of this still open.

Whatever the location, two rules hold:

1. **The archive is not a pipeline stage.** You write the concept directly and archive the
   source alongside only when it is perishable. The archive is never an input an agent must
   manufacture before it is allowed to write.
2. **Provenance is a pointer, not a copy.** OKF links the layers natively through
   `sources: [{ id, resource, title, author, last_modified }]` and `resource:`. **A concept
   points at its source rather than shadowing it.** A stable public URL stores nothing and
   records `resource:`; a perishable or access-gated source gets archived, with
   `sources[].resource` pointing at the archived copy.

> Licensing does not choose a directory — it chooses whether to **publish**. Verbatim
> third-party content is the same obligation in `references/` as beside a concept, and the
> real decision is whether the publish gate emits it at all. Private bundles carry no such
> question.
>
> The ~100 opencode session transcripts currently in the private vault are legitimate raw
> sources under this reading, and are the concrete case §9.3 has to settle.

### 5.4 The schema

The AGENTS.md block and the skill. This is where "how we do it" lives, and it is the layer
we co-evolve.

---

## 6. The skill

**One skill.** Triggers differ — "what do we know about X", "note this down", "audit the
wiki" — and splitting sharpens the routing descriptions. We keep one anyway, because
`references/` is scoped to a single skill directory: three skills means duplicating the OKF
reference three times or symlinking it, and both drift. Split later if activation proves
unreliable; siblings would then call the CLI, never each other.

### 6.1 What goes where

> If it is a branch the agent takes, it belongs in `SKILL.md`. If it is a table the agent
> consults, it belongs in `references/`.

Progressive disclosure sets the economics: name and description load at startup, the body
loads on activation, `references/` loads only when a task reaches for it. The body stays
short and almost entirely control flow, well under 500 lines.

### 6.2 Layout

```text
~/.agents/skills/fkb/
├── SKILL.md                    # decisions / control flow
├── scripts/
│   ├── fkb                     # our CLI (PEP 723, uv)
│   └── okf_validate.py         # vendored, unmodified (§8)
└── references/
    ├── SPEC.md                 # vendored verbatim OKF v0.2 (§8)
    ├── APACHE-2.0.txt          # vendored — licence for SPEC.md
    ├── concept-template.md     # vendored, lightly adapted
    ├── house-style.md          # ours
    └── federation.md           # ours
```

Shipping the CLI inside the skill as `scripts/` means one `npx skills add …` installs both,
and there is no separate step to forget. The manifest lives outside, in
`$XDG_CONFIG_HOME/fkb/`, because it is machine-local user data rather than code.

**Nothing installs anything.** Installation is a one-time human command. The skill's
contract is: present, use it; absent, stay quiet; present but broken, tell the human and
install nothing.

> A skill that installs runs at unpredictable moments during unrelated work.

### 6.3 Filing knowledge — the decision tree

This is the body's spine.

1. **What am I holding?**
   - an *external artifact* — a raw source, continue at 2
   - an *insight from this session*, such as a decision made or a principle extracted —
     **there is no raw source. Write the concept directly.**
2. **If external, is it perishable?** A stable public URL archives nothing and records
   `resource:`. A perishable or access-gated source gets archived, recorded in `sources[]`.
3. **Which bundle?** `fkb list`, then pick by sensitivity. In doubt, the most-private
   writable bundle.
4. **Write the file directly** with the normal write tool.
5. **Frontmatter:** the required floor inline; `references/concept-template.md` and
   `SPEC.md` §5 for the optional palette. Set `generated:`; never self-assert `verified:`
   (§6.4).
6. **Update `index.md`, append to `log.md`.**
7. **Run `fkb lint`.**

Seven steps, no lookups, no other skill invoked.

> Step 1's second branch is stated as an explicit prohibition rather than left as an
> omission — it is the one an ingest-shaped tool gets wrong.

### 6.4 Actors and trust

OKF §7 gives one convention for every identity field (`generated.by`, `verified[].by`):

| Shape | For | Spec's example |
| --- | --- | --- |
| `<producer>/<version>` | agents and tools | `reference_agent/gemini-2.5-pro` |
| `human:<id>` | a person | `human:ahormati` |
| `process:<id>` | an automated process | `process:finance-nightly` |

**Producer is the program that did the writing; version is the model it ran on.** The
spec's own example pairs a program (`reference_agent`) with a model (`gemini-2.5-pro`), so
ours pairs the harness with the model:

```yaml
generated: { by: opencode/claude-opus-5, at: 2026-09-01T14:22:00Z }
verified:  { by: human:felix,            at: 2026-09-02T08:10:00Z }
```

| Situation | `by` | Not |
| --- | --- | --- |
| An agent in opencode wrote the concept | `opencode/claude-opus-5` | `fkb`, `claude`, `Sisyphus`, `opencode` |
| An agent in Codex wrote it | `codex/gpt-5.6-sol` | `codex/codex` |
| Felix wrote or reviewed it | `human:felix` | `Human:felix`, `human/felix`, `felix` |
| A scheduled job refreshed it | `process:wiki-nightly` | `process/wiki-nightly` |

> **The skill is not an actor.** `fkb` is prose an agent reads; the agent is what acts.
> Naming the skill would record the same string no matter which harness or model produced
> the content, which is precisely the information the field exists to carry.

Two consequences worth stating in the skill body:

- `generated.by` is **required** whenever `generated` is present (OKF §5.2). Half a
  `generated` block is malformed.
- OKF §5.3 derives the trust tier from `verified` alone: absent ⇒ **unverified**,
  non-`human:` actors only ⇒ **machine-confirmed**, any `human:<id>` ⇒ **human-reviewed**. A
  near-miss such as `Human:felix` or `human/felix` silently downgrades a reviewed concept to
  machine-confirmed, which earns a dedicated lint check rather than a note in a guide.

### 6.5 Two lints, one of them code

| | Lives in | Checks |
| --- | --- | --- |
| **Deterministic** | the CLI | OKF §11 conformance, **the bundle's declared floor**, actor shapes, links resolve, `stale_after` passed, the reference rule |
| **Semantic** | `SKILL.md` prose | contradictions between pages, claims superseded by newer sources, orphans, concepts mentioned but lacking a page, gaps |

**The floor is what the bundle requires beyond OKF's `type`** — plausibly `title`, `status`
and a `generated` block, so that provenance is enforced rather than merely encouraged. OKF
deliberately makes those optional and requires consumers to tolerate their absence, so the
floor is ours to impose, not the spec's.

Two properties follow from bundles we do not control, and from a bundle needing to lint
itself without knowing it is federated:

- **The floor is per-bundle, not global.** A read-only upstream is held to OKF conformance
  and nothing more.
- **The bundle declares its own floor**, so its standalone pre-commit hook and `fkb lint`
  read one declaration and cannot disagree. Where that declaration lives is §9.2.

Semantic lint is the operation a retrieval system structurally cannot perform, and it is
the payoff of the whole pattern rather than a formality. It is also the second reason the
skill exists.

`status: deprecated` and `stale_after` are the *inputs* to deterministic lint. That is why
the optional OKF fields earn their keep: without them, lint has nothing to check.

---

## 7. The CLI

Five commands, and we stay suspicious of the sixth. Single-file PEP 723 Python, run through
`uv`.

```text
fkb list                    # bundles, paths, tiers, publish URLs
fkb search <query>          # ripgrep across bundles, bundle-qualified hits
fkb lint [bundle]           # vendored OKF validator plus the bundle's floor
fkb resolve <bundle>        # one bundle as JSON, for scripting
fkb init | fkb add <path>   # setup, run once by a human
```

`can-reference` folds into `lint`, being a check rather than a workflow. Clone, pull, commit
and file creation get no command, since git and the editor already do them clearly.

### `fkb search` is in scope, and it is not a search engine

**What it adds over plain `rg` is the bundle set, not the ranking.** It knows which bundles
exist and where they are checked out, and it emits each hit qualified by bundle and, where
`publish` is set, as a real URL. An agent that greps a directory it happened to guess gets
neither. That value holds at 40 concepts and at 4000, so we build it now.

The engine underneath stays deliberately dull: ripgrep over concept bodies and frontmatter,
deterministic and dependency-free. Ranking is §9.1.

> We do not dispatch to a better engine when one happens to be installed. Identical queries
> would return different results on different machines, and a search whose behaviour depends
> on what a laptop has lying around is not one you can reason about. Adopting a heavier
> engine is an explicit, recorded choice.

`fkb lint` shells out to the vendored `okf_validate.py` for OKF conformance and adds its own
passes: the bundle's declared floor, actor shapes, the reference rule, no-copied-state. It
does not reimplement conformance checking.

---

## 8. Vendoring from okf-skills

[scaccogatto/okf-skills](https://github.com/scaccogatto/okf-skills) is MIT-licensed, 353
stars, actively maintained, and independently arrived at this architecture: a 151-line
decision-flow SKILL.md, a 1012-line verbatim spec in `reference/`, templates, and
deterministic Python in `scripts/`. It is a personal project, not an Anthropic one, despite
its "for Claude Code" tagline.

> Their ADR `self-contained-skills.md` states invariant 4 in their own words: "Each skill
> ships its script inside its own directory… No absolute paths, no post-install
> configuration."

### What we take

| Artifact | Size | Why |
| --- | --- | --- |
| `reference/SPEC.md` | 1012 lines | The verbatim spec. Our current excerpt is 43 lines — enough to check conformance, not enough to author against. Loads on demand only. |
| `templates/concept.md` | 38 lines | Every optional field present and commented, which makes filling them the default rather than an act of recall. |
| Actor convention (§7) | ~10 lines | See §6.4. |
| `okf_validate.py` | 571 lines | PEP 723 plus pyyaml, `--json`, `--strict`, `--max-warnings N`. We do not write an OKF linter. |

### What we skip

- **Attested Computations (OKF §10)** — sanctioned SQL and metric concepts for data
  catalogues. It rides along inertly inside `SPEC.md`; the house guide leaves it out.
- **MCP server, visualizer, GitHub Action, stop hooks, `backfill`** — ~1400 LOC of
  Claude Code plugin scaffolding. Our publishing stack renders and gates already.
- **`agents/` subagents** — harness-specific.
- **`--migrate`** (v0.1 to v0.2) — we have no v0.1 content.
- **`.okf/` as the default bundle root** — our MkDocs layout owns `docs/`.

### Mechanics

Copy their provenance header, which names the upstream commit and makes a later re-pull a
diff:

```text
Vendored from …/okf/SPEC.md
Commit:  3fcbb9f828c2f23d109c855ee403c3a4c81f3a96
License: Apache-2.0 (c) Google LLC — included verbatim under its terms.
```

Two licences travel with the files:

- `SPEC.md` is Apache-2.0, © Google LLC. Keep the header, ship `APACHE-2.0.txt`, record it
  in `NOTICE`.
- `okf_validate.py` and `concept-template.md` are MIT, © 2026 Marco Boffo. Retain the
  copyright and permission notice.

Two adaptations are required:

1. **Replace `${CLAUDE_SKILL_DIR}`.** It appears in every invocation line, and Codex,
   Gemini, Zed and Cursor do not set it. Cross-harness portability is why we use a skill at
   all.
2. **Vendor the validator unmodified.** House rules live in `fkb`, which calls it. Editing
   their file turns every future re-pull into a merge.

> We reject two alternatives. Depending on `okf-skills` reproduces the dependency breakage
> in appendix A. A git submodule pins versions but adds clone friction, and agents handle
> submodules badly.

---

## 9. Open decisions

### 9.1 Ranking, once `rg` stops being enough

`fkb search` ships ripgrep-backed (§7). The open part is what replaces the engine when
lexical matching stops finding things — not whether the command exists.

Karpathy reports index-first navigation working "surprisingly well at moderate scale (~100
sources, ~hundreds of pages)". Two days of capture produced ~40 concepts, so team-wide
rollout crosses that band quickly and the question is when, not if.

[qmd](https://github.com/tobi/qmd) is the named candidate: local hybrid BM25 and vector
search over markdown, with both a CLI and an MCP server. It is also heavy — an index to
build, keep fresh, and reason about per bundle.

**Revisit when** a query an agent should have answered from the bundles gets answered from
the web instead. Record the query when it happens; a handful of real misses is what should
justify an index, not a projection.

### 9.2 Where a bundle declares its floor

The floor (§6.5) is per-bundle and bundle-owned. Where it is written is open, and the
constraint is that one declaration must serve both `fkb lint` and the bundle's own
standalone pre-commit hook (§9.5).

Candidates: the bundle-root `index.md` frontmatter, which OKF §8 already permits extra keys
in and okf-skills already uses for its `upkeep:` flag; or a small dotfile at the bundle
root. The first keeps the bundle to markdown; the second is easier for a hook to parse
without a YAML dependency.

Also open: the floor's *content*. `title` and `status` are cheap. Requiring `generated`
is what makes provenance real, and is also the field most likely to be missing from any
bundle we did not author.

### 9.3 Markdown raw sources: `references/` concepts, or outside the bundle

OKF §6.3 sanctions `references/` as the home for mirrored external material, **as
first-class concepts**. That is the spec-aligned option: give a clipped article
`type: Source` and let it live in the bundle.

It has consequences to weigh:

- Raw sources appear in `index.md`, in search results, and on the published site unless the
  publish gate excludes them.
- It blurs Karpathy's layer boundary, where raw sources are the thing the wiki is
  *distilled from*, not part of the wiki.

The alternative — keeping them above the bundle root — preserves the boundary and keeps the
validator quiet, at the cost of leaving the spec's own convention unused and putting the
archive somewhere `path` does not reach.

**Decide during the first migration**, when the ~100 transcripts need a home.

### 9.4 Non-knowledge pages inside a bundle

OKF §3.1 is absolute: every non-reserved `.md` is a concept. With `docs/` as the bundle
root, `running-linux`'s `docs/meta/editing_on_github.md` and `docs/meta/tech_stack.md` are
concepts that currently carry only `title:`.

Three ways out, none yet chosen: give them `type: Document` and accept them as concepts;
move them above the bundle root and lose them from the published nav; or narrow the bundle
root to a subdirectory of `docs/` so the meta pages sit outside it.

> A skip-list is not an option. okf-skills is explicit that one "would put the checker out
> of conformance", and vendoring their validator means inheriting that stance.

### 9.5 How a bundle lints standalone

A bundle is a normal git repo that does not know it belongs to a federation, so its own
pre-commit hooks have to enforce OKF conformance and its floor without `fkb` present. The
federation layer then adds only the checks that need the manifest: the reference rule and
cross-bundle links.

The open question is packaging. Publishing this repo as a `pre-commit` hook source lets a
bundle pin it by revision like any other hook, and keeps one implementation of the
deterministic checks. It also means the hook and the vendored copy inside the skill must
not drift — plausibly the skill's `scripts/` becomes the single source and the hook wraps
it.

This is the piece that makes "each bundle stands alone" true rather than aspirational, so
it wants settling before the bundle template is fixed.

### 9.6 Settled

- **Canonical OKF home** is `GoogleCloudPlatform/open-knowledge-format`. The
  `knowledge-catalog` path in the okf-skills header is stale; pin from the former.
- **Claude Code discovery** is not our problem — no Claude Code in use here. If it ever is,
  a `~/.claude/skills/fkb` symlink covers it.
- **Assets live beside their concept** (§5.2).

---

## 10. The path

One clean bundle comes before any framework work. A repo we are happy editing by hand is
what tells us whether `fkb` needs five commands or three.

1. **Neutralise the global AGENTS.md block.** It advertises fkb to every cold session while
   the skills it names are absent.
2. **Migrate the ~60 public concepts** into a git repo built from the `running-linux`
   template. The published concepts are canonical; the `raw/` copies add nothing.
   - add `type:`; drop `sources: [raw/…]` and `render_hash`
   - convert `[[wikilinks]]` to relative markdown links through a filename and title map,
     emitting an unresolved list for manual review rather than guessing
   - delete the `raw/` shadow tree after validation
   - settle §9.3 and §9.4 here, since the ~100 transcripts and the `meta/` pages both need
     a home before the template is fixed
   - verify with the vendored validator and `mkdocs build --strict`
3. **Use it for a week** with an editor, grep, git and the AGENTS.md block. Record friction
   that actually occurs.
4. **Build `fkb`** to what that week proved necessary. If cross-bundle discovery never hurt,
   we are done.
5. **Migrate the private bundle** once the public one is clean.
6. **Rewrite `README.md` and `DECISIONS.md`** to describe this design, after tagging the
   current architecture on an archival branch.

> Step 6 discards 20 commits and 56 green tests. Green tests do not make deleted
> architecture valuable; they are sunk cost, not a constraint.

---

## Appendix A — what the invariants cost

Kept short, and only to argue §2.

**agent-wiki (awiki)** produced the ~60 concepts we still consider our best content, and
three properties made it untenable. Every concept carried a shadow `docs/raw/<slug>.md`
plus a `.meta.yaml`; `raw/autofix-in-hook.md` and its published concept are byte-identical
apart from frontmatter, so an agent wrote a fake source purely to feed a pipeline that
re-emitted the file it already had (invariant 1). Backlinks track `[[wikilinks]]` only,
against our own blueprint and OKF §6.1. Nothing knew about tiers.

**fkb over the `kb-*` skills** reached 20 commits and 56 green tests. `fkb-query` called
`skill(name="kb-query")` per bundle and then executed the returned prose, which is control
flow through prompt obedience; the SKILL.md accumulated three shouted warnings against an
indirection we had introduced ourselves (invariant 2). `create-bundle` already bypassed
`kb-init` to hand-roll its scaffold, because a skill is prose rather than a callable binary.
The `kb-*` skills are not installed on this machine while the global AGENTS.md advertises
fkb, because skills have no dependency resolution — `npx skills add` copies a directory and
verifies no "requires" (invariant 4).

The conclusion this design returns to was reached on 2026-08-27 in
`public/docs/research/substrate-options-…md`, ranked first among the options considered:

> OKF plain-markdown files + thin pre-commit scripts + an AGENTS.md contract, no engine

---

## Appendix B — deliberate deviations

| Source | Says | We do | Why |
| --- | --- | --- | --- |
| Karpathy | "You never (or rarely) write the wiki yourself — the LLM writes and maintains all of it" | Felix co-authors and edits concepts directly | Karpathy's vault is private, single-reader, optimised for compounding synthesis. Ours is published, multi-tier and human-facing, with a house voice, prek hooks and GitHub web editing as a deliberate entry point. |
| OKF §11 | Consumers tolerate every missing optional field | `fkb lint` enforces a per-bundle floor above `type` | Provenance that is merely encouraged does not get written. The floor is ours, not the spec's, and applies only to bundles we own (§6.5). |
| okf-skills | `.okf/` at the repo root | `docs/` | The publishing stack owns that directory. Consequences for non-knowledge pages are §9.4. |
| awiki | `[[wikilinks]]` | standard markdown links | Our blueprint mandates them, OKF §6.1 specifies them, and Obsidian and MkDocs both support them. |

---

## Sources

- [Karpathy, LLM Wiki](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f)
- [Open Knowledge Format v0.2](https://github.com/GoogleCloudPlatform/open-knowledge-format)
- [scaccogatto/okf-skills](https://github.com/scaccogatto/okf-skills) — MIT
- [stjbrown/agent-knowledge](https://github.com/stjbrown/agent-knowledge) — the `kb-*` skills
- [TacoTakumi/agent-wiki](https://github.com/TacoTakumi/agent-wiki)
- [Agent Skills specification](https://agentskills.io) — `SKILL.md`, `references/`,
  `scripts/`, progressive disclosure
- Local: `~/.agents/wikis/public/docs/research/substrate-options-…md`,
  `blueprints/mkdocs-material-pkb-publishing-stack.md`
- Local: `~/Projects/public/running-linux` — the working publishing stack
