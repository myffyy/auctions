"""Проверить отклонение опасных изменений итоговой Compose-конфигурации."""

from copy import deepcopy

import pytest
from scripts.container_policy import PolicyError, validate_compose

DIGEST = "@sha256:" + "a" * 64


@pytest.fixture
def config():
    services = {}
    for name, uid in (("db", "70:70"), ("app", "10001:10001"), ("migrate", "10001:10001")):
        services[name] = {
            "image": "auctions-app:0.1.0" if name != "db" else "postgres:14-alpine" + DIGEST,
            "user": uid,
            "networks": {"backend": None},
            "healthcheck": {"test": ["CMD", "true"]},
            "deploy": {"resources": {"limits": {"cpus": "0.5", "memory": "256M"}}},
        }
    services["app"]["ports"] = [{"target": 8000, "published": "18000"}]
    services["migrate"]["command"] = ["alembic", "upgrade", "head"]
    services["migrate"]["restart"] = "no"
    del services["migrate"]["healthcheck"]
    services["app"]["depends_on"] = {"migrate": {"condition": "service_completed_successfully"}}
    return {"services": services}


def test_accept_valid_configuration(config):
    validate_compose(config)


@pytest.mark.parametrize(
    ("service", "field", "value"),
    [
        ("app", "image", "auctions-app:latest"),
        ("db", "image", "postgres:14-alpine"),
        ("app", "user", "0:0"),
        ("app", "user", "root"),
        ("app", "healthcheck", {"disable": True}),
        ("db", "healthcheck", {"test": ["NONE"]}),
        ("db", "ports", [{"target": 5432, "published": "5432"}]),
        ("app", "ports", [{"target": 8000}, {"target": 9000}]),
        ("app", "network_mode", "host"),
        ("app", "privileged", True),
        ("app", "deploy", {}),
        ("app", "depends_on", {"db": {"condition": "service_started"}}),
        ("migrate", "command", ["true"]),
    ],
)
def test_reject_operational_violation(config, service, field, value):
    config["services"][service][field] = value
    with pytest.raises(PolicyError):
        validate_compose(config)


def test_reject_missing_healthcheck(config):
    del config["services"]["db"]["healthcheck"]
    with pytest.raises(PolicyError):
        validate_compose(config)


def test_nginx_requires_hidden_application_and_two_replicas(config):
    config["services"]["nginx"] = deepcopy(config["services"]["app"])
    nginx = config["services"]["nginx"]
    nginx["image"] = "nginx:1.27-alpine" + DIGEST
    nginx["ports"] = [{"target": 8080, "published": "8090"}]
    config["services"]["app"]["deploy"]["replicas"] = 2
    with pytest.raises(PolicyError):
        validate_compose(config)
    config["services"]["app"].pop("ports")
    validate_compose(config)
    config["services"]["app"]["deploy"]["replicas"] = 1
    with pytest.raises(PolicyError):
        validate_compose(config)


@pytest.mark.parametrize(
    "line",
    [
        "COPY . /app",
        "ADD src /app",
        "ARG SESSION_SECRET",
        "FROM python:3.12",
        "COPY --from=uv:latest /uv /bin/",
    ],
)
def test_reject_unsafe_build_inputs(tmp_path, line):
    from scripts.container_policy import validate_sources

    (tmp_path / "Dockerfile").write_text("FROM python:3.12" + DIGEST + " AS base\n" + line + "\n")
    (tmp_path / ".dockerignore").write_text("**\n!src/\n!src/**\n")
    with pytest.raises(PolicyError):
        validate_sources(tmp_path)


def test_secret_crossing_read_boundary_is_detected():
    from io import BytesIO

    from scripts.check_container_image import contains_secret

    secret = b"runtime-secret-value"
    stream = BytesIO(b"x" * (1024 * 1024 - 5) + secret + b"other-layer")
    assert contains_secret(stream, [secret])
    assert not contains_secret(BytesIO(b"clean-image"), [secret])
