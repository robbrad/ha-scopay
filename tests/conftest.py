"""Shared fixtures for the SCOPAY tests."""

from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


def _load(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


@pytest.fixture
def products_html() -> str:
    """The /products page for a pupil with catering, a trip and lessons."""
    return _load("products.html")


@pytest.fixture
def history_html() -> str:
    """An account-history page with four dated rows and one blank."""
    return _load("history.html")


@pytest.fixture
def login_html() -> str:
    """The login page, as returned when the session has expired."""
    return _load("login.html")


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Let Home Assistant load custom_components/scopay in every test."""
    yield
