"""LOW finding (audit v0.3.2): trivial coverage for /health and /metrics."""
import asyncio

import app
import config


def test_health_reports_model_and_auth_state(monkeypatch):
    monkeypatch.setattr(config, "AUTH_SECRET", "test-secret")
    result = asyncio.run(app.health())
    assert result["ok"] is True
    assert result["model"] == config.MODEL_SIZE
    assert result["auth"] is True


def test_metrics_returns_the_live_metrics_dict():
    result = asyncio.run(app.metrics())
    assert result is app.METRICS
    assert "windows_transcribed" in result
