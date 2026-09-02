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

Detail in §9. None of them blocks the first task; §10 says which task settles each, and
answering earlier than that trades away what the work would have told us.

| # | Question | Settled by |
| --- | --- | --- |
| 9.1 | How `fkb search` ranks once bundles outgrow lexical matching | T4, from journal evidence |
| 9.2 | The floor's exact content, and the config file's name | T1 |
| 9.3 | Whether markdown raw sources become `references/` concepts or stay outside the bundle | T1 |
| 9.4 | How non-knowledge pages in a bundle satisfy OKF §11 | T1 |
| 9.5 | How a bundle lints standalone, without knowing it is federated | T6 |
| 9.6 | How knowledge is structured inside a bundle — directories, `tags`, publishing nav | T1, per bundle |
| 9.7 | Whether we may assume more than `uv` is installed | T4 |

§9.8 records what is settled.

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

### A worked manifest

```yaml
# $XDG_CONFIG_HOME/fkb/workspace.yaml
workspace_root: ~/.agents/knowledge   # relative bundle paths resolve under this

bundles:
  # Published foundation. Anyone may cite it.
  public:
    path: ./public/docs
    referenceable_by: "*"
    writable: true
    publish: https://example.com/kb

  # Two unranked peers: each names the other. Symmetric, order-free.
  peer:
    path: ./peer/docs
    referenceable_by: [team]
    writable: true
  team:
    path: ./team/docs
    referenceable_by: [peer]
    writable: true

  # Sealed. Nothing may point at it, so its content cannot surface elsewhere.
  private:
    path: ./private/docs
    referenceable_by: []
    writable: true

  # Someone else's bundle: read and cite freely, never author into.
  upstream:
    path: /home/felix/src/their-kb/docs
    referenceable_by: "*"
    writable: false
    publish: https://them.example/kb
```

An absolute `path` ignores `workspace_root` and stays where it is, which is how a checkout
that already lives somewhere gets adopted without moving. With no `workspace_root`, every
path must be absolute.

Both defaults are the cautious ones: omit `referenceable_by` and nothing may cite the
bundle; omit `writable` and no agent may author into it.

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

#### The AGENTS.md block

It loads on every session, so it stays at roughly this length. Its only job is to make an
agent reach for the skill; everything else lives one hop away.

```markdown
## Knowledge bundles (fkb)

Durable knowledge — decisions, research, fixes worth keeping — lives in privacy-tiered
markdown bundles managed by the `fkb` skill. When the user says "the wiki", "my notes"
or "the team wiki", they mean these.

- Before searching the web, check the bundles.
- When something durable is learned, file it.
- Load the `fkb` skill for how; it carries the conventions and the commands.

If the `fkb` skill is not installed, skip this silently.
```

Three properties matter more than the wording. It names the trigger phrases, because an
agent will not guess that "my notes" means a bundle. It defers everything procedural to the
skill, so the two cannot drift. It fails silent, so a machine without fkb loses nothing.

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
    ├── getting-started.md      # ours — onboarding (§6.7)
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

**The floor is what the bundle requires beyond OKF's `type`.** OKF deliberately makes
everything else optional and requires consumers to tolerate absence, so the floor is ours
to impose, not the spec's.

The floor holds **fields that are always knowable when the file is written**, not every
field we would like to see:

| Field | In the floor | Why |
| --- | --- | --- |
| `type` | yes | OKF §11 requires it anyway |
| `title`, `description` | yes | Always knowable; they feed `index.md` and search snippets (OKF §4.1) |
| `status` | yes | Always knowable; an input to deterministic lint |
| `generated` | yes | Always knowable, and the field that makes provenance real rather than encouraged |
| `verified` | **no** | Its absence *is* the signal |
| `stale_after` | no | Only meaningful for content that expires; a principle does not |
| `sources`, `resource` | no | Only when the concept derives from something |

