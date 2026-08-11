import asyncio

import config
import translate


def test_no_api_key_returns_ok_false_without_calling_network(monkeypatch):
    monkeypatch.setattr(config, "ANTHROPIC_API_KEY", "")
    result = asyncio.run(translate.ask_translate("hello there", []))
    assert result == {"ok": False, "reason": "no-api-key"}


def test_empty_text_returns_ok_false(monkeypatch):
    monkeypatch.setattr(config, "ANTHROPIC_API_KEY", "some-key")
    result = asyncio.run(translate.ask_translate("   ", ["previous turn"]))
    assert result == {"ok": False, "reason": "empty-text"}


def test_build_user_content_marks_only_last_turn_for_translation():
    content = translate._build_user_content("how are you", ["hi", "nice to meet you"])
    assert content == (
        "[konteks] hi\n[konteks] nice to meet you\n[terjemahkan] how are you"
    )
