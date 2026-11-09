"""Проверить контейнерный цикл в отдельных временных Compose-проектах."""

import json
import os
import platform
import shutil

# Только доверенный Docker CLI без shell; секреты не передаются в argv.
import subprocess  # nosec B404
import tempfile
import urllib.request
from pathlib import Path
from uuid import uuid4

from scripts.check_container_image import check_image
from scripts.container_policy import PolicyError, require, validate_compose, validate_sources

ROOT = Path(__file__).resolve().parents[1]
DOCKER = shutil.which("docker")


# Запускает команду и возвращает её вывод, проверяя код завершения.
def run(
    arguments: list[str], env: dict | None = None, check: bool = True, include_stderr: bool = False
) -> str:
    # Исполняется Docker CLI, найденный через shutil.which, shell=False.
    result = subprocess.run(arguments, env=env, capture_output=True, text=True)  # nosec B603
    if check and result.returncode:
        raise PolicyError(f"Команда не выполнена: {' '.join(arguments)}\n{result.stderr[-3000:]}")
    return (result.stdout + (result.stderr if include_stderr else "")).strip()


class Environment:
    """Изолированное пространство имён контейнеров, сети и volume."""

    # Настраивает имя проекта, окружение и список Compose-файлов.
    def __init__(self, name: str, env: dict, extra: list[Path] = ()):
        self.name = name
        self.env = env
        self.files = [ROOT / "docker-compose.yml", *extra]

    # Выполняет команду Docker Compose для этого проекта.
    def command(self, *arguments: str, check: bool = True) -> str:
        # Имя проекта изолирует контейнеры, сети и volume от рабочего окружения.
        files = [item for path in self.files for item in ("-f", str(path))]
        return run(
            [
                DOCKER,
                "compose",
                "--project-directory",
                str(ROOT),
                "-p",
                self.name,
                *files,
                *arguments,
            ],
            self.env,
            check,
        )

    # Возвращает итоговую конфигурацию Compose в виде словаря.
    def config(self) -> dict:
        # Compose объединяет файлы и подставляет переменные до проверки политики.
        return json.loads(self.command("config", "--format", "json"))

    # Запускает сервисы и ожидает их готовности.
    def up(self, *services: str, recreate: bool = False) -> None:
        flags = ["--force-recreate"] if recreate else []
        self.command("up", "-d", "--wait", "--wait-timeout", "120", *flags, *services)

    # Возвращает идентификаторы работающих контейнеров проекта.
    def ids(self, service: str = "") -> list[str]:
        return self.command("ps", "-q", *([service] if service else [])).split()

    # Выполняет SQL-запрос в контейнере базы данных.
    def query(self, statement: str) -> str:
        # Берём имя БД и пользователя из итоговой конфигурации, без пароля в команде.
        db = self.config()["services"]["db"]["environment"]
        return self.command(
            "exec",
            "-T",
            "db",
            "psql",
            "--no-psqlrc",
            "-v",
            "ON_ERROR_STOP=1",
            "-U",
            db["POSTGRES_USER"],
            "-d",
            db["POSTGRES_DB"],
            "-tAc",
            statement,
        )

    # Удаляет временный проект и его ресурсы.
    def cleanup(self) -> None:
        # Удаляются только ресурсы этого временного Compose-проекта.
        self.command("down", "-v", "--remove-orphans", check=False)


# Возвращает сведения Docker о контейнере.
def inspect(container: str) -> dict:
    return json.loads(run([DOCKER, "inspect", container]))[0]


# Проверяет признаки штатного завершения приложения.
def assert_graceful(state: dict, logs: str) -> None:
    require(state["ExitCode"] == 0 and not state["OOMKilled"], "Нештатная остановка или OOM")
    require("Application shutdown complete." in logs, "Нет подтверждения graceful shutdown")


# Проверяет volume и совпадение восстановленных данных.
def assert_restored(source: str, target: str, expected: str, actual: str) -> None:
    require(bool(source) and bool(target) and source != target, "Нужен новый отдельный volume")
    require(bool(expected) and actual == expected, "Восстановленные данные не совпадают")


# Определяет имя volume с данными PostgreSQL.
def data_volume(environment: Environment) -> str:
    # Имя volume нужно, чтобы доказать восстановление в отдельное хранилище.
    mounts = inspect(environment.ids("db")[0])["Mounts"]
    return next(
        item["Name"] for item in mounts if item["Destination"] == "/var/lib/postgresql/data"
    )


