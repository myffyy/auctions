#!/usr/bin/env bash
set -euo pipefail

COMPOSE="docker compose"
fail() { echo "FAIL: $*" >&2; exit 1; }
ok()   { echo "OK:   $*"; }

DBUSER="${POSTGRES_USER:-auctions}"
DBNAME="${POSTGRES_DB:-auctions}"

echo "== 1. Сборка образа (воспроизводимость) =="
$COMPOSE build
ok "образ собран"

echo "== 2. Запуск окружения =="
$COMPOSE up -d

echo "== 3. Ожидание healthcheck приложения =="
status=""
for i in $(seq 1 30); do
  status=$($COMPOSE ps --format '{{.Health}}' app 2>/dev/null || true)
  [ "$status" = "healthy" ] && break
  sleep 2
done
[ "$status" = "healthy" ] || fail "приложение не стало healthy"
ok "приложение healthy"

echo "== 4. Процесс приложения не от root (пункт 3) =="
proc_user=$($COMPOSE exec -T app id -un)
[ "$proc_user" != "root" ] || fail "приложение запущено от root"
ok "пользователь процесса: $proc_user"

echo "== 5. Порт БД наружу не опубликован (пункт 8) =="
if $COMPOSE port db 5432 2>/dev/null | grep -Eq ':[1-9]'; then
  fail "порт БД опубликован наружу"
fi
ok "порт БД закрыт снаружи"

echo "== 6. Запись контрольных данных =="
$COMPOSE exec -T app python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3)"
marker="container-check-$(date +%s)"
$COMPOSE exec -T db psql -U "$DBUSER" -d "$DBNAME" \
  -c "CREATE TABLE IF NOT EXISTS container_check(note text); INSERT INTO container_check VALUES ('$marker');"
ok "данные записаны: $marker"

echo "== 7. Пересоздание контейнеров — данные должны выжить (пункт 9) =="
$COMPOSE up -d --force-recreate
sleep 5
found=$($COMPOSE exec -T db psql -U "$DBUSER" -d "$DBNAME" \
  -tAc "SELECT count(*) FROM container_check WHERE note='$marker';")
[ "$found" = "1" ] || fail "данные не сохранились после пересоздания"
ok "данные сохранились после пересоздания"

echo "== 8. Корректное завершение контейнера (пункт 5) =="
start=$(date +%s)
$COMPOSE stop -t 20 app
elapsed=$(( $(date +%s) - start ))
[ "$elapsed" -lt 20 ] || fail "контейнер не завершился за отведённое время (возможно, SIGKILL)"
ok "приложение завершилось штатно за ${elapsed}s"
$COMPOSE up -d app
sleep 5

echo "== 9. Бэкап и восстановление в контейнере (пункт 10) =="
created=$($COMPOSE exec -T app sh -c 'PYTHONPATH=src python scripts/backup.py create')
backup_file=$(printf '%s\n' "$created" | sed -n 's/^Резервная копия создана: //p')
[ -n "$backup_file" ] || fail "не удалось создать бэкап: $created"
$COMPOSE exec -T db psql -U "$DBUSER" -d "$DBNAME" \
  -c "DELETE FROM container_check WHERE note='$marker';"
$COMPOSE exec -T app sh -c "PYTHONPATH=src python scripts/backup.py restore --file '$backup_file'"
restored=$($COMPOSE exec -T db psql -U "$DBUSER" -d "$DBNAME" \
  -tAc "SELECT count(*) FROM container_check WHERE note='$marker';")
[ "$restored" = "1" ] || fail "данные не восстановились из бэкапа"
ok "бэкап/восстановление работают"

echo
echo "===== CONTAINER-CHECK ПРОЙДЕН ====="
