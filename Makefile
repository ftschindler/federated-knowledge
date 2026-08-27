.DEFAULT_GOAL := help

## Show available targets
help:
	@grep -B1 '^[a-z][a-z-]*:' $(MAKEFILE_LIST) \
		| grep -A1 '^##' \
		| awk '/^##/{d=substr($$0,4)} /^[a-z]/{split($$0,a,":"); printf "  %-12s %s\n", a[1], d}'

## Run all tests
test:
	node --test 'tests/**/*.test.mjs'

## Run the full pre-commit guard suite against all files
check:
	prek run --all-files

## Install pre-commit hooks (and git-lfs) into this clone
bootstrap:
	git lfs install --local
	prek install

.PHONY: help test check bootstrap
