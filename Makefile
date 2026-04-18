VIRTUAL_ENV_PATH=venv
SKIP_VENV="${NO_VENV}"
SHELL := /bin/bash
PYTHON := python3.12
SRC_ROOT := ./src
ROOT_PACKAGE := unikit
.DEFAULT_GOAL := pre_commit
POETRY := poetry

FORMAT_PATH := $(SRC_ROOT)
LINT_PATH := $(SRC_ROOT)
MYPY_PATH := $(SRC_ROOT)

POETRY_GROUPS := dev

pre_commit: pre_commit_hook lint

UNAME_S := $(shell uname -s)

ifeq ($(UNAME_S),Darwin)
    SED_COMMAND := gsed
else
    SED_COMMAND := sed
endif

define activate_venv
  if [ -z $(SKIP_VENV) ]; then source $(VIRTUAL_ENV_PATH)/bin/activate; fi;
endef

pre_commit_hook:
	@( \
		$(call activate_venv) \
		pre-commit run --all --hook-stage=commit; \
	)

verify-prerequisites:
	@(development/ensure-dependencies.sh)

setup: verify-prerequisites venv deps
	@( \
		$(call activate_venv) \
		pre-commit install; \
		echo "Pre-commit hooks installed"; \
		echo "DONE: setup"; \
	)

deps:
	@( \
		set -e; \
		$(call activate_venv) \
		$(POETRY) install --all-extras --no-root --with "$(POETRY_GROUPS)"; \
	)

.PHONY: deps-lock
deps-lock:
	@( \
		$(call activate_venv) \
		echo "Locking dependencies..."; \
		$(POETRY) lock; \
		echo "DONE: all dependencies are locked"; \
	)

# Synchronize installed dependencies to match the lock file
.PHONY: deps-sync
deps-sync:
	@( \
		$(call activate_venv) \
		set -e; \
		echo "Syncing dependencies..."; \
		$(POETRY) sync --all-extras --no-root --with "$(POETRY_GROUPS)"; \
		echo "DONE: all dependencies are synchronized"; \
	)

# Update a specific dependency
.PHONY: deps-update-dep
deps-update-dep:
	@( \
		$(call activate_venv) \
		set -e; \
		echo "Updating dependency $(DEPENDENCY)..."; \
		$(POETRY) update $(DEPENDENCY) --with "$(POETRY_GROUPS)"; \
		echo "DONE: dependency $(DEPENDENCY) is updated"; \
	)

# Update all dependencies
.PHONY: deps-update-all
deps-update-all:
	@( \
		$(call activate_venv) \
		echo "Updating dependencies..."; \
		$(POETRY) update --with "$(POETRY_GROUPS)"; \
		echo "DONE: all dependencies are updated"; \
	)

# Show dependencies tree
.PHONY: deps-tree
deps-tree:
	@( \
		$(call activate_venv) \
		echo "Showing dependencies tree..."; \
		$(POETRY) show --tree --with "$(POETRY_GROUPS)"; \
	)

.PHONY: venv
venv:
	@( \
	  	set -e; \
		  $(PYTHON) -m venv $(VIRTUAL_ENV_PATH); \
		  source ./venv/bin/activate; \
	)

copyright:
	@( \
       $(call activate_venv) \
       echo "Applying copyright..."; \
       for p in $(FORMAT_PATH); do \
       	 licenseheaders -t ./development/copyright.tmpl -E ".py" -cy -d $$p; \
       done; \
       echo "DONE: copyright"; \
    )

.PHONY: ruff-fix-pyupgrade
ruff-fix-pyupgrade:
	@( \
	   $(call activate_venv) \
       echo "Applying pyupgrade..."; \
       ruff check --select UP --fix; \
       echo "DONE: pyupgrade"; \
    )

.PHONY: ruff-fix-pyupgrade-unsafe
ruff-fix-pyupgrade-unsafe:
	@( \
	   $(call activate_venv) \
	   echo "Applying pyupgrade..."; \
	   ruff check --select UP --fix --unsafe-fixes; \
	   echo "DONE: pyupgrade"; \
	)

ruff-format:
	@( \
	   $(call activate_venv) \
	   echo "Running Ruff code formatter..."; \
	   ruff format $(FORMAT_PATH); \
	   echo "DONE: Ruff"; \
	)

ruff-format-check:
	@( \
	   $(call activate_venv) \
	   echo "Running Ruff format check..."; \
	   ruff format --diff $(FORMAT_PATH) || exit 1; \
	   echo "DONE: Ruff"; \
	)

ruff-import-sort:
	@( \
	   $(call activate_venv) \
	   echo "Running Ruff import sort..."; \
	   ruff check --select I --fix; \
	   echo "DONE: Ruff"; \
	)

ruff-import-sort-check:
	@( \
	   $(call activate_venv) \
	   echo "Running Ruff import sort..."; \
	   ruff check --select I || exit 1; \
	   echo "DONE: Ruff"; \
	)

ruff-lint:
	@( \
	   $(call activate_venv) \
	   echo "Running Ruff link..."; \
	   ruff check $(LINT_PATH) || exit 1; \
	   echo "DONE: Ruff"; \
	)


format: ruff-import-sort ruff-format
check-format: ruff-import-sort-check ruff-format-check

mypy:
	@( \
	set -e; \
	$(call activate_venv) \
    echo "Running MyPy checks..."; \
    mypy $(MYPY_PATH); \
    echo "DONE: MyPy"; \
	)

.PHONY: lint
lint: check-format ruff-lint mypy

build:
	@( \
		echo "Building packages"; \
		set -e; \
		$(call activate_venv) \
		rm -rf dist/*; \
		poetry build; \
		echo "DONE: Building packages"; \
	)

dev-containers:
	@( \
		echo "Starting docker containers"; \
		docker-compose -f docker-compose.yaml up -d; \
		echo "DONE: Docker containers started"; \
	)

publish: build
	@( \
		echo "Publishing packages"; \
		set -e; \
		$(call activate_venv) \
		poetry publish; \
		echo "DONE: Publishing packages"; \
	)

coverage:
	@( \
		echo "Running coverage"; \
		set -e; \
		$(call activate_venv) \
		coverage run --source $(SRC_ROOT)/$(ROOT_PACKAGE) -m pytest; \
		coverage html; \
		echo "DONE: Coverage"; \
	)

test:
	@( \
		echo "Running tests"; \
		set -e; \
		$(call activate_venv) \
		echo pytest -v --cov-report term-missing --cov=$(SRC_ROOT)/$(ROOT_PACKAGE); \
		pytest -v; \
		echo "DONE: Tests"; \
	)

changelog:
	@( \
		echo "Generating changelog"; \
		set -e; \
		$(call activate_venv) \
		cz changelog --incremental; \
		echo "DONE: Changelog"; \
	)

print-changelog:
	@( \
		$(call activate_venv) \
		cz changelog --dry-run --incremental; \
	)

release:
	@( \
		echo "Preparing release"; \
		set -e; \
		$(call activate_venv) \
		cz bump --changelog; \
		echo "DONE: Preparing release"; \
	)

print-version:
	@( \
		$(call activate_venv) \
		cz version --project; \
	)
