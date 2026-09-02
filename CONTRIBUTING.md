# Contributing

## Local Dev Environment

### Prerequisites

We require

- [uv](https://docs.astral.sh/uv/),
- [Node.js](https://nodejs.org),

and optionally [make](https://en.wikipedia.org/wiki/Make_(software)).

> Using make is actually an optional convenience.
> If not available: look up the raw uv or node calls in the [Makefile](Makefile)

### Clone and bootstrap

```bash
git clone https://github.com/ftschindler/federated-knowledge.git
cd federated-knowledge
make bootstrap
```

### Using the development version of the skills globally

This repo ships no skills yet (see [DESIGN.md](DESIGN.md)). Once it does, symlink them into
the location every harness reads:

```bash
mkdir -p ~/.agents/skills && \
for ii in $(cd skills && ls -d *); do ln -s "${PWD}/skills/${ii}" ~/.agents/skills/; done
```

> Remove previously installed copies from the target location beforehand.

### Running the tests

Two layers, both run by:

```bash
make test
```

#### Support scripts

Fast and deterministic, no network:

```bash
make test_python_scripts
```

#### The end-to-end harness

Slower and non-deterministic, because it drives a real agent:

```bash
make test_skills
```

These tests

- prepare a [throwaway agent environment](#a-throwaway-agent-environment),
- invoke `opencode` with instructions (the non-deterministic part),
- assert deterministically on the returned transcript and the created files.

While the repo has no skills of its own, this layer installs a canary skill authored by the
test and checks that an agent discovers and follows it. That keeps every moving part of the
harness exercised: the opencode install, the permission grant, skill discovery, activation
and transcript parsing.

#### A throwaway agent environment

The harness

- creates a fake `HOME` with all `XDG_*` redirected into it,
- installs a pinned `opencode` (an agent harness plus free access to its default model),
- copies skill directories from a given source into `~/.agents/skills`.

Build one by hand and drop into a shell inside it:

```bash
make fakehome                          # this repo's skills, if any
.scripts/fake-home.py --skills DIR     # skills from elsewhere
.scripts/fake-home.py --no-skills      # opencode only
```

On a test failure the fake home is preserved and the command to enter it is printed.

### Before you push

Run the full pre-commit guard suite against every file (the same hooks that run on commit):

```bash
uvx prek run --all-files
```