# Проверяет пользователей, состояние, ресурсы и порты контейнеров.
def check_runtime(environment: Environment) -> None:
    for container in environment.ids():
        item = inspect(container)
        name = item["Config"]["Labels"]["com.docker.compose.service"]
        # Проверяем реальные процессы, а не только директиву user в Compose.
        users = run([DOCKER, "top", container, "-eo", "uid,pid"]).splitlines()[1:]
        require(
            bool(users) and all(int(uid.split()[0]) > 0 for uid in users), f"{name}: root-процесс"
        )
        require(item["State"]["Health"]["Status"] == "healthy", f"{name}: unhealthy")
        limits = item["HostConfig"]
        require(limits["Memory"] > 0 and limits["NanoCpus"] > 0, f"{name}: лимиты не применены")
        if name != "nginx":
            require(not limits["PortBindings"], f"{name}: порт опубликован")


# Отправляет запрос и получает идентификатор ответившей реплики.
def request_instance(url: str) -> str:
    # URL сформирован из loopback и числового порта тестового проекта.
    with urllib.request.urlopen(url, timeout=5) as response:  # nosec B310
        require(response.status == 200, "HTTP не вернул 200")
        instance = response.headers.get("X-Instance", "")
        require(bool(instance) and instance != "unknown", "Нет идентификатора реплики")
        return instance


# Проверяет распределение запросов и работу при отказе реплики.
def check_failover(environment: Environment, url: str) -> None:
    # Сначала убеждаемся, что Nginx направляет запросы обеим репликам.
    instances = {request_instance(url) for _ in range(12)}
    require(len(instances) == 2, "Запросы не распределяются между двумя репликами")
    stopped = environment.ids("app")[0]
    run([DOCKER, "stop", "-t", "20", stopped])
    try:
        # После остановки одной реплики все ответы должны приходить от другой.
        actual = {request_instance(url) for _ in range(20)}
        require(len(actual) == 1 and actual < instances, "Ошибка доступности после отказа реплики")
    finally:
        # Возвращаем остановленную реплику даже при ошибке проверки.
        run([DOCKER, "start", stopped])
    environment.up()


# Проверяет штатную остановку всех реплик приложения.
def check_shutdown(environment: Environment) -> None:
    # Сохраняем ID до остановки: после неё compose ps может их не показывать.
    applications = environment.ids("app")
    environment.command("stop", "-t", "20", "app")
    for container in applications:
        assert_graceful(
            inspect(container)["State"], run([DOCKER, "logs", container], include_stderr=True)
        )
    environment.up()


# Создаёт резервную копию и проверяет восстановление в новый volume.
def check_restore(
    source: Environment, target: Environment, directory: Path, expected: str, statement: str
) -> None:
    source.command(
        "exec",
        "-T",
        "-e",
        "PYTHONPATH=src",
        "app",
        "python",
        "scripts/backup.py",
        "create",
        "--file",
        "/app/backups/container-check.dump",
    )
    # Переносим архив из контейнера в приватный временный каталог на хосте.
    archive = directory / "restore.dump"
    source.command("cp", "--index", "1", "app:/app/backups/container-check.dump", str(archive))
    archive.chmod(0o644)
    # Поднимаем только новую БД и убеждаемся, что до восстановления она пуста.
    target.up("db")
    require(
        target.query("SELECT count(*) FROM pg_tables WHERE schemaname='public';") == "0",
        "Целевая БД не пустая",
    )
    target.command(
        "run",
        "--rm",
        "--no-deps",
        "-T",
        "-e",
        "PYTHONPATH=src",
        "--volume",
        f"{archive}:/restore.dump:ro",
        "app",
        "python",
        "scripts/backup.py",
        "restore",
        "--file",
        "/restore.dump",
    )
    # Сравниваем и содержимое строки, и имена исходного и целевого volume.
    assert_restored(data_volume(source), data_volume(target), expected, target.query(statement))
    require(
        source.query("SELECT version_num FROM alembic_version;")
        == target.query("SELECT version_num FROM alembic_version;"),
        "Не восстановлена версия миграций",
    )


# Проверяет обновление образа и сохранность данных.
def check_update(
    base: Environment, frontend: Environment, image: str, marker: str, statement: str, expected: str
) -> dict:
    # RELEASE_REVISION меняет артефакт образа без изменения бизнес-логики.
    before = run([DOCKER, "image", "inspect", "--format", "{{.Id}}", image])
    base.command("build", "--build-arg", f"RELEASE_REVISION={marker}-updated")
    after = run([DOCKER, "image", "inspect", "--format", "{{.Id}}", image])
    require(before != after, "Образ не обновился")
    check_image(base.config())
    frontend.up()
    require(
        all(inspect(container)["Image"] == after for container in frontend.ids("app")),
        "Реплики используют старый образ",
    )
    require(frontend.query(statement) == expected, "Потеря данных после обновления образа")
    return {"before": before, "after": after}


