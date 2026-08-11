from app import _buffer_drop_sec


def test_no_drop_when_under_max_buf():
    assert _buffer_drop_sec(combined_len=1000, max_buf=32000, sr=16000) is None


def test_no_drop_when_exactly_at_max_buf():
    assert _buffer_drop_sec(combined_len=32000, max_buf=32000, sr=16000) is None


def test_reports_dropped_seconds_when_over_max_buf():
    # 16000 samples over max_buf, at 16kHz -> exactly 1.0s silently discarded
    assert _buffer_drop_sec(combined_len=48000, max_buf=32000, sr=16000) == 1.0


def test_fractional_seconds():
    assert _buffer_drop_sec(combined_len=32800, max_buf=32000, sr=16000) == 0.05
