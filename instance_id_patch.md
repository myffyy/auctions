# Доп. задание, пункт 5 — идентификатор экземпляра в ответе

Добавьте middleware в `src/auctions/main.py` (после создания `app`), чтобы
каждый ответ нёс заголовок с именем контейнера-реплики. Docker подставляет
в переменную окружения HOSTNAME идентификатор контейнера, поэтому код
менять под каждый экземпляр не нужно.

```python
import os

...


@app.middleware("http")
async def add_instance_header(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Instance"] = os.getenv("HOSTNAME", "unknown")
    return response
```

Проверка балансировки после запуска накладки с nginx:

```bash
for i in $(seq 1 6); do curl -s -D - -o /dev/null http://localhost:8080/health | grep -i x-instance; done
```

В выводе должны чередоваться два разных идентификатора экземпляров.
