# Contributing

This repo is a set of agent skills plus the dev tooling and tests that guard them. The `fkb-*`
skills are plain files; the tests exercise the deterministic `manifest.mjs` core, the Python support
scripts under `.scripts/`, and the skills end-to-end by driving a real `opencode` in an isolated fake
home.

## System requirements

We require [uv](https://docs.astral.sh/uv/) and [Node.js](https://nodejs.org),
and optionally [make](https://en.wikipedia.org/wiki/Make_(software)).

> make is actually an optional convenience.
> If not available, look up the rax uv or npm calls in the [Makefile](Makefile)

## Clone and bootstrap

```bash
git clone https://github.com/ftschindler/federated-knowledge.git
cd federated-knowledge
make bootstrap
```

## Running the tests

Run all available tests with:

```bash
make test
```

We can also run individual test layers.

### testing node scripts

Running the node tests is fast and deterministic:

```bash
make test_node_scripts
```

### testing python scripts

Running the Python tests is fast and deterministic as well:

```bash
make test_python_scripts
```

### testing the skills

Testing the skills themselves is slower and not deterministic:

```bash
make test_skills
```

As we can only test the skills by letting them being carried out by an agent, these tests are move involved:

- they prepare a [throwaway agent environment](#a-throwaway-agent-environment)
- invoke `opncode` with instructions involving the skills (the non-deterministic part)
- carry out deterministic tests on the returned output and the created files

#### a throwaway agent environment

The tests

- create a fake `HOME` environment,
- install a pinned `opencode` into it (as that gives us an agent harness and free access to it's default LLM),
- install the `fkb*` skills and (depending on the test) the required (`kb*`) skills

which can be manually done as well:

```bash
make fakehome
```

## Before you push

Run the full pre-commit guard suite against every file (the same hooks that run on commit):

```bash
uvx prek run --all-files
```
