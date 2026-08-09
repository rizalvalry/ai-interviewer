import logging
import time

import numpy as np
from faster_whisper import WhisperModel

import config
from filters import is_repetitive, keep

log = logging.getLogger("asr")

_model: WhisperModel | None = None


def load() -> WhisperModel:
    global _model
    if _model is None:
        t0 = time.perf_counter()
        _model = WhisperModel(
            config.MODEL_SIZE,
            device=config.DEVICE,
            compute_type=config.COMPUTE_TYPE,
            cpu_threads=config.CPU_THREADS,
        )
        log.info(
            "model_loaded model=%s compute=%s threads=%d load_ms=%d",
            config.MODEL_SIZE,
            config.COMPUTE_TYPE,
            config.CPU_THREADS,
            int((time.perf_counter() - t0) * 1000),
        )
    return _model


def warmup() -> None:
    """transcribe() returns a lazy generator; the guide never consumes it, so its warmup
    does no actual work and the first real request still pays JIT + allocation cost."""
    model = load()
    t0 = time.perf_counter()
    segments, _ = model.transcribe(np.zeros(config.SR, dtype=np.float32))
    list(segments)
    log.info("warmup_done ms=%d", int((time.perf_counter() - t0) * 1000))


def transcribe_clean(audio: np.ndarray) -> tuple[list[dict], str, dict]:
    """Run one window through Whisper with every anti-hallucination decode setting on.

    Returns (segments, language, stats) where stats counts what each filter layer rejected
    so the UI overlay in guide 9 can show where text is disappearing.
    """
    model = load()
    t0 = time.perf_counter()

    segments, info = model.transcribe(
        audio,
        language=None,
        temperature=0.0,
        beam_size=1,
        best_of=1,
        word_timestamps=False,
        condition_on_previous_text=False,
        vad_filter=True,
        vad_parameters=dict(
            min_silence_duration_ms=500,
            speech_pad_ms=200,
            threshold=config.VAD_THRESHOLD,
        ),
        no_speech_threshold=0.6,
        log_prob_threshold=-1.0,
        compression_ratio_threshold=2.4,
    )

    out: list[dict] = []
    stats = {"total": 0, "rejected_keep": 0, "rejected_repetitive": 0}

    for seg in segments:
        stats["total"] += 1
        if not keep(seg):
            stats["rejected_keep"] += 1
            continue
        if is_repetitive(seg.text):
            stats["rejected_repetitive"] += 1
            continue
        out.append(
            {
                "text": seg.text.strip(),
                "conf": float(seg.avg_logprob),
                "low": seg.avg_logprob < config.LOW_CONF_LOGPROB,
            }
        )

    stats["asr_latency_ms"] = int((time.perf_counter() - t0) * 1000)
    return out, (info.language or "unknown"), stats
