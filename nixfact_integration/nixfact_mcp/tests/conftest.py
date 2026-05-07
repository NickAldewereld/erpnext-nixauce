"""Shared pytest fixtures for nixfact-mcp tests."""

from __future__ import annotations


import pytest


@pytest.fixture(autouse=True)
def _set_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Default env so NixfactClient() constructs without arguments."""
    monkeypatch.setenv("NIXFACT_BASE_URL", "https://erp.test")
    monkeypatch.setenv("NIXFACT_API_KEY", "test-key")
    monkeypatch.setenv("NIXFACT_API_SECRET", "test-secret")


@pytest.fixture
def base_url() -> str:
    return "https://erp.test"