> **`verified` cannot default to empty.** OKF §5.3 derives the trust tier from absence:
> no key ⇒ unverified. Writing `verified: null` says the same thing a second way, and the
> vendored validator rejects it outright — it warns unless the value is a `{by, at}` mapping
> or a list of them. Requiring the field would also push an agent toward self-asserting it,
> which §6.4 forbids. Absence is the encoding; leave it absent.

Enforcing an optional field converts a meaningful absence into noise. That is the limit on
"as rich as possible".

Two properties follow from bundles we do not control, and from a bundle needing to lint
itself without knowing it is federated:

- **The floor is per-bundle, not global.** A read-only upstream is held to OKF conformance
  and nothing more.
- **The bundle declares its own floor**, so its standalone pre-commit hook and `fkb lint`
  read one declaration and cannot disagree. Where that declaration lives is §9.2.

### 6.6 What `fkb lint` does across bundles

It iterates every bundle in the manifest and checks each one in place. It does not assume a
bundle carries a floor declaration or a pre-commit config — a bundle that declares nothing
is held to OKF conformance, which every bundle can meet.

**Findings in a non-writable bundle are reported as warnings, never errors.** An upstream we
cannot edit is not a failure state, and a lint that fails on what you cannot fix is a lint
you learn to ignore.

Semantic lint is the operation a retrieval system structurally cannot perform, and it is
the payoff of the whole pattern rather than a formality. It is also the second reason the
skill exists.

`status: deprecated` and `stale_after` are the *inputs* to deterministic lint. That is why
the optional OKF fields earn their keep: without them, lint has nothing to check.

---

### 6.7 The skill explains itself

Someone runs `npx skills add …`, opens a fresh session and asks "what is this, and how do I
start?". That question must be answerable from the skill alone, with no README, no web page
and no prior context. A skill that needs documentation elsewhere has failed the one job that
distinguishes it from a library.

**The user story, from the previous README.** Someone wants their agent to read from and
write into any combination of:

1. bundles that live in remote git repos, readable or writable;
2. bundles already checked out somewhere on disk, possibly without realising they are
   bundles;
3. bundles that do not exist yet, to share or to keep private.

Those three are how a bundle arrives, and they map onto the setup commands (§7).

**What the skill answers.** `SKILL.md` carries a short "new here?" branch that explains what
a bundle is, checks whether a workspace exists, and routes to the right first step.
`references/getting-started.md` carries the long form: the three arrival paths worked
through, what each manifest field means, and what to do first when nothing is configured.

> The split follows §6.1. "Do you have a workspace yet?" is a branch and belongs in the
> body. "Here is each arrival path in full" is a lookup and belongs in the reference.

**The acceptance test is behavioural**, and worth writing down because it is easy to fake:
a session with no prior context, given only the question, produces an accurate explanation
and a first command that works. Not a summary of the design — a next step the person can
run.

## 7. The CLI

Five commands, and we stay suspicious of the sixth. Single-file PEP 723 Python, run through
`uv`.

```text
fkb list                    # bundles, paths, tiers, publish URLs
fkb search <query>          # ripgrep across bundles, bundle-qualified hits
fkb lint [bundle]           # vendored OKF validator plus the bundle's floor
fkb resolve <bundle>        # one bundle as JSON: policy plus observed vocabulary
fkb init                    # create the workspace manifest — once per machine
fkb add <what>              # bring a bundle into the workspace — once per bundle
```

`can-reference` folds into `lint`, being a check rather than a workflow. Clone, pull, commit
and file creation get no command, since git and the editor already do them clearly.

### Setup is two steps, because they answer different questions

`fkb init` creates the workspace: the manifest file, with `workspace_root` and no bundles.
It runs once per machine and asks nothing about knowledge.

`fkb add` brings one bundle in, and covers the three ways a bundle arrives (§6.7):

