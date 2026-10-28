"""Проверить отсутствие runtime-секретов в слоях собранного образа."""

import json
import shutil

# Только доверенный Docker CLI без shell; аргументы не содержат секретов.
import subprocess  # nosec B404
import sys
from typing import BinaryIO

from scripts.container_policy import PolicyError, require

SECRET_NAMES = {"POSTGRES_PASSWORD", "SESSION_SECRET", "ADMIN_PASSWORD"}


def contains_secret(stream: BinaryIO, secrets: list[bytes]) -> bool:
    tail = b""
    overlap = max(map(len, secrets), default=1)
    while chunk := stream.read(1024 * 1024):
        data = tail + chunk
        if any(secret in data for secret in secrets):
            return True
        tail = data[-overlap:]
    return False


def check_image(config: dict) -> None:
    docker = shutil.which("docker")
    require(docker is not None, "Не найден Docker CLI")
    image = config["services"]["app"]["image"]
    # Docker CLI найден в PATH, команды фиксированы, shell=False, секретов в argv нет.
    metadata = json.loads(subprocess.check_output([docker, "image", "inspect", image]))[0]  # nosec B603
    user = metadata["Config"].get("User", "").split(":", 1)[0]
    require(user not in {"", "0", "root"}, "Образ приложения запускается от root")
    env = metadata["Config"].get("Env", [])
    require(not any(item.split("=", 1)[0] in SECRET_NAMES for item in env), "Секрет в ENV образа")
    secrets = {
        value.encode()
        for service in config["services"].values()
        for key, value in service.get("environment", {}).items()
        if key in SECRET_NAMES and value
    }
    # docker save выдаёт несжатые слои; поток проверяется без записи архива на диск.
    with subprocess.Popen([docker, "image", "save", image], stdout=subprocess.PIPE) as child:  # nosec B603
        if contains_secret(child.stdout, list(secrets)):
            child.terminate()
            raise PolicyError("Runtime-секрет найден в слоях образа")
        require(child.wait() == 0, "Не удалось прочитать слои образа")


if __name__ == "__main__":
    try:
        check_image(json.load(sys.stdin))
    except PolicyError as error:
        raise SystemExit(f"FAIL: {error}") from None
    print("OK: runtime-секреты отсутствуют в конфигурации и слоях образа")
