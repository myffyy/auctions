# syntax=docker/dockerfile:1

############################
# Сборка окружения (uv)
############################
FROM python:3.12.5-slim-bookworm AS base

# uv фиксированной версии (пункт 2 — воспроизводимая сборка)
COPY --from=ghcr.io/astral-sh/uv:0.10.7 /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0 \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Клиент PostgreSQL 14 для pg_dump/pg_restore (пункт 10: бэкап/восстановление в контейнере)
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates gnupg \
    && install -d /usr/share/postgresql-common/pgdg \
    && curl -o /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc \
         https://www.postgresql.org/media/keys/ACCC4CF8.asc \
    && echo "deb [signed-by=/usr/share/postgresql-common/pgdg/apt.postgresql.org.asc] \
         http://apt.postgresql.org/pub/repos/apt bookworm-pgdg main" \
         > /etc/apt/sources.list.d/pgdg.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends postgresql-client-14 \
    && apt-get purge -y --auto-remove gnupg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 1) Сначала только зависимости — слой кэшируется, пока не изменились lock-файлы
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-install-project --no-dev

# 2) Затем исходный код приложения
COPY . /app
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

# entrypoint ждёт БД и накатывает миграции; CMD запускается как PID 1 через exec (пункт 5)
ENTRYPOINT ["/app/docker/entrypoint.sh"]
CMD ["uvicorn", "auctions.main:app", "--app-dir", "src", "--host", "0.0.0.0", "--port", "8000"]