| Arrival | What `add` does |
| --- | --- |
| A remote git repo | Clone it under `workspace_root`, find the bundle root inside it, register it |
| An existing local checkout | Register the path as-is, absolute, moving nothing |
| A bundle that does not exist yet | Scaffold a minimal conformant bundle, register it writable and sealed |

Each asks for the policy it cannot infer — `referenceable_by`, `writable`, `publish` — and
ends by printing the manifest line it wrote, so what entered the federation is visible
before it is used.

> Finding the bundle root matters more than it sounds. A repo is often infrastructure at the
> top with the bundle in `docs/`, so `add` inspects the checkout for the shallowest
> `index.md` and asks when the answer is ambiguous rather than guessing.

### `fkb resolve` reports what a bundle *does*, not only what it declares

Alongside the manifest fields, `resolve` returns the vocabulary in use: the `tags` and
`type` values that appear across the bundle, and its top-level directories. The skill
already calls `resolve` before writing (§6.3 step 3), so choosing a tag that matches its
neighbours costs no extra call.

This half of house style is **derived**, which is why it is the half in the CLI: it cannot
drift, needs no declaration, and works on read-only upstreams that will never adopt our
conventions. The *declared* half — casing rules, prohibitions, intent — lives in the bundle
beside its floor declaration (§9.2), never in the manifest (§9.6).

The scan is the one `lint` already performs over frontmatter.

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

### 9.2 Where a bundle declares its floor — a YAML file at the bundle root

**Settled: a small YAML file, not the bundle-root `index.md`.** The vendored validator
warns on any root-index key outside `okf_version` and its own `upkeep`:

```python
extra = set(meta) - {"okf_version", "upkeep"}
# → warn "§12 root index.md frontmatter may only carry `okf_version`"
```

Putting our floor there means our own linter warning about our own config on every run, and
silencing it would mean editing the vendored file (§8). A YAML file also parses without a
markdown-frontmatter reader, which the standalone hook (§9.5) wants.

Still open: the file's name and the floor's exact content. `title`, `description`, `status`
and `generated` are the candidates from §6.5; whether `tags` joins them depends on §9.6.

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

### 9.6 How knowledge is structured inside a bundle

*Deferred by agreement; recorded so it is not rediscovered.*

Nothing in this design dictates a bundle's internal shape, and OKF deliberately declines to
either:

> The directory structure is independent of the domain: producers organize concepts however
> makes sense for the knowledge being captured. (§3)

OKF gives exactly one classification key, `tags` — "a YAML list of short strings for
cross-cutting categorization" (§4.1) — and no file format for aggregating by it: "a consumer
that wants a tag-browsing view can synthesize one at consumption time by scanning
frontmatter" (§3.1). So there are two axes, directories and `tags`, and no third.

awiki introduced a third, `topic:`, whose value duplicated the top-level directory
(`topic: principles` inside `principles/`). That is copied state under our own no-copied-
state rule: the path already carries it, and the two can drift. **Drop `topic:` during
migration.**

The live tension is that top-level directories carry publishing meaning — nav sections, URL
prefixes — which pulls toward deciding them up front, while structure-emerges-over-time
pulls the other way. Both existing principles in the public bundle,
`split-orthogonal-classification-axes-across-folders-and-tags` and
`categorize-by-what-content-is-not-why-you-made-it`, already bear on this.

**This is per-bundle house style, not federation policy**, so it can differ between bundles
and does not belong in `fkb`. Pick it up when the first bundle's layout is fixed.

#### How an agent learns a bundle's style

Distinct styles across bundles create a real cost: the skill must decide *where* to write
(§6.3 step 3) and then *how* to write for that bundle. Three answers, ranked.

1. **Converge the bundles we own on one house style.** The cheapest fix by a distance.
   Better discovery tooling makes ten vocabularies cheaper to endure; one vocabulary makes
   the problem absent. Discovery then only matters for upstreams we do not control.
2. **Derive the rest.** `fkb resolve` reports the tags, types and top-level directories a
   bundle actually uses (§7). Derived facts cannot drift, need no declaration, and work on
   an upstream that will never adopt our conventions — which is exactly the case a
   declaration cannot reach.
