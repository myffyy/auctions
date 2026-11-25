# ЛР6. Доставка в staging

## Подготовка

Цель — учебная VM `app-server` (ARM64), Compose-проект `auctions-lr6`. Интерфейс приложения слушает `127.0.0.1:18060`, PostgreSQL доступен только в сети проекта. С Mac открыть интерфейс можно через административный SSH-туннель.

Администратор устанавливает `deploy/compose.yml`, `deploy/staging.sh`, `deploy/smoke.py` и `deploy/ssh-command.sh` в `/opt/auctions-lr6` с владельцем root. Каталог и код доступны на запись только root. Использовать содержимое проверенного коммита. Для `staging.env` взять за основу `.env.docker.example`, задать отдельные значения пароля PostgreSQL, пароля администратора и секрета сессии. Пароль PostgreSQL должен быть безопасен для подстановки в URL. Файлы с настройками и Docker credentials доступны только root.

Учётной записи `auctions-deploy` выдаётся отдельный ключ, без доступа к Docker и без интерактивного входа. В `authorized_keys` задать `restrict,port-forwarding,permitlisten="127.0.0.1:15001",command="/opt/auctions-lr6/ssh-command.sh"`. В конфигурации sshd для этой учётной записи разрешить только remote TCP forwarding и адрес `127.0.0.1:15001`; проверить конфигурацию через `sshd -t` до перезагрузки. В отдельном файле sudoers, проверенном `visudo`, разрешить `auctions-deploy ALL=(root) NOPASSWD: /opt/auctions-lr6/staging.sh`. Forced command принимает только строго проверенные `deploy` и `rollback`.

В доверенном каталоге монитора ЛР5 создать `ci/.secrets/staging-ssh.conf` с правами 0600:

```sshconfig
Host auctions-staging
    HostName 192.168.64.24
    User auctions-deploy
    IdentityFile /absolute/path/to/staging-key
    UserKnownHostsFile /absolute/path/to/staging-known-hosts
    IdentitiesOnly yes
    StrictHostKeyChecking yes
    BatchMode yes
    ExitOnForwardFailure yes
    RemoteForward 127.0.0.1:15001 127.0.0.1:5001
```

Закрепить проверенный ключ VM. При открытом туннеле выполнить на VM от root `docker --config /opt/auctions-lr6/registry-auth login 127.0.0.1:15001 --password-stdin --username ci`, передав пароль из защищённого файла через stdin. Registry ЛР5 использует htpasswd с доступом на уровне сервиса.

Первичное заполнение выполнить от администратора staging. Через открытый туннель скачать проверенный образ, выставить `APP_IMAGE` на ссылку по digest и из `/opt/auctions-lr6` выполнить `docker compose --env-file staging.env up -d --no-build --wait`. Через интерфейс создать аукцион, доступный лот и отдельную учётную запись покупателя. Записать её логин, пароль и числовой идентификатор контрольного лота в root-only `smoke.json` с полями `username`, `password` и `lot_id`. Затем выполнить штатный deploy того же SHA для первой записи приёмки. После проверки настроек заменить доверенную копию `trusted-release.sh` обновлённым скриптом из одобренного коммита.

## Выпуск и проверки

После публикации main процесс ЛР5 вызывает staging по SSH. Digest и результат HTTP-приёмки сохраняются в `reports/releases/<sha>/` доверенного процесса. На VM файл `accepted` содержит две строки с текущей и предыдущей принятыми версиями. Файл `attempted` обозначает незавершённую приёмку после начала применения кандидата.

Ручные операции выполняются с доверенного Mac:

```bash
ssh -F "$STAGING_SSH_CONFIG" auctions-staging "deploy $SHA"
ssh -F "$STAGING_SSH_CONFIG" auctions-staging rollback
```

Для защиты использовать временные изменения конфигурации только в staging:

| Проверка | Действие и ожидаемый этап отказа |
| --- | --- |
| Неверный тег | Передать отсутствующий SHA из 40 hex-символов. Ошибка на этапе pull. |
| Отсутствующая настройка | Временно убрать `SESSION_SECRET` из `staging.env`. Ошибка на этапе configuration. |
| Недоступный registry | Запустить команду через административный доступ на VM при закрытом туннеле. Ошибка на этапе pull. |
| Неуспешный healthcheck | Временно изменить команду Docker healthcheck приложения на завершающуюся с ошибкой. Этап apply завершается с ошибкой. |
| Сбой пользовательского сценария | Временно подставить неверный пароль покупателя в `smoke.json`. Контейнеры, HTTP health и версия проходят, этап http завершается с ошибкой. |
| Возврат | Восстановить staging-конфигурацию и выполнить rollback. Приёмка должна подтвердить прежние SHA, digest и контрольный лот. |
| Две операции | Во время первой операции вызвать вторую серверную команду через отдельный сеанс. Вторая останавливается на этапе lock. |

После теста записать наблюдаемый результат, SHA, digest и ссылки на Issue, PR и CI.
