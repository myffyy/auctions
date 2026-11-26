# ЛР6. Доставка в staging

## Подготовка

Цель — учебная VM `app-server` (ARM64), Compose-проект `auctions-lr6`. Интерфейс приложения слушает `127.0.0.1:18060`, PostgreSQL доступен только в сети проекта. С Mac открыть интерфейс можно через административный SSH-туннель.

### Подготовка VM

На VM выделенная учётная запись `auctions-deploy` запускает собственный [Docker Engine в режиме rootless](https://docs.docker.com/engine/security/rootless/). У неё нет доступа к системному сокету Docker. Для daemon нужны `uidmap`, диапазоны в `/etc/subuid` и `/etc/subgid`, пользовательский systemd с `loginctl enable-linger auctions-deploy` и сетевые зависимости rootless Docker. Для команд приёмки нужны Bash, Python 3, Docker Compose, `flock`, `nsenter`, `curl` и `socat`. Системный Docker, который обслуживает ЛР4, следует оставить запущенным. Установку rootless Docker рядом с системным Docker выполняют с `--force` по инструкции Docker.

В `/home/auctions-deploy/staging` положить `compose.yml` из `deploy/compose.yml`, отдельный `staging.env` и `smoke.json` с логином и паролем тестового покупателя и идентификатором контрольного лота. В `registry-auth/config.json` хранится авторизация Docker для `127.0.0.1:15001`. Каталог принадлежит `auctions-deploy`, права каталога 0700, файлов с секретами 0600. Значения `staging.env` можно взять из существующего staging, если переносится его БД.

Для ключа Jenkins в `authorized_keys` использовать опции `restrict,port-forwarding`. В разделе `Match User auctions-deploy` задать `AuthenticationMethods publickey`, `AllowTcpForwarding no`, `AllowStreamLocalForwarding remote`, `PermitTTY no`, `X11Forwarding no` и `AllowAgentForwarding no`. При переходе убрать старый принудительный `command=` из ключа и прежнее разрешение sudo для обработчика доставки. Проверить `sshd -t` и перезагрузить конфигурацию SSH. Jenkins передаёт команды Bash в stdin своей SSH-сессии. Он открывает временный Unix-сокет до registry, а TCP-ретранслятор на `127.0.0.1:15001` работает только внутри сетевого пространства rootless daemon.

При переходе со старого staging сохраните логический дамп БД. После остановки только проекта `auctions-lr6` на старом daemon запустите PostgreSQL в rootless-проекте и восстановите дамп. Так сохранятся тестовый покупатель и контрольный лот из `smoke.json`. Скопировать `accepted` можно после проверки сохранённой базы и доступности обоих образов из registry. Старый том PostgreSQL оставьте до проверки новой трассы. Ниже автоматический выпуск и ручной откат идут через Jenkins.

## Выпуск и проверки

После публикации Jenkins вызывает staging по SSH. Команды настройки Docker, развёртывания и HTTP-приёмки определены непосредственно в `Jenkinsfile`. Digest и результат HTTP-приёмки доступны в артефактах выпуска Jenkins. На VM файл `accepted` содержит текущую и предыдущую принятые версии. Файл `attempted` обозначает незавершённую приёмку после начала применения кандидата.

Для защиты использовать временные изменения конфигурации только в staging:

| Проверка | Действие и ожидаемый этап отказа |
| --- | --- |
| Неверный тег | Передать отсутствующий SHA из 40 hex-символов. Ошибка на этапе pull. |
| Отсутствующая настройка | Временно убрать `SESSION_SECRET` из `staging.env`. Ошибка на этапе configuration. |
| Недоступный registry | Сделать registry недоступным во время учебного прогона Jenkins. Ошибка на этапе pull. |
| Неуспешный healthcheck | Временно изменить команду Docker healthcheck приложения на завершающуюся с ошибкой. Этап apply завершается с ошибкой. |
| Сбой пользовательского сценария | Временно подставить неверный пароль покупателя в `smoke.json`. Контейнеры, HTTP health и версия проходят, этап http завершается с ошибкой. |
| Возврат | Восстановить staging-конфигурацию и выполнить rollback. Приёмка должна подтвердить прежние SHA, digest и контрольный лот. |
| Две операции | Во время первой операции вызвать вторую серверную команду через отдельный сеанс. Вторая останавливается на этапе lock. |

После теста записать наблюдаемый результат, SHA, digest и ссылки на Issue, PR и CI.


## CD в Jenkins

`Jenkinsfile` используется как заданием PR, так и отдельным заданием выпуска. Выпуск выполняется на отдельном контроллере с собственным хранилищем credentials и inbound-агентом на Mac. Учётные данные registry и SSH находятся только на контроллере выпуска. PR продолжают выполняться на контроллере CI на порту 8081.

1. Поднимите контроллер выпуска командой `docker compose -f ci/compose.cd.yml up -d --build`. В [Jenkins CD](http://127.0.0.1:8082/) завершите первичную настройку, создайте администратора и установите для встроенного узла 0 исполнителей.
2. Создайте постоянный inbound-узел с меткой `auctions-release`, одним исполнителем и рабочим каталогом на Mac, доступным только владельцу. Запустите команду подключения из Jenkins с WebSocket в пользовательской сессии Mac. Передайте секрет агента из файла с режимом 0600 через `-secret @/path/to/secret`, используйте Java 21 или 25 и включите в PATH Git, Docker, uv, Make и клиентские команды PostgreSQL. Проверьте, что Docker Desktop и registry на `127.0.0.1:5001` доступны агенту.
3. Только в Jenkins CD создайте credentials `auctions-ci-postgres-password`, `auctions-ci-session-secret`, `auctions-ci-admin-password` (тестовые значения для отдельного контейнерного цикла) и `auctions-release-registry-password` (пароль пользователя `ci`). Добавьте Secret file `auctions-release-ssh-key` с закрытым ключом `auctions-deploy` и Secret file `auctions-release-known-hosts` с проверенным ключом хоста VM.
4. Создайте обычный Pipeline с именем `auctions-staging-release`. Definition → Pipeline script from SCM, Git URL `https://github.com/myffyy/auctions.git`, Branch Specifier `*/main`, Script Path `Jenkinsfile`. Включите Poll SCM с расписанием `H/5 * * * *`. Ограничьте право Configure заданием администратора контроллера выпуска.
5. В окно переключения дождитесь окончания активного выпуска и остановите старый монитор командой `launchctl bootout "gui/$(id -u)" "$HOME/Library/LaunchAgents/com.auctions.lr5.release.plist"`. Переместите plist из `~/Library/LaunchAgents` в закрытый каталог, чтобы монитор не вернулся после входа в систему. Запустите первое задание Jenkins и проверьте стадии публикации и приёмки. Если переключение не прошло, отключите опрос в Jenkins и восстановите plist перед запуском прежнего монитора.

Для запуска конкретного SHA используйте **Build with Parameters → deploy** и заполните `RELEASE_TAG`. Для отката выберите **rollback**. Плановые запуски используют **publish**. В Console Output видны результат публикации, вывод VM и строка `Accepted`; `reports/publish.log`, `reports/published-digest.txt` и `reports/staging.log` доступны в артефактах. Стадия держит общую блокировку VM до окончания приёмки в рамках одного SSH-вызова.
