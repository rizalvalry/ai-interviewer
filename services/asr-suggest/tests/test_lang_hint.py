import pytest

from app import _normalize_lang_hint


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("id", "id"),
        ("en", "en"),
        ("auto", None),
        ("", None),
        ("de", None),  # never forward an unsupported value straight to Whisper
        ("ID", None),  # exact match only - the UI always sends lowercase
    ],
)
def test_normalize_lang_hint(raw, expected):
    assert _normalize_lang_hint(raw) == expected
