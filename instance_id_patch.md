# Идентификатор экземпляра приложения

Middleware X-Instance уже реализован в src/auctions/main.py. Заголовок содержит HOSTNAME контейнера; за Nginx запросы доходят до двух реплик.

После запуска docker-compose.nginx.yml проверьте порт 8090:

```bash
for i in $(seq 1 12); do
  curl -fsS -D - -o /dev/null http://127.0.0.1:8090/health | grep -i x-instance
done
```

Ожидаются два разных идентификатора. Полная проверка балансировки и доступности после остановки экземпляра выполняется через make container-check. Команды для защиты приведены в [документации ЛР4](docs/lab4.md).
