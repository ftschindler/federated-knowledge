---
name: fkb-ingest
description: >-
  Capture a source into the correct privacy tier of a federated OKF workspace. Use when the user
  wants to ingest, capture, file, or "add this" — a note, transcript, PDF, web page, or any raw
  source — into a multi-bundle workspace.okf.yaml federation, and the right bundle must be chosen by
  sensitivity. Classifies the target (fail-closed to the most-private bundle), gates disclosure, then
  delegates the write to kb-ingest.
version: 0.1.0
tags: [knowledge, okf, federation, fkb, ingest, capture]
---

# fkb-ingest — classify, gate, delegate

**THIS SKILL INSTRUCTS YOU TO EXECUTE AN INGEST.** Do not just read these instructions and stop.
Follow the steps below to classify the source, gate disclosure, then **actually delegate** to kb-ingest.

Wraps [kb-ingest](../fkb/SKILL.md#route-to-the-right-skill). fkb-ingest owns **which bundle** and
**whether allowed**; `kb-ingest` owns the actual capture and integration into that one bundle.

## 1. Preflight (mandatory)

```bash
uv run "${XDG_CONFIG_HOME:-$HOME/.config}/federated-knowledge/manifest.py" check-deps kb-ingest
```

Exit 4 → STOP; the message names what is missing — install `uv`, or run
`npx skills add stjbrown/agent-knowledge` for the kb skills. **Never hand-roll the ingest** — that
bypasses OKF conformance and the trust model.

Load the bundle set:

```bash
uv run "${XDG_CONFIG_HOME:-$HOME/.config}/federated-knowledge/manifest.py" list
```

## 2. Classify the target bundle — FAIL CLOSED

Read the source, then decide which bundle it belongs to by **sensitivity**:

- Names an internal system, client, employer specific, codename, or unpublished detail → the
  matching **sealed / most-private** bundle.
- Generic, already-public, employer-neutral knowledge → a public bundle (only if one is `writable`).

**When in doubt, classify to the most-private writable bundle.** A wrongly-private capture is merely
less reuse; a wrongly-public one is irreversible disclosure (git history keeps it forever). This is
*why* the default is sealed.

## 3. Gate before writing

Two checks, both must pass:

1. **Writable gate.** The target must be `writable: true` (`manifest.py resolve <target>`). Use the
   returned `resolved_path` for filesystem work. A read-only upstream is a source, never a write
   target.
2. **Disclosure gate.** If your classification places the source into a bundle **more open** than the
   sealed default (e.g. anything with `referenceable_by: "*"` or a published `publish` URL), this is
   irreversible disclosure → **require explicit human sign-off** before proceeding. State plainly:
   "This will be captured into `<bundle>`, which is published at `<url>` / referenceable by anyone.
   Confirm?"

## 4. Resolve cross-links

If the new concept references another bundle B, enforce the leak rule first:

```bash
uv run "${XDG_CONFIG_HOME:-$HOME/.config}/federated-knowledge/manifest.py" can-reference <target> <B>   # exit 0 allow / 1 deny
```

Deny → do not write that link. Allow → emit the link as B's published URL if B has `publish`, else a
workspace-relative path (never a raw local absolute path). For a read-only upstream target, also
record the reference as an OKF `sources[]` provenance entry (its `publish` URL + a `last_modified`
signal), so provenance survives a broken live link.

## 5. Hand off to kb-ingest (EXECUTE, don't just read)

**CRITICAL**: This skill **instructs you to execute** kb-ingest. Do not just read these instructions
and stop. You must **actually invoke** the kb-ingest skill:

```text
skill(name="kb-ingest", user_message="<describe the source and target>")
```

Then **execute the kb-ingest instructions** it returns — it will:

- Create the concept file in the target bundle
- Update that bundle's `index.md` and `log.md`
- Ensure OKF conformance

fkb writes nothing in the bundle itself — kb-ingest owns all bundle mutations.

## 6. Report

State the chosen bundle, why, whether a disclosure gate fired, and the concept path kb-ingest wrote.

## Must not

- Never write into a non-`writable` bundle.
- Never place into a more-open bundle without human sign-off.
- Never emit a cross-link that `can-reference` denies.
- Never author bundle content directly — always invoke and execute kb-ingest.
- **Do not skip executing kb-ingest** — the whole point of this skill is to classify and gate, then
  **actually delegate** the write to kb-ingest.
