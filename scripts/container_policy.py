"""Проверить ограничения итогового Compose и входных файлов сборки."""

import json
import math
import re
import shlex
import sys
from pathlib import Path


class PolicyError(ValueError):
    """Контейнерное окружение нарушает обязательное ограничение."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise PolicyError(message)


def validate_image(image: str, external: bool = True) -> None:
    tagged = image.split("@", 1)[0].rsplit("/", 1)[-1]
    require(":" in tagged and tagged.rsplit(":", 1)[1] != "latest", "Нужен явный тег без latest")
    if external:
        require(bool(re.search(r"@sha256:[a-f0-9]{64}$", image)), "Внешний образ требует digest")


def validate_service(name: str, service: dict, nginx: bool) -> None:
    validate_image(service.get("image", ""), external=name in {"db", "nginx"})
    uid = str(service.get("user", "")).split(":", 1)[0]
    require(uid.isdigit() and int(uid) > 0, f"{name}: требуется непривилегированный UID")
    require(not service.get("privileged"), f"{name}: privileged запрещён")
    require(not service.get("network_mode"), f"{name}: network_mode запрещён")
    require(set(service.get("networks", {})) == {"backend"}, f"{name}: нужна сеть backend")
    limits = service.get("deploy", {}).get("resources", {}).get("limits", {})
    cpu = float(limits.get("cpus", 0))
    require(math.isfinite(cpu) and cpu > 0, f"{name}: нужен конечный CPU limit")
    require(
        bool(re.fullmatch(r"[1-9][0-9]*(?:[kKmMgG][bB]?)?", str(limits.get("memory", "")))),
        f"{name}: нужен memory limit",
    )
    allowed_port = {"nginx": 8080} if nginx else {"app": 8000}
    ports = service.get("ports", [])
    require(len(ports) <= int(name in allowed_port), f"{name}: лишний опубликованный порт")
    for port in ports:
        require(int(port["target"]) == allowed_port[name], f"{name}: запрещённый порт")
    if name != "migrate":
        health = service.get("healthcheck", {})
        require(
            not health.get("disable") and bool(health.get("test")), f"{name}: нужен healthcheck"
        )
        require(health["test"][0] != "NONE", f"{name}: healthcheck отключён")


def validate_compose(config: dict) -> None:
    services = config["services"]
    nginx = "nginx" in services
    require(
        set(services) == {"app", "db", "migrate"} | ({"nginx"} if nginx else set()),
        "Неожиданный набор сервисов",
    )
    for name, service in services.items():
        validate_service(name, service, nginx)
    migrate = services["migrate"]
    require(
        migrate.get("command") == ["alembic", "upgrade", "head"], "migrate должен выполнять Alembic"
    )
    require(migrate.get("restart") == "no", "migrate должен завершаться однократно")
    condition = services["app"].get("depends_on", {}).get("migrate", {}).get("condition")
    require(condition == "service_completed_successfully", "app должен ждать миграции")
    if nginx:
        require(services["app"].get("deploy", {}).get("replicas", 1) >= 2, "Нужны две реплики")


def validate_sources(root: Path) -> None:
    text = (root / "Dockerfile").read_text()
    logical = text.replace("\\\n", " ")
    stages = set()
    allowed = {
        "src",
        "migrations",
        "docker/entrypoint.sh",
        "scripts/backup.py",
        "alembic.ini",
        "pyproject.toml",
        "uv.lock",
    }
    for line in logical.splitlines():
        words = shlex.split(line, comments=True)
        if not words:
            continue
        if words[0] == "FROM":
            validate_image(words[1])
            stages.add(words[-1])
        if words[0] == "COPY":
            validate_copy(words[1:], stages, allowed)
        require(words[0] != "ADD", "ADD запрещён: используйте явный COPY")
    require(
        not re.search(r"(?:ARG|ENV)\s+[^\n]*(?:PASSWORD|SECRET|TOKEN|PRIVATE_KEY)", logical),
        "Секреты в ARG/ENV образа запрещены",
    )
    patterns = (root / ".dockerignore").read_text().splitlines()
    require(patterns[0] == "**" and "!**" not in patterns, "Контекст сборки требует allowlist")


def validate_copy(words: list[str], stages: set[str], allowed: set[str]) -> None:
    if words[0].startswith("--from="):
        source = words[0].split("=", 1)[1]
        if source not in stages:
            validate_image(source)
        return
    require(set(words[:-1]) <= allowed, "COPY содержит лишние входные файлы")


if __name__ == "__main__":
    try:
        validate_compose(json.load(sys.stdin))
        validate_sources(Path(__file__).resolve().parents[1])
    except (PolicyError, KeyError, ValueError) as error:
        raise SystemExit(f"FAIL: {error}") from None
    print("OK: Compose и входные файлы соответствуют контейнерным ограничениям")