# Записывает успешно завершённый этап и выводит его название.
def record(events: list[str], name: str) -> None:
    events.append(name)
    print("OK: " + name, flush=True)


# Выполняет полный цикл проверок в изолированных проектах.
def execute(directory: Path, events: list[str]) -> dict:
    # Уникальные имена защищают рабочее окружение и параллельные запуски.
    marker = "auctions-check-" + uuid4().hex[:12]
    image = "auctions-check:" + uuid4().hex
    env = os.environ | {"APP_IMAGE": image}
    # Docker сам выберет свободный порт, доступный только на localhost.
    override = directory / "ports.yml"
    override.write_text('services:\n  nginx:\n    ports: !override\n      - "127.0.0.1::8080"\n')
    base = Environment(marker, env)
    frontend = Environment(marker, env, [ROOT / "docker-compose.nginx.yml", override])
    target = Environment(marker + "-restore", env)
    old_image = ""
    try:
        # Сначала проверяем политику обеих конфигураций и собранный образ.
        validate_sources(ROOT)
        validate_compose(base.config())
        validate_compose(Environment(marker, env, [ROOT / "docker-compose.nginx.yml"]).config())
        base.command("build", "--build-arg", f"RELEASE_REVISION={marker}")
        check_image(base.config())
        old_image = run([DOCKER, "image", "inspect", "--format", "{{.Id}}", image])
        record(events, "policy-and-image")
        # Запускаем две реплики и проверяем миграции и реальные параметры контейнеров.
        frontend.up()
        check_runtime(frontend)
        frontend.command("exec", "-T", "app", "alembic", "check")
        record(events, "migrations-and-runtime")
        # Сохраняем полную строку, чтобы обнаружить изменения любых её полей.
        frontend.query("INSERT INTO sellers(name) VALUES ('container-check');")
        statement = "SELECT row_to_json(s)::text FROM sellers s WHERE name='container-check';"
        expected = frontend.query(statement)
        frontend.up(recreate=True)
        require(frontend.query(statement) == expected, "Потеря данных после пересоздания")
        record(events, "recreate-with-data")
        # Проверяем обновление образа, восстановление, остановку и отказ реплики.
        images = check_update(base, frontend, image, marker, statement, expected)
        record(events, "image-update-with-data")
        check_restore(frontend, target, directory, expected, statement)
        record(events, "restore-into-new-volume")
        target.cleanup()
        check_shutdown(frontend)
        record(events, "graceful-shutdown")
        port = frontend.command("port", "nginx", "8080").rsplit(":", 1)[1]
        check_failover(frontend, f"http://127.0.0.1:{int(port)}/health")
        record(events, "two-instances-and-failover")
        return {"project": marker, "images": images}
    except Exception:
        # Последние журналы помогают найти причину до удаления тестового окружения.
        print(frontend.command("logs", "--no-color", "--tail", "20", check=False))
        raise
    finally:
        # Убираем временные проекты и образы как при успехе, так и при ошибке.
        target.cleanup()
        frontend.cleanup()
        run([DOCKER, "image", "rm", image], check=False)
        if old_image:
            run([DOCKER, "image", "rm", old_image], check=False)


# Подготавливает проверку и сохраняет итоговый JSON-отчёт.
def main() -> None:
    os.chdir(ROOT)
    require(DOCKER is not None, "Не найден Docker CLI")
    events = []
    report = {
        "host": platform.node(),
        "system": platform.system(),
        "machine": platform.machine(),
        "checks": events,
        "passed": False,
    }
    (ROOT / "reports").mkdir(exist_ok=True)
    try:
        with tempfile.TemporaryDirectory(prefix="auctions-check-") as temporary:
            report.update(execute(Path(temporary), events))
        report["passed"] = True
    finally:
        # Отчёт сохраняется и при ошибке: passed останется false, а checks покажет пройденные этапы.
        (ROOT / "reports/container-check.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n"
        )
    print("CONTAINER-CHECK PASS: " + ", ".join(events))


if __name__ == "__main__":
    try:
        main()
    except PolicyError as error:
        raise SystemExit(f"FAIL: {error}") from None
