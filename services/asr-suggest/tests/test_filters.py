from dataclasses import dataclass

import numpy as np
import pytest

from filters import cap_history, dedup_boundary, is_audible, is_repetitive, keep


@dataclass
class FakeSegment:
    text: str
    start: float = 0.0
    end: float = 2.0
    avg_logprob: float = -0.2
    no_speech_prob: float = 0.05


class TestIsAudible:
    def test_digital_silence_is_not_audible(self):
        assert is_audible(np.zeros(16000, dtype=np.float32)) is False

    def test_empty_buffer_is_not_audible(self):
        assert is_audible(np.zeros(0, dtype=np.float32)) is False

    def test_speech_level_tone_is_audible(self):
        t = np.linspace(0, 1, 16000, dtype=np.float32)
        assert is_audible(0.2 * np.sin(2 * np.pi * 440 * t)) is True

    def test_noise_floor_below_threshold_is_gated(self):
        rng = np.random.default_rng(0)
        assert is_audible(rng.normal(0, 0.0005, 16000).astype(np.float32)) is False


class TestKeep:
    def test_accepts_normal_segment(self):
        assert keep(FakeSegment("Saya punya pengalaman lima tahun")) is True

    def test_rejects_empty_text(self):
        assert keep(FakeSegment("   ")) is False

    @pytest.mark.parametrize(
        "text",
        [
            "Terima kasih telah menonton",
            "thanks for watching!",
            "Jangan lupa like dan subscribe",
            "Terima kasih kerana menonton!",  # gejala #2 screenshot: Malay spelling variant
        ],
    )
    def test_rejects_blocklisted_hallucination(self, text):
        assert keep(FakeSegment(text)) is False

    def test_rejects_segment_shorter_than_300ms(self):
        assert keep(FakeSegment("ya", start=1.0, end=1.2)) is False

    def test_rejects_low_logprob(self):
        assert keep(FakeSegment("halo dunia", avg_logprob=-1.5)) is False

    def test_rejects_high_no_speech_prob(self):
        assert keep(FakeSegment("halo dunia", no_speech_prob=0.9)) is False


class TestHallucinationPhrases:
    """bug-hunter H2 follow-up: known Whisper filler hallucinations, gated on no_speech_prob
    rather than unconditional - a candidate genuinely saying "sorry" with clear audio must
    still survive."""

    @pytest.mark.parametrize("text", ["Hello.", "hi", "Hallo!", "Sorry", "I'm sorry.", "Thanks"])
    def test_drops_known_phrase_when_no_speech_prob_elevated(self, text):
        assert keep(FakeSegment(text, no_speech_prob=0.4)) is False

    @pytest.mark.parametrize("text", ["Hello.", "Sorry", "I'm sorry."])
    def test_keeps_known_phrase_when_no_speech_prob_low(self, text):
        assert keep(FakeSegment(text, no_speech_prob=0.1)) is True

    def test_keeps_unrelated_text_even_with_elevated_no_speech_prob(self):
        assert keep(FakeSegment("Saya suka kopi pagi ini", no_speech_prob=0.4)) is True


class TestIsRepetitive:
    def test_short_text_is_never_flagged(self):
        assert is_repetitive("ya ya ya") is False

    def test_detects_decoder_loop(self):
        assert is_repetitive("ya ya ya ya ya ya ya ya") is True

    def test_normal_sentence_passes(self):
        assert is_repetitive("saya membangun sistem pembayaran untuk aplikasi mobile") is False


class TestDedupBoundary:
    def test_no_overlap_returns_new_text_unchanged(self):
        assert dedup_boundary("selamat pagi", "apa kabar") == "apa kabar"

    def test_partial_overlap_is_trimmed(self):
        assert dedup_boundary("saya bekerja di bank", "di bank selama lima tahun") == "selama lima tahun"

    def test_full_containment_returns_empty(self):
        assert dedup_boundary("halo semuanya", "halo semuanya") == ""

    def test_overlap_matches_despite_punctuation_and_case(self):
        assert dedup_boundary("kita mulai sekarang.", "Sekarang, kita lanjut") == "kita lanjut"

    def test_empty_previous_returns_new(self):
        assert dedup_boundary("", "kalimat pertama") == "kalimat pertama"

    def test_empty_new_returns_empty(self):
        assert dedup_boundary("kalimat sebelumnya", "") == ""

    def test_punctuation_only_token_does_not_desync_indexes(self):
        assert dedup_boundary("bagian satu -", "- bagian dua") == "bagian dua"


class TestCapHistory:
    """F-1 translation context: cap_history(history, text) -> new list, last N kept."""

    def test_appends_when_under_cap(self):
        assert cap_history([], "a") == ["a"]
        assert cap_history(["a"], "b") == ["a", "b"]

    def test_drops_oldest_beyond_default_cap_of_two(self):
        assert cap_history(["a", "b"], "c") == ["b", "c"]

    def test_respects_custom_max_len(self):
        assert cap_history(["a", "b", "c"], "d", max_len=3) == ["b", "c", "d"]

    def test_does_not_mutate_input_list(self):
        original = ["a", "b"]
        cap_history(original, "c")
        assert original == ["a", "b"]
