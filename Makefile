# File: Makefile
# Description: One command per task, used the same way by humans, AI
#     agents, and CI. Targets that need Docker, the database, or campaigns
#     are added when those pieces exist (see docs/roadmap.md §5.3).
# Author(s): Tyler Black

PYTHON ?= python3
LINT_PATHS = src tests scripts

.PHONY: setup lint fmt test coverage check dev

## Install pinned dependencies.
setup:
	$(PYTHON) -m pip install -r requirements.txt

## Ruff lint + format check, pycodestyle, and the header check.
lint:
	$(PYTHON) -m ruff check $(LINT_PATHS)
	$(PYTHON) -m ruff format --check $(LINT_PATHS)
	$(PYTHON) -m pycodestyle --max-line-length=79 --ignore=E203,W503 \
		$(LINT_PATHS)
	$(PYTHON) scripts/check_headers.py

## Auto-format and apply safe lint fixes.
fmt:
	$(PYTHON) -m ruff format $(LINT_PATHS)
	$(PYTHON) -m ruff check --fix $(LINT_PATHS)

## All tests, Selenium included. LLM_MODE is forced to fake.
test:
	LLM_MODE=fake $(PYTHON) -m pytest

## Tests under coverage; fails under 90%. HTML report in htmlcov/.
## (The leading "-" keeps going if html trips fail_under, so the report
## below still prints the missing lines before failing.)
coverage:
	LLM_MODE=fake $(PYTHON) -m coverage run -m pytest
	-$(PYTHON) -m coverage html
	$(PYTHON) -m coverage report

## What CI runs. Add validate-campaigns here once the validator exists.
check: lint coverage

## Flask with auto-reload on http://localhost:8000.
dev:
	$(PYTHON) -m flask --app src.app run --debug --port 8000
