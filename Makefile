.PHONY: setup test-setup run test test-unit test-mutations quality sast format migrate check-migrations verify

setup:
	uv sync --locked
	PYTHONPATH=src:. uv run --locked python scripts/setup.py

run:
	uv run --locked uvicorn auctions.main:app --app-dir src \
		--host "$${APP_HOST:-127.0.0.1}" \
		--port "$${APP_PORT:-8000}" \
		--reload

test-setup:
	uv sync --locked
	PYTHONPATH=src:. uv run --locked python scripts/setup.py --test

test: test-setup
	uv run --locked pytest --cov=auctions --cov-branch \
		--cov-report=term-missing --cov-report=xml:reports/coverage.xml \
		--cov-report=html:reports/htmlcov --junitxml=reports/tests.xml

test-unit:
	uv run --locked pytest tests/test_sales_unit.py tests/test_schemas.py \
		tests/test_test_configuration.py tests/test_health.py --junitxml=reports/unit-tests.xml

test-mutations:
	uv run --locked python scripts/check_mutations.py

migrate:
	uv run --locked alembic upgrade head

check-migrations: test-setup
	PYTHONPATH=src:. uv run --locked python scripts/check_migrations.py

quality:
	uv lock --check
	uv run --locked ruff format --check .
	uv run --locked ruff check .

sast:
	mkdir -p reports
	uv run --locked bandit -r src scripts migrations tests/configuration.py --severity-level all \
		--confidence-level all -f json -o reports/sast.json
	uv run --locked python scripts/check_sast_report.py

format:
	uv run --locked ruff format .
	uv run --locked ruff check . --fix

verify: quality sast test test-mutations check-migrations
