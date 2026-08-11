"""bug-hunter RC-1 regression: config.LOW_CONF_LOGPROB must actually reach keep(), not just
sit in config.py unused. Mocks WhisperModel.transcribe so no real model load is needed -
these test the WIRING between asr.py/config.py/filters.py, not Whisper's own accuracy."""
from dataclasses import dataclass
from unittest.mock import patch

import numpy as np
import pytest

import asr
import config


@dataclass
class FakeSegment:
    text: str
    start: float = 0.0
    end: float = 2.0
    avg_logprob: float = -0.2
    no_speech_prob: float = 0.05


@dataclass
class FakeInfo:
    language: str = "id"
    language_probability: float = 0.9


def _run_transcribe_clean(monkeypatch, segments, language_hint=None):
    with patch.object(asr, "load") as mock_load:
        mock_model = mock_load.return_value
        mock_model.transcribe.return_value = (segments, FakeInfo())
        result = asr.transcribe_clean(np.zeros(32000, dtype=np.float32), language_hint)
    return result, mock_model


class TestLowConfThresholdWiring:
    def test_drops_segment_below_configured_threshold(self, monkeypatch):
        monkeypatch.setattr(config, "LOW_CONF_LOGPROB", -0.7)
        # exact reproduction of bug-hunter evidence: base model on "selamat sore"
        segs = [FakeSegment(text="Selamat sori.", avg_logprob=-0.802, no_speech_prob=0.122)]
        (out, _lang, stats), _ = _run_transcribe_clean(monkeypatch, segs)
        assert out == []
        assert stats["rejected_keep"] == 1

    def test_keeps_segment_above_configured_threshold(self, monkeypatch):
        monkeypatch.setattr(config, "LOW_CONF_LOGPROB", -0.7)
        segs = [FakeSegment(text="Selamat pagi.", avg_logprob=-0.3, no_speech_prob=0.05)]
        (out, _lang, _stats), _ = _run_transcribe_clean(monkeypatch, segs)
        assert len(out) == 1
        assert out[0]["text"] == "Selamat pagi."

    def test_threshold_is_read_from_config_not_hardcoded(self, monkeypatch):
        # same segment, two different config values -> two different outcomes proves the
        # value actually flows from config.py at call time, not a hardcoded constant.
        segs = [FakeSegment(text="halo dunia", avg_logprob=-0.85)]

        monkeypatch.setattr(config, "LOW_CONF_LOGPROB", -0.9)
        (out_lenient, _, _), _ = _run_transcribe_clean(monkeypatch, segs)
        assert len(out_lenient) == 1

        monkeypatch.setattr(config, "LOW_CONF_LOGPROB", -0.7)
        (out_strict, _, stats_strict), _ = _run_transcribe_clean(monkeypatch, segs)
        assert out_strict == []
        assert stats_strict["rejected_keep"] == 1


class TestLanguageHint:
    def test_defaults_to_auto_detect(self, monkeypatch):
        _, mock_model = _run_transcribe_clean(monkeypatch, [])
        assert mock_model.transcribe.call_args.kwargs["language"] is None

    def test_forwards_explicit_hint(self, monkeypatch):
        _, mock_model = _run_transcribe_clean(monkeypatch, [], language_hint="id")
        assert mock_model.transcribe.call_args.kwargs["language"] == "id"

    @pytest.mark.parametrize("hint", ["id", "en"])
    def test_forwards_both_supported_hints(self, monkeypatch, hint):
        _, mock_model = _run_transcribe_clean(monkeypatch, [], language_hint=hint)
        assert mock_model.transcribe.call_args.kwargs["language"] == hint
