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

Simply symlink to these skills with:

```bash
for ii in $(cd skills && ls -d *); do ln -s "${PWD}/skills/${ii}" "~/.agents/skills/${ii}"; done
```

> Ensure to remove previously installed skills from the target location beforehand.

### Running the tests

This repo contains agents skills, scripts the skills invoke, and dev tooling around that.
We provide tests for each, run all available ones with:

```bash
make test
```

We can also run individual test layers.

#### testing node scripts

Running the node tests is fast and deterministic:

```bash
make test_node_scripts
```

#### testing python scripts

Running the Python tests is fast and deterministic as well:

```bash
make test_python_scripts
```

#### testing the skills

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

### Before you push

Run the full pre-commit guard suite against every file (the same hooks that run on commit):

```bash
uvx prek run --all-files
```
