# OKF v0.2 reference (local excerpt)

This is the local reference the fkb skills use for conformance decisions. Source:
<https://github.com/GoogleCloudPlatform/open-knowledge-format/blob/main/SPEC.md>

## Bundle structure

An OKF bundle is a directory tree of markdown files. It may be distributed as a
git repository, a tarball/zip archive, or a subdirectory within a larger repository.

Reserved filenames have defined meaning at any level and are **not** ordinary
concept documents:

| Filename | Meaning |
| --- | --- |
| `index.md` | Directory listing / progressive disclosure |
| `log.md` | Chronological update history |

All other `.md` files are concept documents.

## Concept documents

Every non-reserved concept document is UTF-8 markdown with:

1. a YAML frontmatter block at the top, delimited by `---`, and
2. a markdown body.

Only one frontmatter key is always required:

```yaml
---
type: <Type name>
---
```

`title`, `description`, `resource`, `tags`, provenance, trust, lifecycle, and
attestation fields are optional. Consumers must tolerate unknown types and extra
frontmatter keys.

## Index files

`index.md` may appear in any directory. It lists directory contents. It normally
has **no frontmatter**. The bundle-root `index.md` is the one exception: it may
carry `okf_version: "0.2"` in frontmatter.

## Log files

`log.md` may appear in any directory. It records update history as date-grouped
markdown entries, newest first. Date headings use ISO `YYYY-MM-DD` form.

## Conformance summary

A bundle conforms to OKF v0.2 if:

1. every non-reserved `.md` file has parseable YAML frontmatter;
2. every such frontmatter block has a non-empty `type` field;
3. reserved `index.md` and `log.md` files follow their reserved-file structure.

Missing optional fields, unknown types, unknown extra frontmatter keys, broken
cross-links, and missing index files do not make a bundle non-conformant.
