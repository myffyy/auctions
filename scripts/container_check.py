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

    def __init__(self, name: str, env: dict, extra: list[Path] = ()):
        self.name = name
        self.env = env
        self.files = [ROOT / "docker-compose.yml", *extra]

    def command(self, *arguments: str, check: bool = True) -> str:
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

    def config(self) -> dict:
        return json.loads(self.command("config", "--format", "json"))

    def up(self, *services: str, recreate: bool = False) -> None:
        flags = ["--force-recreate"] if recreate else []
        self.command("up", "-d", "--wait", "--wait-timeout", "120", *flags, *services)

    def ids(self, service: str = "") -> list[str]:
        return self.command("ps", "-q", *([service] if service else [])).split()

    def query(self, statement: str) -> str:
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

    def cleanup(self) -> None:
        self.command("down", "-v", "--remove-orphans", check=False)


def inspect(container: str) -> dict:
    return json.loads(run([DOCKER, "inspect", container]))[0]


def assert_graceful(state: dict, logs: str) -> None:
    require(state["ExitCode"] == 0 and not state["OOMKilled"], "Нештатная остановка или OOM")
    require("Application shutdown complete." in logs, "Нет подтверждения graceful shutdown")


def assert_restored(source: str, target: str, expected: str, actual: str) -> None:
    require(bool(source) and bool(target) and source != target, "Нужен новый отдельный volume")
    require(bool(expected) and actual == expected, "Восстановленные данные не совпадают")


def data_volume(environment: Environment) -> str:
    mounts = inspect(environment.ids("db")[0])["Mounts"]
    return next(
        item["Name"] for item in mounts if item["Destination"] == "/var/lib/postgresql/data"
    )


def check_runtime(environment: Environment) -> None:
    for container in environment.ids():
        item = inspect(container)
        name = item["Config"]["Labels"]["com.docker.compose.service"]
        users = run([DOCKER, "top", container, "-eo", "uid,pid"]).splitlines()[1:]
        require(
            bool(users) and all(int(uid.split()[0]) > 0 for uid in users), f"{name}: root-процесс"
        )
        require(item["State"]["Health"]["Status"] == "healthy", f"{name}: unhealthy")
        limits = item["HostConfig"]
        require(limits["Memory"] > 0 and limits["NanoCpus"] > 0, f"{name}: лимиты не применены")
        if name != "nginx":
            require(not limits["PortBindings"], f"{name}: порт опубликован")


def request_instance(url: str) -> str:
    # URL сформирован из loopback и числового порта тестового проекта.
    with urllib.request.urlopen(url, timeout=5) as response:  # nosec B310
        require(response.status == 200, "HTTP не вернул 200")
        instance = response.headers.get("X-Instance", "")
        require(bool(instance) and instance != "unknown", "Нет идентификатора реплики")
        return instance


def check_failover(environment: Environment, url: str) -> None:
    instances = {request_instance(url) for _ in range(12)}
    require(len(instances) == 2, "Запросы не распределяются между двумя репликами")
    stopped = environment.ids("app")[0]
    run([DOCKER, "stop", "-t", "20", stopped])
    try:
        actual = {request_instance(url) for _ in range(20)}
        require(len(actual) == 1 and actual < instances, "Ошибка доступности после отказа реплики")
    finally:
        run([DOCKER, "start", stopped])
    environment.up()


def check_shutdown(environment: Environment) -> None:
    applications = environment.ids("app")
    environment.command("stop", "-t", "20", "app")
    for container in applications:
        assert_graceful(
            inspect(container)["State"], run([DOCKER, "logs", container], include_stderr=True)
        )
    environment.up()


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
    archive = directory / "restore.dump"
    source.command("cp", "--index", "1", "app:/app/backups/container-check.dump", str(archive))
    archive.chmod(0o644)
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
    assert_restored(data_volume(source), data_volume(target), expected, target.query(statement))
    require(
        source.query("SELECT version_num FROM alembic_version;")
        == target.query("SELECT version_num FROM alembic_version;"),
        "Не восстановлена версия миграций",
    )


def check_update(
    base: Environment, frontend: Environment, image: str, marker: str, statement: str, expected: str
) -> dict:
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


def record(events: list[str], name: str) -> None:
    events.append(name)
    print("OK: " + name, flush=True)


def execute(directory: Path, events: list[str]) -> dict:
    marker = "auctions-check-" + uuid4().hex[:12]
    image = "auctions-check:" + uuid4().hex
    env = os.environ | {"APP_IMAGE": image}
    override = directory / "ports.yml"
    override.write_text('services:\n  nginx:\n    ports: !override\n      - "127.0.0.1::8080"\n')
    base = Environment(marker, env)
    frontend = Environment(marker, env, [ROOT / "docker-compose.nginx.yml", override])
    target = Environment(marker + "-restore", env)
    old_image = ""
    try:
        validate_sources(ROOT)
        validate_compose(base.config())
        validate_compose(Environment(marker, env, [ROOT / "docker-compose.nginx.yml"]).config())
        base.command("build", "--build-arg", f"RELEASE_REVISION={marker}")
        check_image(base.config())
        old_image = run([DOCKER, "image", "inspect", "--format", "{{.Id}}", image])
        record(events, "policy-and-image")
        frontend.up()
        check_runtime(frontend)
        frontend.command("exec", "-T", "app", "alembic", "check")
        record(events, "migrations-and-runtime")
        frontend.query("INSERT INTO sellers(name) VALUES ('container-check');")
        statement = "SELECT row_to_json(s)::text FROM sellers s WHERE name='container-check';"
        expected = frontend.query(statement)
        frontend.up(recreate=True)
        require(frontend.query(statement) == expected, "Потеря данных после пересоздания")
        record(events, "recreate-with-data")
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
        print(frontend.command("logs", "--no-color", "--tail", "20", check=False))
        raise
    finally:
        target.cleanup()
        frontend.cleanup()
        run([DOCKER, "image", "rm", image], check=False)
        if old_image:
            run([DOCKER, "image", "rm", old_image], check=False)


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
        (ROOT / "reports/container-check.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n"
        )
    print("CONTAINER-CHECK PASS: " + ", ".join(events))


if __name__ == "__main__":
    try:
        main()
    except PolicyError as error:
        raise SystemExit(f"FAIL: {error}") from None
