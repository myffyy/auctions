# Лабораторная работа №4

## Ресурсы и пользователи

Окружение рассчитано на учебную Linux VM с 1 ГБ RAM и небольшой нагрузкой.

| Сервис | UID:GID | CPU | Память | Обоснование |
| --- | --- | --- | --- | --- |
| db | 70:70 | 0,5 | 256 МБ | PostgreSQL: shared_buffers=64MB, max_connections=40, без публикации порта |
| migrate | 10001:10001 | 0,5 | 256 МБ | Один процесс Alembic; завершается до запуска реплик |
| app, базовый режим | 10001:10001 | 0,5 | 256 МБ | Один процесс Uvicorn, запросы к PostgreSQL |
| app, каждая из двух реплик | 10001:10001 | 0,5 | 192 МБ | Две реплики делят нагрузку; суммарно до 384 МБ |
| nginx | 101:101 | 0,25 | 64 МБ | Один worker; проксирование и rate limit |

В режиме Nginx сумма ограничений долгоживущих сервисов — 704 МБ; остаётся память для Linux, Docker и служебных процессов. Миграции завершаются до старта приложений. Лимиты — верхние границы, а не резервирование памяти; при росте нагрузки их нужно менять по измерениям.

У каждого долгоживущего сервиса есть healthcheck. У однократного migrate результат проверяется по коду завершения через service_completed_successfully; healthcheck для завершившегося процесса не применяется.

Nginx слушает непривилегированный порт 8080 внутри контейнера и публикует 8090 (NGINX_PORT). PID и временные файлы размещены в /tmp, журналы направлены в stdout/stderr. Порты реплик при подключении docker-compose.nginx.yml удаляются через !reset; требуется Compose 2.24.4 или новее.

## Автоматические запреты

make container-check сначала проверяет нормализованный JSON базовой конфигурации и варианта Nginx. Запрещены latest, отсутствие digest у внешних образов, root, отключение healthcheck у долгоживущих сервисов, лишние порты, host network, privileged и отсутствие лимитов. Проверяется ожидание единственного сервиса миграций и наличие двух реплик за Nginx.

Dockerfile копирует только перечисленные входные пути; .dockerignore по умолчанию исключает всё. Проверка слоёв docker image save ищет текущие POSTGRES_PASSWORD, SESSION_SECRET и ADMIN_PASSWORD, включая файлы, удалённые поздними слоями. Она не заменяет поиск неизвестных секретов: пользовательские секреты следует хранить вне исходников и передавать только через окружение. Значения не выводятся и не передаются в argv.

## Подготовка и запуск на Linux VM

