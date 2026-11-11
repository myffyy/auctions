# syntax=docker/dockerfile:1.7.0@sha256:dbbd5e059e8a07ff7ea6233b213b36aa516b4c53c645f1817a4dd18b83cbea56

############################
# Сборка окружения (uv)
############################
FROM postgres:14-alpine@sha256:b084304744d27cbc34513a1d2916129bd6a33383fa17b79b9a9030a950f14870 AS pgclient
FROM python:3.12-alpine@sha256:e064671ca452259bab50e8e2c7bd896e39e9a343bb06ca25234adf6fe18d0fc7 AS base

# uv фиксированной версии (пункт 2 — воспроизводимая сборка)
COPY --from=ghcr.io/astral-sh/uv:0.10.7@sha256:edd1fd89f3e5b005814cc8f777610445d7b7e3ed05361f9ddfae67bebfe8456a /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0 \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Клиент PostgreSQL 14 и совместимая библиотека libpq в Alpine.
RUN apk add --no-cache libpq=18.6-r0
COPY --from=pgclient /usr/local/bin/pg_dump /usr/local/bin/pg_dump
COPY --from=pgclient /usr/local/bin/pg_restore /usr/local/bin/pg_restore

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
RUN addgroup -g 10001 -S appuser \
    && adduser -S -D -H -u 10001 -G appuser appuser \
    && chown -R appuser:appuser /app

USER appuser

# venv в PATH; слушаем все интерфейсы контейнера
ENV PATH="/app/.venv/bin:$PATH" \
    APP_HOST=0.0.0.0 \
    APP_PORT=8000

ARG RELEASE_REVISION=development

LABEL org.opencontainers.image.revision=$RELEASE_REVISION

EXPOSE 8000

# Compose выполняет миграции отдельно; exec запускает CMD как PID 1 (пункт 5)
ENTRYPOINT ["/app/docker/entrypoint.sh"]

CMD ["uvicorn", "auctions.main:app", "--app-dir", "src", "--host", "0.0.0.0", "--port", "8000"]
