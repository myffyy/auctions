.PHONY: setup test-setup run test test-unit test-mutations quality sast format migrate check-migrations backup restore check-backup verify up down logs container-check docker-linter

export BACKUP_FILE

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
		tests/test_test_configuration.py tests/test_health.py tests/test_backup_commands.py \
		--junitxml=reports/unit-tests.xml

test-mutations:
	uv run --locked python scripts/check_mutations.py

migrate:
	uv run --locked alembic upgrade head

check-migrations: test-setup
	PYTHONPATH=src:. uv run --locked python scripts/check_migrations.py

backup:
	PYTHONPATH=src:. uv run --locked python scripts/backup.py create

restore:
	PYTHONPATH=src:. uv run --locked python scripts/backup.py restore

check-backup: test-setup
	PYTHONPATH=src:. uv run --locked python scripts/check_backup.py

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

verify: quality sast test test-mutations check-migrations check-backup

up:
	docker compose up -d --build

down:
	docker compose down

logs:
	docker compose logs -f

container-check:
	bash scripts/container_check.sh

# Автоматические исправления Tally и последующая проверка Hadolint.
docker-linter:
	uv run --locked tally lint --fix --fix-unsafe --ignore tally/labels/no-buildx-git-overlap --ignore tally/prefer-copy-heredoc --fail-level error Dockerfile
	docker run --rm -i hadolint/hadolint:v2.12.0 < Dockerfile

# Проверки CI не изменяют исходные файлы и возвращают ненулевой код при ошибке.
.PHONY: docker-lint-check secrets-check dependencies-check image-check

docker-lint-check:
	uv run --locked tally lint --ignore tally/labels/no-buildx-git-overlap --ignore tally/prefer-copy-heredoc --fail-level error Dockerfile
	docker run --rm -i hadolint/hadolint:v2.12.0 < Dockerfile

dependencies-check:
	mkdir -p reports
	docker run --rm -v "$(CURDIR):/src:ro" -v "$(CURDIR)/reports:/reports" -v auctions-trivy-cache:/root/.cache/ aquasec/trivy:0.60.0 fs --scanners vuln --include-dev-deps --severity HIGH,CRITICAL --exit-code 1 --format json --output /reports/dependencies.json /src/uv.lock

image-check:
	@test -n "$(IMAGE)" || (echo 'Set IMAGE to the image to scan' >&2; exit 2)
	mkdir -p reports
	docker run --rm -v /var/run/docker.sock:/var/run/docker.sock -v "$(CURDIR)/reports:/reports" -v auctions-trivy-cache:/root/.cache/ aquasec/trivy:0.60.0 image --scanners vuln --severity HIGH,CRITICAL --exit-code 1 --format json --output /reports/image.json "$(IMAGE)"

secrets-check:
	python3 scripts/check_secrets.py
