.PHONY: setup run test quality format verify

setup:
	uv sync --python 3.12

run:
	uv run uvicorn auctions.main:app --app-dir src \
		--host "$${APP_HOST:-127.0.0.1}" \
		--port "$${APP_PORT:-8000}" \
		--reload

test:
	uv run pytest

quality:
	uv run ruff format --check .
	uv run ruff check .

format:
	uv run ruff format .
	uv run ruff check . --fix

verify: quality test
