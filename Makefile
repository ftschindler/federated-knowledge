.DEFAULT_GOAL := help

## Show available targets
help:
	@grep -B1 '^[a-z][a-z_-]*:' $(MAKEFILE_LIST) \
		| grep -A1 '^##' \
		| awk '/^##/{d=substr($$0,4)} /^[a-z]/{split($$0,a,":"); printf "  %-20s %s\n", a[1], d}'

## Run all tests (node scripts, python scripts, and skills e2e)
test: test_node_scripts test_python_scripts test_skills

## Test the node scripts under skills/ (fast, deterministic)
test_node_scripts:
	node --test 'tests/**/*.test.mjs'

## Test the python support scripts under .scripts/ (fast, deterministic)
test_python_scripts:
	uvx --with pytest pytest -m python_scripts

## Test the skills end-to-end by driving opencode in a fake home (slow, needs network)
test_skills:
	uvx --with pytest pytest -m skills

## Run the full pre-commit guard suite against all files
check:
	prek run --all-files

## Install pre-commit hooks (and git-lfs) into this clone
bootstrap:
	git lfs install --local
	prek install

.PHONY: help test test_node_scripts test_python_scripts test_skills check bootstrap
