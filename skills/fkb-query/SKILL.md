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

**THIS SKILL INSTRUCTS YOU TO EXECUTE A QUERY.** Do not just read these instructions and stop.
Follow the steps below to **actually perform** the query across all bundles in your federation.

Wraps [kb-query](../fkb/SKILL.md#route-to-the-right-skill). **Reading is unrestricted** across the
federation — the `referenceable_by` leak rule governs *authoring* cross-links, not reading. So query
fans out to every bundle; only writing is gated (see fkb-ingest).

## 1. Preflight (mandatory)

```bash
uv run "${XDG_CONFIG_HOME:-$HOME/.config}/federated-knowledge/manifest.py" check-deps kb-query
```

Exit 4 → STOP; the message names what is missing — surface this to the user and offer resolutions
(install `uv`, run `npx skills add stjbrown/agent-knowledge` for the kb skills),
never install anything unprompted!

Load the bundle set:

```bash
uv run "${XDG_CONFIG_HOME:-$HOME/.config}/federated-knowledge/manifest.py" list
```

## 2. Fan kb-query across bundles (EXECUTE, don't just read)

**CRITICAL**: This skill **instructs you to execute** the following steps. Do not just read these
instructions and stop. You must **actually perform** the query by following the steps below.

For **each** bundle in the manifest (writable or not — reading is allowed everywhere):

1. **Invoke the kb-query skill** for this bundle:

   ```text
   skill(name="kb-query", user_message="<the user's query>")
   ```

   This returns the kb-query instructions — **execute them** by:
   - Reading the bundle's `knowledge/index.md`
   - Navigating to relevant concepts via progressive disclosure
   - Reading the specific concept files that match the query
   - Synthesizing an answer with citations

2. **Collect the result**: Note which concepts were found and what they say.

**Example**: If the user asks "LLM wiki" and you have one bundle `stjbrown/agent-knowledge`:

- Call `skill(name="kb-query", user_message="LLM wiki")` → get instructions
- Read `~/.agents/knowledge/stjbrown/agent-knowledge/knowledge/index.md`
- Find the link to `concepts/llm_wiki.md`
- Read that file and synthesize the answer

## 3. Merge and rank

Combine the per-bundle answers into one response:

- De-duplicate overlapping facts; prefer the most-specific / most-recently-updated source.
- Note genuine conflicts between bundles rather than silently picking one.
- If different tiers disagree, surface both and label by bundle.

## 4. Cite bundle-qualified

Every citation must name **which bundle** it came from, so tier is always visible:

- Published bundle → its `publish` URL + concept path (no `docs/` segment — MkDocs strips it).
- Unpublished bundle → `bundle:concept/path.md`, e.g. `private:decisions/pricing.md`.

Use `manifest.py resolve <bundle>` to get the `publish` base and `resolved_path` when formatting a
URL citation.

## Must not

- Do not write anything. fkb-query is read-only unless the user explicitly asks to file the answer
  back — in which case hand off to **fkb-ingest** (which re-applies classification + gates), never
  write directly.
- Do not hide which bundle a fact came from — bundle-qualified citation is mandatory.
- **Do not skip executing the kb-query skill instructions** — the whole point of this skill is to
  instruct you to fan out to kb-query for each bundle and **actually execute** those instructions.
