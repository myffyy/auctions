.PHONY: setup run test quality format migrate verify

setup:
	uv sync --locked
	PYTHONPATH=src uv run --locked python scripts/setup.py

run:
	uv run --locked uvicorn auctions.main:app --app-dir src \
		--host "$${APP_HOST:-127.0.0.1}" \
		--port "$${APP_PORT:-8000}" \
		--reload

test:
	uv run --locked pytest

migrate:
	uv run --locked alembic upgrade head

quality:
	uv lock --check
	uv run --locked ruff format --check .
	uv run --locked ruff check .

format:
	uv run --locked ruff format .
	uv run --locked ruff check . --fix

verify: quality test
