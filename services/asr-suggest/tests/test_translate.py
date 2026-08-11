import asyncio

import httpx

import config
import translate
from conftest import FakeGeminiResponse


class TestTranslationBatch:
    """WI-12: batching window is pure state + injected `now`, no asyncio/timer needed."""

    def test_does_not_flush_when_empty(self):
        batch = translate.TranslationBatch()
        assert batch.should_flush(now=1000.0) is False

    def test_flushes_when_max_items_reached(self):
        batch = translate.TranslationBatch(max_items=3, max_wait_sec=100.0)
        batch.add(1, "a")
        batch.add(2, "b")
        assert batch.should_flush(now=0.0) is False
        batch.add(3, "c")
        assert batch.should_flush(now=0.0) is True

    def test_flushes_when_max_wait_elapsed(self):
        batch = translate.TranslationBatch(max_items=10, max_wait_sec=4.0)
        batch.add(1, "a")  # started_at captured via time.monotonic() internally
        started = batch.started_at
        assert batch.should_flush(now=started + 3.9) is False
        assert batch.should_flush(now=started + 4.0) is True

    def test_drain_resets_state_and_returns_items(self):
        batch = translate.TranslationBatch()
        batch.add(1, "a")
        batch.add(2, "b")
        items = batch.drain()
        assert items == [{"seq": 1, "text": "a"}, {"seq": 2, "text": "b"}]
        assert batch.items == []
        assert batch.should_flush(now=999999.0) is False

    def test_second_batch_after_drain_starts_its_own_window(self):
        batch = translate.TranslationBatch(max_items=10, max_wait_sec=4.0)
        batch.add(1, "a")
        batch.drain()
        batch.add(2, "b")
        assert batch.should_flush(now=batch.started_at + 3.9) is False


class TestAskTranslateBatchGuards:
    def test_no_api_key_returns_ok_false_without_calling_network(self, monkeypatch):
        monkeypatch.setattr(config, "GEMINI_API_KEY", "")
        result = asyncio.run(translate.ask_translate_batch([{"seq": 0, "text": "hi"}], []))
        assert result == {"ok": False, "reason": "no-api-key"}

    def test_empty_batch_returns_ok_false(self, monkeypatch):
        monkeypatch.setattr(config, "GEMINI_API_KEY", "some-key")
        result = asyncio.run(translate.ask_translate_batch([], []))
        assert result == {"ok": False, "reason": "empty-batch"}


class TestAskTranslateBatchErrorMapping:
    def test_http_429_maps_to_quota(self, monkeypatch):
        monkeypatch.setattr(config, "GEMINI_API_KEY", "some-key")

        async def fake_post(self, url, params=None, json=None):
            return FakeGeminiResponse(429)

        monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
        result = asyncio.run(translate.ask_translate_batch([{"seq": 0, "text": "hi"}], []))
        assert result == {"ok": False, "reason": "quota"}

    def test_valid_response_parses_translations_by_seq(self, monkeypatch):
        monkeypatch.setattr(config, "GEMINI_API_KEY", "some-key")

        async def fake_post(self, url, params=None, json=None):
            return FakeGeminiResponse(
                200,
                {
                    "candidates": [
                        {
                            "content": {
                                "parts": [
                                    {
                                        "text": (
                                            '[{"seq": 0, "text": "halo"}, '
                                            '{"seq": 1, "text": "apa kabar"}]'
                                        )
                                    }
                                ]
                            }
                        }
                    ]
                },
            )

        monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
        result = asyncio.run(
            translate.ask_translate_batch(
                [{"seq": 0, "text": "hi"}, {"seq": 1, "text": "how are you"}], []
            )
        )
        assert result == {"ok": True, "translations": {0: "halo", 1: "apa kabar"}}

    def test_malformed_json_response_maps_to_bad_response(self, monkeypatch):
        monkeypatch.setattr(config, "GEMINI_API_KEY", "some-key")

        async def fake_post(self, url, params=None, json=None):
            return FakeGeminiResponse(
                200,
                {"candidates": [{"content": {"parts": [{"text": "bukan json"}]}}]},
            )

        monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
        result = asyncio.run(translate.ask_translate_batch([{"seq": 0, "text": "hi"}], []))
        assert result == {"ok": False, "reason": "bad-response"}