3. **Declare what derivation cannot see** — casing rules, prohibitions, intent — in the
   bundle, beside its floor declaration (§9.2). One file, one standalone-parseable answer.

> **Not in the manifest.** §4 admits machine-local facts and federation policy, and house
> style is neither. It belongs to the bundle, must travel with the repo, and must work when
> nobody knows the federation exists (§9.5). A manifest pointer would be a second home for
> something the bundle owns, drifting the moment the bundle is edited on another machine.

### 9.7 What we may assume is installed

`fkb` runs through `uv`, which is the one dependency the design already assumes. Whether
`fkb search` may additionally assume `ripgrep`, or must scan in pure Python, is open.

Pure Python keeps the dependency floor at `uv` alone and stays comfortably fast at the scale
of §9.1. Shipping `rg` as a conditional fast path reintroduces the machine-dependence §7
rejects, unless results are provably identical.

Largely an implementation question, recorded here because it bounds what §7 can promise.

### 9.8 Settled

- **Canonical OKF home** is `GoogleCloudPlatform/open-knowledge-format`. The
  `knowledge-catalog` path in the okf-skills header is stale; pin from the former.
- **Claude Code discovery** is not our problem — no Claude Code in use here. If it ever is,
  a `~/.claude/skills/fkb` symlink covers it.
- **Assets live beside their concept** (§5.2).
- **The floor declaration is a YAML file**, not the bundle-root `index.md` (§9.2).
- **`verified` is never required and never nulled** — absence is how OKF encodes
  unverified (§6.5).

---

## 10. The way forward

This section is the implementation plan. It assumes nothing from this repository except
this document — a fresh session should be able to start here.

### How to use it

**Answer an open question only when a task forces it.** Deciding early trades away the
information the work itself produces. Every task below therefore names two things: which
questions it must settle, and which it must leave alone even when the answer feels obvious.
Leaving one alone is not procrastination; it is refusing to guess when the next task will
know.

Tasks run in order. Each states what "done" means in terms someone else could check.

### Before starting

A fresh session needs four things, none of which live in this repository.

| What | Where | Why |
| --- | --- | --- |
| The OKF v0.2 spec | `GoogleCloudPlatform/open-knowledge-format` | Vendored verbatim (§8) |
| `okf-skills` at a pinned commit | `scaccogatto/okf-skills` | Source of the validator, template and spec copy (§8) |
| The publishing template | `~/Projects/public/running-linux` | MkDocs, prek, CI, Pages — reused, not rebuilt |
| The existing content | `~/.agents/wikis/{public,private}/docs` | ~60 concepts, ~100 transcripts |

Everything else — the manifest schema (§4), the AGENTS.md block (§5.4), the skill layout
(§6.2), the command set (§7) — is specified in this document.

One thing this repository *does* provide: `tests/fake_home.py` and `tests/conftest.py` build
an isolated HOME, install a pinned opencode, copy skill directories into `~/.agents/skills`
and drive `opencode run`, returning a parsed transcript. It survived the previous
architecture because it is independent of what it drives. Use it for T2's skill tests rather
than rebuilding it; `tests/test_harness.py` shows the shape.

---

### T1 — Prepare the bundle, empty

**Goal.** A conformant, publishing bundle that is ready to be written into, before any
content is migrated. Hours, not days — T2 is blocked on this and nothing else.

**Deliverable.** A git repo from the running-linux template, with the directory layout
fixed, the floor declaration written, publishing working, and a handful of concepts in it
as proof.

**Steps.**

- Copy the template: MkDocs, prek, CI, Pages.
- Fix the top-level directory layout, and decide how the `meta/` pages satisfy OKF §11
  (§9.4). Both are forced now, because everything written afterwards assumes them.
- Decide where markdown raw sources live (§9.3). The ~100 transcripts are the concrete
  case; deciding does not mean moving them yet.
