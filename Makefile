# File: Makefile
# Description: One command per task, used the same way by humans, AI
#     agents, and CI. Targets that need Docker, the database, or campaigns
#     are added when those pieces exist (see docs/roadmap.md §5.3).
# Author(s): Tyler Black

PYTHON ?= python3
LINT_PATHS = src tests scripts

.PHONY: setup lint fmt test coverage check dev up down db runner migrate seed validate-campaigns fill-expected

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

## Start Postgres db container for local testing if not running in CI.
db:
	@if [ "$$CI" != "true" ]; then \
		docker compose up -d --wait db; \
	fi

## Build and start the sandbox runner container (also in CI: the
## hostile-code suite in tests/runner/ runs against it).
runner:
	docker compose up -d --build --wait runner

## Run database migrations up to head revision.
migrate:
	$(PYTHON) -m alembic upgrade head

## All tests, Selenium included. LLM_MODE is forced to fake.
test: db runner
	LLM_MODE=fake $(PYTHON) -m pytest

## Tests under coverage; fails under 90%. HTML report in htmlcov/.
## (The leading "-" keeps going if html trips fail_under, so the report
## below still prints the missing lines before failing.)
coverage: db runner
	LLM_MODE=fake $(PYTHON) -m coverage run -m pytest
	-$(PYTHON) -m coverage html
	$(PYTHON) -m coverage report

## Seed validated campaigns into the database.
seed: db
	$(PYTHON) scripts/seed.py

## Validate all seed campaign JSON files.
validate-campaigns:
	$(PYTHON) scripts/validate_campaigns.py

## Fill expected_output in a campaign JSON file using its reference solution.
fill-expected:
	@if [ -z "$(FILE)" ]; then \
		echo "Usage: make fill-expected FILE=path/to/campaign.json"; \
		exit 1; \
	fi
	$(PYTHON) scripts/fill_expected.py $(FILE)

## What CI runs: lint, campaign validation, and coverage.
check: lint validate-campaigns coverage

## Flask with auto-reload on http://localhost:8001.
dev:
	$(PYTHON) -m flask --app src.app:create_dev_app run --debug --port 8001

## Start web, db, and runner containers with Docker Compose.
up:
	docker compose up --build

## Stop running Docker Compose containers.
down:
	docker compose down
