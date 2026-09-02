# Minimal OKF bundle for `create-bundle`

`create-bundle` writes the smallest useful OKF v0.2 bundle: a directory with a
bundle-root `index.md` and `log.md`. These are reserved files, not ordinary
concept documents, so they do **not** need a `type` frontmatter key.

## Files written

`index.md`:

```markdown
---
okf_version: "0.2"
---
# <bundle name>

An OKF knowledge bundle.
```

`log.md`:

```markdown
# Log

## <YYYY-MM-DD>

* **Initialization**: Created bundle.
```

## Why this is conformant

OKF v0.2 treats `index.md` and `log.md` as reserved filenames. Reserved files
follow their own structure. The bundle-root `index.md` may carry `okf_version:
"0.2"`; `log.md` records date-grouped entries. The `type` requirement applies
to non-reserved concept documents, not to these two reserved files.

Richer scaffolds may add concepts, generated indexes, provenance, or house style.
They are useful, not required for conformance.