- Write the floor declaration file (§9.2). Nothing reads it until T4.
- Write `index.md`, `log.md`, and three or four real concepts by hand.

**Done when.** `okf_validate.py --strict` passes, `mkdocs build --strict` passes, and the
site is live.

**Settles.** §9.2, §9.3, §9.4, and §9.6 for this bundle.

**Leave alone.** §9.1, §9.5, §9.7. Migrate no bulk content — that is T3.

---

### T2 — Minimum capture, and a friction journal

**Goal.** Agent sessions file knowledge from today, while still producing honest evidence
about which commands are worth building.

**The bargain.** Building before observing risks the journal recording friction with the
tooling rather than with the task. That risk attaches to the commands, not to the
instructions, so this task builds every part whose necessity is not in question and
deliberately withholds the rest.

| Build now | Withhold |
| --- | --- |
| The skill, scoped to *filing* (§6.3, §6.4) | Query and audit workflows |
| `fkb list` | `fkb search` (§9.1) |
| `fkb lint`, conformance and floor only | `fkb resolve`'s vocabulary reporting (§7) |
| The AGENTS.md block (§5.4) | Semantic lint (§6.5) |
| Vendored spec, template, validator (§8) | `fkb init`, `fkb add` |

Withholding `search` and `resolve` is the entire point: reaching for the web when the
bundle knew the answer, or picking a tag that fits nothing, are the observations that decide
whether those commands exist.

**Deliverable.** `~/.agents/skills/fkb/` per §6.2 but filing-only, the two commands, the
AGENTS.md block, and `JOURNAL.md` in this repository beside this document.

**The journal.** The skill instructs the agent to append to `JOURNAL.md` whenever the work
runs into a limit. Three rules keep it worth reading:

- **Record what happened, not what should be built.** "Searched the web for X; the bundle
  had it at `principles/y.md`" is evidence. "Search would be useful" is a wish, and wishes
  are free.
- **Record only concrete incidents, with the artifacts.** The actual query, the actual path,
  the actual tag chosen. An entry that names no file and no query did not happen.
- **Record what was done instead.** The workaround is the measurement. If there was no
  workaround, say the task was abandoned.

One line per incident, dated, so the file greps:

```markdown
- **2026-09-04** search — asked "do we pin actions by SHA"; web-searched; bundle had
  `principles/pin-github-actions-to-full-commit-shas.md`. Read the whole index to find it.
- **2026-09-05** tags — filed `ci` where the bundle uses `ci-cd`; noticed only at lint.
```

> Agents asked to report problems will invent plausible ones. The three rules exist to make
> a fabricated entry obviously empty: no path, no query, nothing done instead.

**Done when.** Filing works end to end from a cold session, and the journal has run for
seven days or accumulated enough entries to decide T4 without waiting.

**Settles.** Nothing formally. It supplies the evidence for §9.1 and for T4's scope.

**Leave alone.** Everything in the withhold column, however obvious it looks mid-week. The
whole value of this task is that the gaps stay open long enough to be measured.

---

### T3 — Migrate the ~60 public concepts

**Goal.** Move the existing content into the T1 bundle. Runs alongside T2's observation
window; capture does not wait for it.

**Steps.**

- Copy from `~/.agents/wikis/public/docs`. The published files are canonical; the `raw/`
  shadows carry nothing extra.
- Frontmatter: add `type:`; drop `sources: [raw/…]`, `render_hash` and `topic:` (the
  directory already carries the topic, §9.6).
- Convert `[[wikilinks]]` to relative markdown links using a filename-and-title map. Emit
  the unresolved ones as a list for manual review rather than guessing a target.
- Delete the `raw/` tree once the conversion validates.
- Move the transcripts wherever T1 decided (§9.3).

**Done when.** `okf_validate.py --strict` and `mkdocs build --strict` both pass, internal
links resolve, and the unresolved-link list is empty or consciously accepted.

