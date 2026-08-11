import sys
from pathlib import Path

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).parent))

import config
import portfolio_store


@pytest.fixture
def portfolio_db(tmp_path, monkeypatch):
    """Isolated SQLite file per test - portfolio_store's connection is a module-level
    singleton (process lifetime), so it must be reset after repointing PORTFOLIO_DB_PATH or
    a later test would keep reading/writing a previous test's (possibly deleted) tmp_path."""
    monkeypatch.setattr(config, "PORTFOLIO_DB_PATH", str(tmp_path / "portfolios.db"))
    portfolio_store._reset_connection_for_tests()
    yield
    portfolio_store._reset_connection_for_tests()


class FakeGeminiResponse:
    """Minimal httpx.Response stand-in for testing Gemini REST error mapping (suggest.py,
    translate.py) without a real network call. Shared here since both modules' tests need it."""

    def __init__(self, status_code, json_data=None):
        self.status_code = status_code
        self._json_data = json_data or {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("error", request=None, response=self)

    def json(self):
        return self._json_data
