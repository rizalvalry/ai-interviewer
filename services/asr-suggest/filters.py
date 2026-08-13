"""Anti-hallucination layers 1, 4, 5 and 6 from the guide.

Pure functions only, no model or IO dependency, so the whole defense stack is unit
testable without loading Whisper.
"""

import math
import re

import numpy as np

BLOCKLIST = {
    "terima kasih telah menonton",
    "terima kasih sudah menonton",
    "terima kasih kerana menonton",  # gejala #2 screenshot: Malay spelling variant slipped through
    "thanks for watching",
    "thank you for watching",
    "subscribe",
    "like dan subscribe",
    "sampai jumpa di video berikutnya",
    "jangan lupa like dan subscribe",
    "silakan berlangganan",
}

# Bug ASR bahasa Indonesia (2026-08-11, bug-hunter Phase 1): klasik Whisper hallucinated
# fillers on ambiguous/quiet audio - "Hello.", "I'm sorry.", "Hallo!", "Sorry" reported live.
# Gated on no_speech_prob rather than unconditional (unlike BLOCKLIST above): a candidate
# legitimately saying "Sorry, could you repeat that?" with clear audio must not be dropped -
# only when the model is ALSO moderately unsure whether this was speech at all.
HALLUCINATION_PHRASES = {
    "hello",
    "hi",
    "hallo",
    "sorry",
    "i'm sorry",
    "thank you",
    "thanks",
}
HALLUCINATION_NO_SPEECH_THRESHOLD = 0.3

_PUNCT = re.compile(r"[.,!?;:\"'()\[\]]+")

# WI-A5 (audit v0.3.2): the old `b in lowered` substring check matched BLOCKLIST single
# words inside unrelated words too - "subscribe" inside "subscribers"/"subscription" was
# silently dropping real interview content about SaaS/social-media metrics. Single-word
# entries now require a word boundary; multi-word phrases keep substring matching (specific
# enough on their own not to over-match).
_BLOCKLIST_PATTERNS = [
    re.compile(r"\b" + re.escape(b) + r"\b", re.IGNORECASE)
    if " " not in b
    else re.compile(re.escape(b), re.IGNORECASE)
    for b in BLOCKLIST
]


def _is_known_hallucination(text: str, no_speech_prob: float) -> bool:
    # Only trailing punctuation, not _PUNCT's full strip - "i'm sorry" needs its apostrophe
    # to match the phrase set below; _PUNCT (shared with dedup_boundary) removes it.
    normalized = text.strip().lower().rstrip(".,!?")
    return normalized in HALLUCINATION_PHRASES and no_speech_prob > HALLUCINATION_NO_SPEECH_THRESHOLD


def is_audible(pcm: np.ndarray, thresh_db: float = -45.0) -> bool:
    """Layer 1: never hand silence to Whisper. Input it never sees cannot be hallucinated."""
    if pcm.size == 0:
        return False
    rms = float(np.sqrt(np.mean(pcm.astype(np.float64) ** 2) + 1e-12))
    return bool(20.0 * math.log10(rms + 1e-12) > thresh_db)


def _norm_words(text: str) -> list[str]:
    return [w for w in _PUNCT.sub("", text.lower()).split() if w]


def _align_norm(words: list[str]) -> list[str]:
    """Normalize per word, preserving 1:1 index alignment with the raw list."""
    return [_PUNCT.sub("", w.lower()) for w in words]


def keep(seg, low_conf_logprob: float = -1.0) -> bool:
    """Layer 4: per-segment rejection."""
    text = (seg.text or "").strip()
    if not text:
        return False
    no_speech_prob = getattr(seg, "no_speech_prob", 0.0)
    if no_speech_prob > 0.5:
        return False
    if getattr(seg, "avg_logprob", 0.0) < low_conf_logprob:
        return False
    if (seg.end - seg.start) < 0.3:
        return False
    if _is_known_hallucination(text, no_speech_prob):
        return False
    return not any(p.search(text) for p in _BLOCKLIST_PATTERNS)


def is_repetitive(text: str, max_ratio: float = 0.5) -> bool:
    """Layer 5: a stuck decoder emits the same few words on loop.

    Also catches single-token character-level repetition (e.g. "μρδδδδδδδ…" seen
    when Whisper hallucinates on ambiguous audio at the start of a session): if the
    text has almost no character-level diversity relative to its length it's almost
    certainly a stuck decoder, not real speech.
    """
    words = _norm_words(text)
    if len(words) < 6:
        # Single-token hallucination check: very long "word" with near-zero char diversity.
        # Threshold: unique_chars / total_chars < 0.15 AND length > 20.
        # "μρδδδδδδδδδδδδδδδδδδδδδδδδ" → 3 unique / 26 total = 0.115 → caught.
        # "selamat sore" (12 chars, 10 unique) → 0.83 → not caught.
        stripped = text.strip()
        if len(stripped) > 20:
            diversity = len(set(stripped.lower())) / len(stripped)
            if diversity < 0.15:
                return True
        return False
    return (len(set(words)) / len(words)) < max_ratio


def cap_history(history: list[str], text: str, max_len: int = 2) -> list[str]:
    """F-1 translation context: keep only the last `max_len` final utterances per channel.

    Returns a new list (never mutates the input) so callers can hold a stable snapshot to
    pass into a background translation task while the connection's state moves on.
    """
    return (history + [text])[-max_len:]


def dedup_boundary(prev_text: str, new_text: str, max_overlap_words: int = 12) -> str:
    """Layer 6: strip the longest prev-suffix that is also a new-prefix.

    Word level rather than character level: Whisper re-punctuates and re-cases the overlap
    region between windows, so a character comparison misses almost every real duplicate.
    Returns "" when the new text is entirely contained in the previous one.
    """
    new_stripped = (new_text or "").strip()
    if not prev_text or not new_stripped:
        return new_stripped

    prev_words = (prev_text or "").strip().split()
    new_words = new_stripped.split()
    if not prev_words or not new_words:
        return new_stripped

    prev_norm = _align_norm(prev_words)
    new_norm = _align_norm(new_words)
    limit = min(len(prev_norm), len(new_norm), max_overlap_words)

    for k in range(limit, 0, -1):
        if prev_norm[-k:] == new_norm[:k]:
            return " ".join(new_words[k:]).strip()
    return new_stripped
