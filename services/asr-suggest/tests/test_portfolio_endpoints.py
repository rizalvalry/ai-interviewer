import asyncio

import pytest
from fastapi import HTTPException

import app
import auth
import config


def _run(coro):
    return asyncio.run(coro)


class TestAuthGate:
    """WI-13/WI-16: every portfolio endpoint must reject a missing/invalid token with 401,
    same auth.verify() gate as /suggest and /stream - none of the four is exempt."""

    def test_list_without_token_is_401(self, monkeypatch):
        monkeypatch.setattr(config, "AUTH_SECRET", "test-secret")
        with pytest.raises(HTTPException) as exc:
            _run(app.list_portfolios_endpoint(session="s", token=""))
        assert exc.value.status_code == 401

    def test_get_without_token_is_401(self, monkeypatch):
        monkeypatch.setattr(config, "AUTH_SECRET", "test-secret")
        with pytest.raises(HTTPException) as exc:
            _run(app.get_portfolio_endpoint(portfolio_id=1, session="s", token=""))
        assert exc.value.status_code == 401

    def test_create_without_token_is_401(self, monkeypatch):
        monkeypatch.setattr(config, "AUTH_SECRET", "test-secret")
        req = app.PortfolioCreateRequest(session="s", token="", name="CV", content="isi")
        with pytest.raises(HTTPException) as exc:
            _run(app.create_portfolio_endpoint(req))
        assert exc.value.status_code == 401

    def test_delete_without_token_is_401(self, monkeypatch):
        monkeypatch.setattr(config, "AUTH_SECRET", "test-secret")
        with pytest.raises(HTTPException) as exc:
            _run(app.delete_portfolio_endpoint(portfolio_id=1, session="s", token=""))
        assert exc.value.status_code == 401

    def test_wrong_session_for_valid_token_is_401(self, monkeypatch):
        # a token is signed for a specific session_id - reusing it under a different one
        # must fail the same way a missing token does.
        monkeypatch.setattr(config, "AUTH_SECRET", "test-secret")
        token = auth.issue("session-a")
        with pytest.raises(HTTPException) as exc:
            _run(app.list_portfolios_endpoint(session="session-b", token=token))
        assert exc.value.status_code == 401


class TestValidTokenReachesStore:
    def test_list_with_valid_token_succeeds(self, monkeypatch, portfolio_db):
        monkeypatch.setattr(config, "AUTH_SECRET", "test-secret")
        token = auth.issue("s")
        result = _run(app.list_portfolios_endpoint(session="s", token=token))
        assert result == []

    def test_create_then_get_round_trip(self, monkeypatch, portfolio_db):
        monkeypatch.setattr(config, "AUTH_SECRET", "test-secret")
        token = auth.issue("s")
        created = _run(
            app.create_portfolio_endpoint(
                app.PortfolioCreateRequest(session="s", token=token, name="CV-A", content="isi CV")
            )
        )
        record = _run(app.get_portfolio_endpoint(portfolio_id=created["id"], session="s", token=token))
        assert record["content"] == "isi CV"

    def test_create_with_invalid_content_is_400(self, monkeypatch, portfolio_db):
        monkeypatch.setattr(config, "AUTH_SECRET", "test-secret")
        token = auth.issue("s")
        req = app.PortfolioCreateRequest(session="s", token=token, name="CV", content="")
        with pytest.raises(HTTPException) as exc:
            _run(app.create_portfolio_endpoint(req))
        assert exc.value.status_code == 400

    def test_get_missing_id_is_404(self, monkeypatch, portfolio_db):
        monkeypatch.setattr(config, "AUTH_SECRET", "test-secret")
        token = auth.issue("s")
        with pytest.raises(HTTPException) as exc:
            _run(app.get_portfolio_endpoint(portfolio_id=999, session="s", token=token))
        assert exc.value.status_code == 404
