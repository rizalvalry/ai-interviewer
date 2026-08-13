import asyncio

import httpx

import config
import suggest
from conftest import FakeGeminiResponse


def test_no_api_key_returns_ok_false_without_calling_network(monkeypatch):
    monkeypatch.setattr(config, "GEMINI_API_KEY", "")
    result = asyncio.run(suggest.ask_llm(question="Kenapa pindah kerja?", utterances=[]))
    assert result == {"ok": False, "reason": "no-api-key", "text": "Saran tidak tersedia."}


def test_empty_question_returns_ok_false(monkeypatch):
    monkeypatch.setattr(config, "GEMINI_API_KEY", "some-key")
    result = asyncio.run(suggest.ask_llm(question="   ", utterances=[]))
    assert result == {"ok": False, "reason": "empty-question", "text": "Saran tidak tersedia."}


def test_http_429_maps_to_quota_not_a_crash(monkeypatch):
    monkeypatch.setattr(config, "GEMINI_API_KEY", "some-key")

    async def fake_post(self, url, params=None, json=None):
        return FakeGeminiResponse(429)

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    result = asyncio.run(suggest.ask_llm(question="Kenapa pindah kerja?", utterances=[]))
    assert result == {"ok": False, "reason": "quota", "text": "Saran tidak tersedia."}


def test_valid_response_extracts_text(monkeypatch):
    monkeypatch.setattr(config, "GEMINI_API_KEY", "some-key")

    async def fake_post(self, url, params=None, json=None):
        return FakeGeminiResponse(
            200,
            {
                "candidates": [{"content": {"parts": [{"text": "- Jawab jujur."}]}}],
                "usageMetadata": {"promptTokenCount": 10, "candidatesTokenCount": 5},
            },
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    result = asyncio.run(suggest.ask_llm(question="Kenapa pindah kerja?", utterances=[]))
    assert result == {"ok": True, "text": "- Jawab jujur.", "attempt": 1}


def test_timeout_then_success_on_second_attempt(monkeypatch):
    monkeypatch.setattr(config, "GEMINI_API_KEY", "some-key")
    calls = {"n": 0}

    async def fake_post(self, url, params=None, json=None):
        calls["n"] += 1
        if calls["n"] == 1:
            raise httpx.TimeoutException("timed out")
        return FakeGeminiResponse(200, {"candidates": [{"content": {"parts": [{"text": "ok"}]}}]})

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    result = asyncio.run(suggest.ask_llm(question="Kenapa pindah kerja?", utterances=[]))
    assert result["ok"] is True
    assert result["attempt"] == 2


def test_timeout_on_both_attempts_returns_timeout(monkeypatch):
    monkeypatch.setattr(config, "GEMINI_API_KEY", "some-key")

    async def fake_post(self, url, params=None, json=None):
        raise httpx.TimeoutException("timed out")

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    result = asyncio.run(suggest.ask_llm(question="Kenapa pindah kerja?", utterances=[]))
    assert result["ok"] is False
    assert result["reason"] == "timeout"


def test_empty_response_from_safety_block_is_not_a_fake_success(monkeypatch):
    # WI-B7 regression: candidates=[] (Gemini safety filter) must not surface as ok=True.
    monkeypatch.setattr(config, "GEMINI_API_KEY", "some-key")

    async def fake_post(self, url, params=None, json=None):
        return FakeGeminiResponse(200, {"candidates": []})

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    result = asyncio.run(suggest.ask_llm(question="Kenapa pindah kerja?", utterances=[]))
    assert result["ok"] is False


def test_build_user_content_keeps_only_last_six_of_eight_utterances():
    utterances = [{"ch": "candidate", "text": f"turn {i}"} for i in range(8)]
    content = suggest._build_user_content("Pertanyaan?", utterances, low_confidence=False)
    assert "turn 0" not in content
    assert "turn 1" not in content
    for i in range(2, 8):
        assert f"turn {i}" in content


def test_build_user_content_marks_low_confidence_question():
    content = suggest._build_user_content("Pertanyaan?", [], low_confidence=True)
    assert "[low-confidence]" in content


def test_system_instruction_keeps_stable_prefix_order_for_implicit_caching(monkeypatch):
    """Portfolio block must stay SECOND in systemInstruction.parts, after SYSTEM_PROMPT,
    on every call - a stable repeated prefix is what Gemini's implicit caching keys off."""
    monkeypatch.setattr(config, "GEMINI_API_KEY", "some-key")
    captured = {}

    async def fake_post(self, url, params=None, json=None):
        captured["body"] = json
        return FakeGeminiResponse(
            200, {"candidates": [{"content": {"parts": [{"text": "ok"}]}}]}
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    asyncio.run(
        suggest.ask_llm(
            question="Kenapa pindah kerja?", utterances=[], portfolio="5 tahun Python"
        )
    )
    parts = captured["body"]["systemInstruction"]["parts"]
    assert len(parts) == 2
    assert parts[0]["text"] == suggest.SYSTEM_PROMPT
    assert "5 tahun Python" in parts[1]["text"]