Проверенная конфигурация app-server: Debian 12, aarch64, 1 ГБ RAM, Docker 20.10.24, Compose 2.36.2, Buildx 0.24.0, make 4.3. На хосте нужен Python 3.10+; Python приложения 3.12.5 находится в образе. Для !override нужен Compose 2.24.4+ ([правила объединения Compose](https://docs.docker.com/reference/compose-file/merge/)).

В корне репозитория создайте .env из .env.docker.example и заполните три пустых секрета. Пример генерирует их без вывода и сохраняет существующий .env:

```bash
python3 - <<'PY'
from pathlib import Path
import secrets

path = Path(".env")
if not path.exists():
    text = Path(".env.docker.example").read_text()
    for name in ("POSTGRES_PASSWORD", "SESSION_SECRET", "ADMIN_PASSWORD"):
        text = text.replace(f"{name}=\n", f"{name}={secrets.token_hex(24)}\n")
    with path.open("x") as output:
        path.chmod(0o600)
        output.write(text)
PY
make container-check
```

Если .env уже существует, добавьте в него недостающие значения вручную. Используйте URL-безопасный пароль PostgreSQL (генератор выше выдаёт hex): DATABASE_URL собирается Compose из имени роли, пароля и имени БД. Не коммитьте .env. Не меняйте POSTGRES_PASSWORD существующего volume только правкой .env: пароль роли хранится в PostgreSQL.

Базовый вариант (одна реплика, прямой порт APP_PORT):

```bash
make up
```

Вариант дополнительного задания (Nginx и две реплики):

```bash
# Функция используется в командах ниже.
dc() { docker compose -f docker-compose.yml -f docker-compose.nginx.yml "$@"; }
dc up -d --build --wait
dc ps
curl -fsS http://127.0.0.1:8090/health
```

На VM ЛР2 порт 8000 занят прежним systemd-приложением: для базового контейнерного варианта в отдельном .env задан APP_PORT=18000. Вариант Nginx использует 8090 и не публикует APP_PORT. Системное приложение и PostgreSQL на db-server не заменяются.

Если firewall VM не разрешает 8090, можно открыть туннель с Mac без изменения firewall:

```bash
ssh -i ~/.ssh/devops_lr2 -L 18090:127.0.0.1:8090 admin@192.168.64.24
```

После этого веб-интерфейс доступен на http://127.0.0.1:18090. Пароль контейнерного администратора находится в ADMIN_PASSWORD отдельного .env на app-server; пароль администратора ЛР2 не меняется.

## Что выполняет container-check

Команда использует отдельные проекты auctions-check-<uuid> и auctions-check-<uuid>-restore. Она не перезапускает рабочее окружение и не восстанавливает архив поверх рабочей БД. Порт Nginx теста выбирается Docker автоматически на 127.0.0.1. Проекты, их volume и тестовые образы удаляются при завершении, в том числе при ошибке.

| Этап | Доказательство |
| --- | --- |
| policy-and-image | Проверены обе конфигурации, входные пути и слои образа |
| migrations-and-runtime | Миграции выполнены единственным сервисом; alembic check не нашёл расхождений; проверены фактические UID, healthcheck, лимиты и порты |
| recreate-with-data | Полная строка sellers, включая дату создания, сохранена после force-recreate |
| image-update-with-data | Собран другой артефакт образа с изменённым RELEASE_REVISION; ID изменился, обе реплики используют новый ID, строка сохранена |
| restore-into-new-volume | До восстановления новая БД пуста; имена volume различаются; восстановлены строка и версия Alembic |
| graceful-shutdown | Каждая реплика завершилась с кодом 0, без OOM; журнал содержит Application shutdown complete |
| two-instances-and-failover | Запросы дошли до двух X-Instance; после остановки одного экземпляра 20 запросов подряд обслужил оставшийся |

JSON-отчёт: reports/container-check.json. RELEASE_REVISION меняет метаданные артефакта, не бизнес-логику приложения. Это проверяет переход на другой образ с сохранением volume. Состав зависимостей фиксируют digest внешних образов, снимок Debian 20241001T000000Z и uv.lock. Побайтовая идентичность слоёв не заявляется.

## Команды для защиты

Запускать на app-server из каталога репозитория, после определения функции dc выше.

Пользователь процесса и распределение запросов:

```bash
dc exec -T app id
dc exec -T db id
dc exec -T nginx id
for i in $(seq 1 12); do
  curl -fsS -D - -o /dev/null http://127.0.0.1:8090/health | grep -i x-instance
done
```

Ожидаются ненулевые UID и два разных идентификатора. По порядку они могут повторяться: распределение не обязано строго чередовать реплики.

Сохранность при пересоздании и обновлении:

```bash
dc exec -T db psql -U auctions -d auctions -c "INSERT INTO sellers(name) VALUES ('defense-demo');"
dc up -d --force-recreate --wait
dc exec -T db psql -U auctions -d auctions -c "SELECT * FROM sellers WHERE name='defense-demo';"
dc build --build-arg RELEASE_REVISION=defense-update
dc up -d --wait
dc exec -T db psql -U auctions -d auctions -c "SELECT * FROM sellers WHERE name='defense-demo';"
```

При изменённых POSTGRES_USER/POSTGRES_DB замените auctions в аргументах psql. Обычный dc down сохраняет volume; dc down -v удаляет данные и для рабочего окружения не нужен.

Резервное копирование и восстановление в новый volume:

```bash
LR4_BACKUP_NAME="defense-$(date +%Y%m%dT%H%M%S).dump"
mkdir -p -m 700 backups
chmod 700 backups
dc exec -T -e PYTHONPATH=src app python scripts/backup.py create --file "/app/backups/$LR4_BACKUP_NAME"
dc cp --index 1 "app:/app/backups/$LR4_BACKUP_NAME" "backups/$LR4_BACKUP_NAME"
chmod 644 "backups/$LR4_BACKUP_NAME"
# Каталог backups закрыт от других пользователей; файл читается процессом контейнера через bind mount.
dr() { docker compose -p auctions-restore-demo -f docker-compose.yml "$@"; }
dr up -d --wait db
dr exec -T db psql -U auctions -d auctions -c "SELECT count(*) FROM pg_tables WHERE schemaname='public';"
dr run --rm --no-deps -T -e PYTHONPATH=src \
  --volume "$PWD/backups/$LR4_BACKUP_NAME:/restore.dump:ro" \
  app python scripts/backup.py restore --file /restore.dump
dr exec -T db psql -U auctions -d auctions -c "SELECT * FROM sellers WHERE name='defense-demo';"
dr exec -T db psql -U auctions -d auctions -c 'SELECT * FROM alembic_version;'
# Удаляется только демонстрационная копия, после проверки преподавателем:
dr down -v
```

Для повторной демонстрации сначала завершите предыдущий auctions-restore-demo: проверка пустоты должна показать 0 таблиц. Автоматический container-check всегда создаёт уникальный новый volume и сравнивает его имя с исходным.

Остановка реплики и доступность:

```bash
LR4_REPLICA=$(dc ps -q app | head -n 1)
docker stop -t 20 "$LR4_REPLICA"
docker inspect --format '{{.State.ExitCode}} {{.State.OOMKilled}}' "$LR4_REPLICA"
docker logs "$LR4_REPLICA" 2>&1 | tail -n 8
curl -fsS -D - http://127.0.0.1:8090/health
docker start "$LR4_REPLICA"
dc up -d --wait
```

Ожидаются 0 false, сообщение штатного shutdown и HTTP 200 от другой реплики. Nginx использует Docker DNS, повтор запроса при error/timeout/502/503/504 и ограничение частоты 20 запросов/с с burst=40. Проверка отказа относится к HTTP-доступности; она не доказывает отказоустойчивость БД.

## Ограничения горизонтального масштабирования

- PostgreSQL и Nginx остаются одиночными узлами. Две реплики приложения не обеспечивают доступность при отказе БД, прокси или самой VM.
- Все реплики должны использовать одну БД и одинаковый SESSION_SECRET. SessionMiddleware хранит подписанную сессию в cookie клиента, поэтому привязка к одной реплике не нужна; разные секреты нарушат вход при переключении.
- Администратор создаётся лениво в /auth/login. Два одновременных первых входа в пустую БД могут конфликтовать при создании учётной записи. Перед нагрузочной демонстрацией выполните один вход; дальнейшее улучшение — однократная идемпотентная инициализация вне HTTP-запроса.
- У каждого процесса SQLAlchemy собственный пул (по умолчанию 5 соединений и до 10 overflow). Две реплики могут использовать до 30 соединений при max_connections=40. Дальнейшее увеличение числа реплик требует пересчёта пулов и лимитов БД.
- Продажи одного лота сериализуются блокировкой строки PostgreSQL. Добавление реплик не ускорит конкурирующие операции над одним лотом.
- Резервные копии, созданные внутри контейнера, локальны конкретной реплике и теряются при её пересоздании. Копируйте архивы наружу до пересоздания. Исходники и статика входят в образ; обновлять следует все реплики одной версией.

## Результаты и порядок принятия изменений

28.10.2026 на app-server Debian 12/aarch64 выполнены сборка и все семь этапов container-check. Снимок отчёта: [lab4-validation.json](lab4-validation.json). Полный make verify: 169 тестов, покрытие 90,10%, Ruff, SAST, три контрольные мутации, миграции и восстановление.

Дополнительно успешно выполнен [GitHub Actions на Ubuntu Linux VM для PR #37](https://github.com/myffyy/auctions/actions/runs/40692140165). Workflow запускается на каждом PR и push в main, публикует JSON и журнал. В защите main включены обязательный PR, успешный container-check, актуальность ветки и применение правила к администраторам; ручное одобрение другого пользователя не требуется.

Каждое исправление оформлено отдельной веткой, проверено, закоммичено, отправлено и слито до следующей задачи: [миграции #32](https://github.com/myffyy/auctions/pull/32), [воспроизводимость #33](https://github.com/myffyy/auctions/pull/33), [пользователи и ресурсы #34](https://github.com/myffyy/auctions/pull/34), [политика #35](https://github.com/myffyy/auctions/pull/35), [контейнерный цикл #36](https://github.com/myffyy/auctions/pull/36), [CI #37](https://github.com/myffyy/auctions/pull/37). Журнал действий и причин: [lab4-work-log.md](lab4-work-log.md).

Изменение digest, снимка APT, лимитов, портов, healthcheck или скрипта проверки проходит тем же путём. Снижение требований для получения зелёного результата не допускается. При обновлении зависимостей меняйте закреплённые входы осознанно и повторяйте проверки.
