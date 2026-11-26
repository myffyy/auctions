# ЛР5: локальная CI-инфраструктура

`python3 ci/init_registry.py`, затем `docker compose -f ci/compose.yml up -d --build` запускает Jenkins на `127.0.0.1:8081` и учебный registry на `127.0.0.1:5001`. Данные хранятся в отдельных именованных volumes. Jenkins при первом запуске требует завершить мастер и создать администратора; начальный пароль можно получить командой `docker exec auctions-lr5-ci-jenkins-1 cat /var/jenkins_home/secrets/initialAdminPassword`. Не размещайте пароль в Git и отчётах. Установку выполните с использованием уже включённых в образ плагинов.

Образ агента содержит Python 3.12.5, uv 0.10.7, Docker CLI/Compose, Make и клиент PostgreSQL. Профиль `agent` поднимает отдельный Docker daemon; агент подключается к Jenkins через WebSocket. В Jenkins нужно создать inbound-узел `auctions-ci` с меткой `auctions-ci` и каталогом `/home/jenkins/agent`, получить его секрет в настройках узла и передать через защищённую переменную `JENKINS_AGENT_SECRET` при запуске `docker compose -f ci/compose.yml --profile agent up -d --build`. Секрет не должен попадать в Git, вывод команд или отчёты. Для реальных недоверенных PR необходим отдельный одноразовый агент и изолированный Docker daemon для каждой сборки: общий агент сохраняет состояние между заданиями.


Перед запуском этапа «Контейнер» добавьте в Jenkins три записи типа **Secret text**, доступные заданию auctions. Используйте отдельные значения для тестового окружения.

| ID в Jenkins | Переменная Docker Compose |
| --- | --- |
| `auctions-ci-postgres-password` | `POSTGRES_PASSWORD` |
| `auctions-ci-session-secret` | `SESSION_SECRET` |
| `auctions-ci-admin-password` | `ADMIN_PASSWORD` |

Пароль PostgreSQL должен состоять из символов, безопасных для URL, поскольку Compose подставляет его напрямую в `DATABASE_URL`. Jenkins передаёт эти значения только на этапе «Контейнер».

В Jenkinsfile предусмотрены отдельная PostgreSQL на случайном локальном порту, `make quality`, тесты и контрольные мутации, миграции, backup, SAST, Gitleaks, анализ lock-файла, контейнерный цикл, сборка и сканирование образа. Для локального запуска новых проверок: `make docker-lint-check`, `make secrets-check`, `make dependencies-check`, `make image-check IMAGE=имя:тег`. Для сканеров необходимы Docker и доступ к базам уязвимостей. Отчёты находятся в `reports/`; значения секретов в отчёте Gitleaks редактируются.

## Оставшиеся условия внедрения

Текущая конфигурация **не является обязательным барьером**: локальный Jenkins недоступен из интернета для webhook, передача результатов Jenkins требует запуска сервиса status-relay с отдельным ограниченным токеном GitHub, а CODEOWNERS начнёт действовать после включения файла в основную ветку. Registry требует отдельный пароль из `ci/.secrets/registry-password` и ограничен loopback. Для публикации нужен доверенный отдельный агент. Секреты из `ci/.secrets/` не добавляются в Git. Не предоставляйте публикационные credentials заданиям PR: изменяемый Jenkinsfile может их раскрыть.

Jenkins обнаруживает изменения при периодическом опросе (интервал — пять минут), а не через webhook. Защита `main` требует статус `ci/jenkins-pr`, существующий `container-check` и независимое одобрение; права записи `nast2007` проверены. После включения CODEOWNERS в `main` действует требование согласования владельца кода.

## Доверенный выпуск в Jenkins

Выпуск из `main` выполняет отдельное задание с этапами CD в корневом `Jenkinsfile`. Настройка и переключение описаны в [ЛР6](../docs/lab6.md#cd-в-jenkins).

## Статус PR в GitHub

Сервис `status-relay` запускается отдельно от агента, не подключается к его Docker daemon и получает только локальные credentials Jenkins и ограниченный токен GitHub. Он проверяет открытые PR раз в минуту, сравнивает SHA последней сборки с текущим SHA PR и отправляет контекст `ci/jenkins-pr`: успешным может стать только завершённый успешный запуск того же SHA; отсутствующая, ещё выполняющаяся или несовпадающая сборка остаётся в состоянии pending, неуспешная — failure.

Credentials хранятся в исключённом из Git файле `ci/.secrets/status.env` с правами 0600. Для сервиса необходим GitHub fine-grained token только для `auctions` с Contents и Pull requests: read, Commit statuses: read/write; Jenkins API token должен иметь право читать задания и сборки. Запуск: `docker compose --env-file ci/.secrets/status.env -f ci/compose.yml --profile status up -d --build status-relay`. Не выдавайте GitHub token агенту сборок. После проверки поступления контекста в GitHub добавьте его к обязательным проверкам, сохранив существующий `container-check`.

## Защита статуса после первого слияния

GitHub позволяет владельцу токена публиковать контекст `ci/jenkins-pr`, но такой статус не привязан к отдельному GitHub App. Workflow `.github/workflows/jenkins-gate.yml` работает на `pull_request_target` из защищённой основной ветки, не запускает код PR и принимает статус для SHA запроса только от `myffyy`. В репозитории уже включён обязательный `jenkins-gate` с источником GitHub Actions. Сохраняйте его при изменениях защиты ветки. До этого момента один контекст `ci/jenkins-pr` не защищён от подмены другим участником с правом писать статусы.
