#!/bin/sh
# Точка входа контейнера приложения.
# БД уже помечена healthy через depends_on в compose, поэтому просто
# накатываем миграции и передаём управление основному процессу (uvicorn)
# через exec — чтобы он стал PID 1 и корректно принимал SIGTERM (пункт 5).
set -e

echo "[entrypoint] applying migrations (alembic upgrade head)..."
alembic upgrade head

echo "[entrypoint] starting: $*"
exec "$@"
