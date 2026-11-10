"""The status relay must not approve unchecked or failed commits."""

import importlib.util
from pathlib import Path

import pytest


@pytest.mark.parametrize(
    ("revision", "building", "result", "expected"),
    [
        ("a" * 40, False, "SUCCESS", "success"),
        ("b" * 40, False, "SUCCESS", "pending"),
        ("a" * 40, True, None, "pending"),
        ("a" * 40, False, "FAILURE", "failure"),
    ],
)
def test_status_requires_matching_successful_build(
    monkeypatch, revision, building, result, expected
):
    monkeypatch.setenv("JENKINS_STATUS_USER", "test")
    monkeypatch.setenv("JENKINS_STATUS_TOKEN", "test")
    monkeypatch.setenv("GITHUB_STATUS_TOKEN", "test")
    path = Path(__file__).resolve().parents[1] / "ci/status-relay/relay.py"
    spec = importlib.util.spec_from_file_location("ci_status_relay", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    sent = []

    def fake_request(url, headers, payload=None):
        if payload is not None:
            sent.append(payload)
            return {}
        if "/pulls?" in url:
            return [{"number": 1, "head": {"sha": "a" * 40}}]
        return {
            "building": building,
            "result": result,
            "actions": [{"lastBuiltRevision": {"SHA1": revision}}],
        }

    monkeypatch.setattr(module, "request", fake_request)
    module.scan({})
    assert sent[0]["state"] == expected