**Leave alone.** The conversion script is disposable and never becomes part of `fkb`.

---

### T4 — Finish the CLI

**Goal.** Add the commands the journal justified, and nothing else.

**Specified by this document.** Manifest schema and resolution (§4), the reference rule
(§4), what `resolve` reports (§7), `lint`'s warning-versus-error behaviour (§6.6).

**Steps.**

- Read `JOURNAL.md` first. A command with no entries against it does not get built.
- Implement the federation checks in `lint`: the reference rule, cross-bundle links, and
  demotion to warnings for non-writable bundles (§6.6).
- Implement `search` if the journal earned it, in pure Python unless §9.7 says otherwise.
  Output must be bundle-qualified, and a published bundle's hits must render as URLs.
- Add `resolve`'s vocabulary reporting if the journal shows style mismatches (§7).
- Implement `fkb init` and `fkb add` with its three arrival paths (§7). Until now the
  workspace was hand-written; T7 introduces a second bundle and a real user, so setup stops
  being a one-off.

**Done when.** Every built command runs against the migrated bundle and at least one
read-only upstream, and the tests drive the installed copy rather than the source tree.

**Settles.** §9.7, and §9.1 to the extent the journal decided it.

---

### T5 — Finish the skill

**Goal.** Extend the filing-only skill of T2 into the full one, including onboarding.

**Steps.**

- Add the query workflow and the semantic lint checklist (§6.5).
- Add the "new here?" branch to `SKILL.md` and write `references/getting-started.md`
  (§6.7). Take the three arrival paths from the previous `README.md` before T7 deletes it.
- Add `references/house-style.md` and `references/federation.md`.
- Fold whatever the journal revealed about the filing instructions back into `SKILL.md`.

**Done when.** Three cold-session tests pass, each starting with no prior context:

1. Given a question, the agent finds the skill, reads a concept and cites it.
2. Given "note this down", it files a conformant concept that passes `fkb lint` uncorrected.
3. Given "what is this and how do I start?" on a machine with **no workspace configured**,
   it explains what a bundle is and gives a first command that runs (§6.7).

The third test is the one that fails quietly. A plausible summary of the design is not a
pass; a next step the person can run is.

**Leave alone.** §9.6 — the skill reads a bundle's style, it does not impose one.

---

### T6 — Ship the standalone pre-commit hook

**Goal.** A bundle enforces its own conformance and floor without `fkb` present.

**Deliverable.** This repository publishes a `pre-commit` hook that a bundle pins by
revision, wrapping the same checker `fkb lint` calls.

**Constraint.** One implementation, two entry points. If the hook and the skill's copy can
drift, the design has failed.

**Done when.** A bundle with no knowledge of the federation rejects a non-conformant commit,
and `fkb lint` reports the same finding on the same file.

**Settles.** §9.5.

---

### T7 — Second bundle, then retire the old architecture

**Goal.** Prove federation on more than one bundle, and remove what this design replaces.

**Steps.**

- Migrate the private bundle as in T1 and T3.
- Populate the manifest with both bundles plus at least one read-only upstream.
- Exercise the reference rule: confirm a private-to-public link is refused and a
  public-to-public link is allowed.
- Fold `JOURNAL.md` into a decisions record and delete it.
- Update `README.md` to describe what now exists rather than what is planned.

**Done when.** The repository contains this design, the CLI, the skill, the hook and their
tests, and nothing describing the previous architecture except Appendix A.

---

### Already done

- **The stale AGENTS.md block is removed** from `~/.config/opencode/AGENTS.md`
  (2026-09-02). Cold sessions currently get no wiki instructions at all, which is correct
  until T4 gives them something true to say.
- **The retired architecture is deleted** (2026-09-02): the six `fkb-*` skills,
  `manifest.py`, `install-glue`, the bundle commands and their tests. The last working
  state is preserved in git history, and what it cost is Appendix A. The e2e harness was
  kept.

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
