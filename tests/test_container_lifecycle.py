"""Проверить критерии штатной остановки и восстановления в новый volume."""

import pytest
from scripts.container_check import assert_graceful, assert_restored
from scripts.container_policy import PolicyError


def test_graceful_shutdown():
    assert_graceful({"ExitCode": 0, "OOMKilled": False}, "Application shutdown complete.")


@pytest.mark.parametrize(
    ("state", "logs"),
    [
        ({"ExitCode": 137, "OOMKilled": False}, "Application shutdown complete."),
        ({"ExitCode": 0, "OOMKilled": True}, "Application shutdown complete."),
        ({"ExitCode": 0, "OOMKilled": False}, "process disappeared"),
    ],
)
def test_reject_forced_shutdown(state, logs):
    with pytest.raises(PolicyError):
        assert_graceful(state, logs)


def test_restored_into_distinct_volume():
    assert_restored("original", "fresh", "original-row", "original-row")


@pytest.mark.parametrize(
    ("source", "target", "actual"),
    [("same", "same", "row"), ("source", "fresh", "changed"), ("source", "fresh", "")],
)
def test_reject_invalid_restore(source, target, actual):
    with pytest.raises(PolicyError):
        assert_restored(source, target, "row", actual)
