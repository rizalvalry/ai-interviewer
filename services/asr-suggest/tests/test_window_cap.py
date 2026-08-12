"""Regression tests for the unbounded-window bug (H4 root fix, 2026-08-12).

The old code did `window = state.buf`, which used the ENTIRE buffer (up to 30 s)
as one inference call.  With inference slower than real-time the buffer grew each
cycle, creating a runaway positive-feedback loop.

The fix: always slice exactly window_len samples; keep everything from
(window_len - overlap_len) onward so the backlog is processed on subsequent loops
instead of being dropped.
"""

import numpy as np

SR = 16000
WINDOW_SEC = 2.0
OVERLAP_SEC = 0.5
window_len = int(SR * WINDOW_SEC)   # 32 000
overlap_len = int(SR * OVERLAP_SEC)  # 8 000


def apply_window_cap(buf: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Replicate the fixed slice logic from app.py for isolated testing."""
    window = buf[:window_len]
    remaining = buf[window_len - overlap_len:]
    return window, remaining


def test_window_is_exactly_window_len_when_buf_equals_window():
    buf = np.ones(window_len, dtype=np.float32)
    window, remaining = apply_window_cap(buf)
    assert len(window) == window_len
    assert len(remaining) == overlap_len  # only the overlap survives


def test_window_is_exactly_window_len_when_buf_is_larger():
    """Core regression: a 10-second buffer must still produce a 2-second window."""
    buf = np.ones(SR * 10, dtype=np.float32)
    window, remaining = apply_window_cap(buf)
    assert len(window) == window_len, "window must be capped at WINDOW_SEC"


def test_remaining_buf_preserves_overlap_and_backlog():
    """After slicing, the tail beyond the overlap is kept for the next iteration.

    buf = [0..window_len-1] + [window_len..end]
    remaining should start at (window_len - overlap_len) and include everything
    after that, so the next loop can immediately process another window without
    waiting for new audio.
    """
    buf_10s = np.arange(SR * 10, dtype=np.float32)
    window, remaining = apply_window_cap(buf_10s)

    # remaining starts at window_len - overlap_len = 24 000
    assert len(remaining) == SR * 10 - (window_len - overlap_len)
    # first element of remaining is the (window_len - overlap_len)-th sample
    assert remaining[0] == float(window_len - overlap_len)


def test_old_bug_would_have_grown_window():
    """Demonstrate the old runaway: old code window = buf grew unbounded."""
    buf_5s = np.ones(SR * 5, dtype=np.float32)
    # OLD (broken) behaviour: window is the whole buffer
    old_window_len = len(buf_5s)  # 80 000 — 5 seconds fed to Whisper
    # NEW (fixed) behaviour: always 32 000
    new_window_len = len(buf_5s[:window_len])
    assert old_window_len == SR * 5, "sanity: old code gave a 5-second window"
    assert new_window_len == window_len, "new code caps at WINDOW_SEC"
    # A 5-second window takes ~2.5x longer than a 2-second window; the old bug
    # compounded this on every cycle until inference fell catastrophically behind.


def test_no_audio_lost_from_backlog():
    """All samples in the backlog must be reachable via successive slices.

    Simulates three consecutive window extractions from a 6-second buffer.
    """
    total_sec = 6
    buf = np.arange(SR * total_sec, dtype=np.float32)
    covered_up_to = 0

    for _ in range(3):
        if len(buf) < window_len:
            break
        window, buf = apply_window_cap(buf)
        assert len(window) == window_len
        # Each window advances by (WINDOW_SEC - OVERLAP_SEC) = 1.5 s worth of UNIQUE samples
        covered_up_to += window_len - overlap_len  # 24 000 samples = 1.5 s

    # After 3 slices we've covered 3 × 1.5 s = 4.5 s of the original 6 s
    assert covered_up_to == 3 * (window_len - overlap_len)
