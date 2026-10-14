import pytest

from tests.configuration import IsolatedTestSettings, validate_database_url

WORKING_URL = "postgresql+psycopg://app:password@localhost:5432/auctions"


@pytest.mark.parametrize(
    "url",
    [
        WORKING_URL,
        "postgresql+psycopg://app:password@localhost:5432/postgres",
        "postgresql+psycopg://app:password@localhost:5432/auctions_testing",
        "postgresql+psycopg://localhost:5432/auctions_test",
        "postgresql+psycopg://app:password@localhost:5432/",
        "sqlite:///auctions_test",
        "postgresql+psycopg://app:password@localhost:5432/auctions_test?dbname=auctions",
    ],
)
def test_reject_unsafe_test_database(url: str) -> None:
    with pytest.raises(ValueError, match="TEST_DATABASE_URL"):
        validate_database_url(url, WORKING_URL)


def test_reject_working_database_even_with_test_suffix() -> None:
    with pytest.raises(ValueError, match="TEST_DATABASE_URL"):
        validate_database_url(
            "postgresql+psycopg://tester:password@127.0.0.1:5432/app_test",
            "postgresql+psycopg://app:password@localhost:5432/app_test",
        )


def test_accept_separate_test_database() -> None:
    validate_database_url(
        "postgresql+psycopg://tester:password@localhost:5432/auctions_test", WORKING_URL
    )


def test_test_settings_ignore_working_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", WORKING_URL)
    monkeypatch.setenv("ADMIN_USERNAME", "working-admin")
    monkeypatch.delenv("TEST_DATABASE_URL", raising=False)
    monkeypatch.delenv("TEST_ADMIN_USERNAME", raising=False)

    settings = IsolatedTestSettings(_env_file=None)

    assert settings.database_url.endswith("/auctions_test")
    assert settings.admin_username == "test-admin"
