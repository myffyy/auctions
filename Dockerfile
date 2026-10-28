# syntax=docker/dockerfile:1.7.0@sha256:dbbd5e059e8a07ff7ea6233b213b36aa516b4c53c645f1817a4dd18b83cbea56

############################
# Сборка окружения (uv)
############################
FROM postgres:14-bookworm@sha256:a389ed49344afc8f4444efd4eb512965df07aaa6ed84b239b54a23246e9fe347 AS pgclient

FROM python:3.12.5-slim-bookworm@sha256:c24c34b502635f1f7c4e99dc09a2cbd85d480b7dcfd077198c6b5af138906390 AS base

# uv фиксированной версии (пункт 2 — воспроизводимая сборка)
COPY --from=ghcr.io/astral-sh/uv:0.10.7@sha256:edd1fd89f3e5b005814cc8f777610445d7b7e3ed05361f9ddfae67bebfe8456a /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0 \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Неизменяемый снимок Debian фиксирует также транзитивные APT-зависимости.
RUN rm /etc/apt/sources.list.d/debian.sources \
    && echo "deb [check-valid-until=no] https://snapshot.debian.org/archive/debian/20241001T000000Z bookworm main" > /etc/apt/sources.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Клиент той же основной версии, что и БД; никаких изменяемых PGDG-репозиториев.
COPY --from=pgclient /usr/lib/postgresql/14/bin/pg_dump /usr/local/bin/pg_dump
COPY --from=pgclient /usr/lib/postgresql/14/bin/pg_restore /usr/local/bin/pg_restore

WORKDIR /app

# 1) Сначала только зависимости — слой кэшируется, пока не изменились lock-файлы
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-install-project --no-dev

# 2) Затем исходный код приложения
COPY src /app/src
COPY migrations /app/migrations
COPY docker/entrypoint.sh /app/docker/entrypoint.sh
COPY scripts/backup.py /app/scripts/backup.py
COPY alembic.ini pyproject.toml uv.lock /app/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev

# Непривилегированный пользователь (пункт 3)
RUN useradd --create-home --uid 10001 appuser \
    && chown -R appuser:appuser /app
USER appuser

# venv в PATH; слушаем все интерфейсы контейнера
ENV PATH="/app/.venv/bin:$PATH" \
    APP_HOST=0.0.0.0 \
    APP_PORT=8000

EXPOSE 8000

# Compose выполняет миграции отдельно; exec запускает CMD как PID 1 (пункт 5)
ENTRYPOINT ["/app/docker/entrypoint.sh"]
CMD ["uvicorn", "auctions.main:app", "--app-dir", "src", "--host", "0.0.0.0", "--port", "8000"]
