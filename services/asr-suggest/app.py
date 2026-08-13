import asyncio
import logging
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass, field

import numpy as np
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

import asr
import auth
import config
import portfolio_store
import suggest
import translate
from filters import cap_history, dedup_boundary, is_audible

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
log = logging.getLogger("app")

HEADER_BYTES = 8
CHANNEL_NAMES = {0: "candidate", 1: "interviewer"}

METRICS = {
    "sessions_started": 0,
    "windows_transcribed": 0,
    "windows_gated_silent": 0,
    "segments_filtered": 0,
    "frames_rejected_seq": 0,
    "llm_calls": 0,
    "llm_errors": 0,
    "asr_latency_ms_last": 0,
    # bug-hunter H4 (2026-08-11): before this, the rolling buffer truncation below silently
    # discarded audio with zero observability - "audio dibuang diam-diam" was invisible.
    "windows_dropped": 0,
    "buffer_dropped_sec": 0.0,
}


@asynccontextmanager
async def lifespan(_: FastAPI):
    if not config.AUTH_SECRET and not config.ALLOW_INSECURE_NO_AUTH:
        raise RuntimeError(
            "AUTH_SECRET is empty and ALLOW_INSECURE_NO_AUTH is not 'true' - refusing to start. "
            "Set AUTH_SECRET (production / any public Space) or ALLOW_INSECURE_NO_AUTH=true "
            "(local dev only) before starting the server."
        )
    await asyncio.to_thread(asr.warmup)
    if not config.AUTH_SECRET:
        log.warning(
            "AUTH_SECRET empty - WS/suggest auth disabled (ALLOW_INSECURE_NO_AUTH=true). "
            "Never deploy a public Space like this."
        )
    if config.ALLOW_DEV_TOKEN:
        log.warning("ALLOW_DEV_TOKEN=true - /dev/token is live. Never enable this on a public Space.")
    yield
    # WI-B2: release the persistent Gemini connection pools on shutdown instead of leaving
    # the sockets to the OS/GC.
    await suggest.close_http_client()
    await translate.close_http_client()


app = FastAPI(title="ai.interviewer ASR", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS or ["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

asr_lock = asyncio.Semaphore(config.MAX_CONCURRENT_ASR)


@dataclass
class ChannelState:
    """Per channel, never shared. The guide keeps one buffer per connection, which silently
    interleaves both speakers into one transcript if a client ever multiplexes channels."""

    buf: np.ndarray = field(default_factory=lambda: np.zeros(0, dtype=np.float32))
    last_seq: int = -1
    last_text: str = ""
    history: list = field(default_factory=list)  # F-1: last 2 final utterances, for translation context
    translation_batch: translate.TranslationBatch = field(default_factory=translate.TranslationBatch)


@app.get("/health")
async def health():
    return {"ok": True, "model": config.MODEL_SIZE, "auth": bool(config.AUTH_SECRET)}


@app.get("/metrics")
async def metrics():
    return METRICS


@app.get("/dev/token")
async def dev_token(session: str = "dev"):
    """Localhost convenience. In production this lives in Laravel behind login.

    404 (not 403) when disabled - a 403 would confirm the route exists."""
    if not config.ALLOW_DEV_TOKEN:
        raise HTTPException(status_code=404)
    return {"session": session, "token": auth.issue(session)}


class SuggestRequest(BaseModel):
    session: str = ""
    token: str = ""
    question: str
    utterances: list[dict] = []
    portfolio: str = ""
    low_confidence: bool = False


@app.post("/suggest")
async def suggest_endpoint(req: SuggestRequest):
    ok, reason = auth.verify(req.session, req.token)
    if not ok:
        log.warning("suggest_rejected session=%s reason=%s", req.session, reason)
        raise HTTPException(status_code=401, detail=reason)

    METRICS["llm_calls"] += 1
    t0 = time.perf_counter()
    result = await suggest.ask_llm(
        question=req.question,
        utterances=req.utterances,
        portfolio=req.portfolio,
        low_confidence=req.low_confidence,
    )
    result["latency_ms"] = int((time.perf_counter() - t0) * 1000)
    if not result.get("ok"):
        METRICS["llm_errors"] += 1
        # Guide 10 point 7: an LLM failure must never look like a transcription failure.
        return JSONResponse(result, status_code=200)
    return result


class PortfolioCreateRequest(BaseModel):
    session: str = ""
    token: str = ""
    name: str
    content: str


@app.get("/portfolios")
async def list_portfolios_endpoint(session: str = "", token: str = ""):
    ok, reason = auth.verify(session, token)
    if not ok:
        raise HTTPException(status_code=401, detail=reason)
    return await asyncio.to_thread(portfolio_store.list_portfolios)


@app.get("/portfolios/{portfolio_id}")
async def get_portfolio_endpoint(portfolio_id: int, session: str = "", token: str = ""):
    ok, reason = auth.verify(session, token)
    if not ok:
        raise HTTPException(status_code=401, detail=reason)
    record = await asyncio.to_thread(portfolio_store.get_portfolio, portfolio_id)
    if record is None:
        raise HTTPException(status_code=404, detail="not-found")
    return record


@app.post("/portfolios")
async def create_portfolio_endpoint(req: PortfolioCreateRequest):
    ok, reason = auth.verify(req.session, req.token)
    if not ok:
        raise HTTPException(status_code=401, detail=reason)
    error = portfolio_store.validate(req.name, req.content)
    if error:
        raise HTTPException(status_code=400, detail=error)
    return await asyncio.to_thread(portfolio_store.upsert_portfolio, req.name.strip(), req.content)


@app.delete("/portfolios/{portfolio_id}")
async def delete_portfolio_endpoint(portfolio_id: int, session: str = "", token: str = ""):
    ok, reason = auth.verify(session, token)
    if not ok:
        raise HTTPException(status_code=401, detail=reason)
    deleted = await asyncio.to_thread(portfolio_store.delete_portfolio, portfolio_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="not-found")
    return {"ok": True}


async def _flush_translation_batch(ws: WebSocket, items: list[dict], context: list[str]) -> None:
    """F-1: fire-and-forget task scheduled from the WS loop. Must never raise into the
    caller - a translation failure/timeout is a missing side message, not a stream error."""
    try:
        result = await translate.ask_translate_batch(items, context)
    except Exception:
        log.exception("translate_task_error batch_size=%d", len(items))
        return
    if not result.get("ok"):
        log.warning("translate_batch_skip batch_size=%d reason=%s", len(items), result.get("reason"))
        return
    translations = result["translations"]
    for it in items:
        text_id = translations.get(it["seq"])
        if text_id is None:
            continue
        try:
            await ws.send_json({"type": "translation", "ref": it["seq"], "text": text_id})
        except Exception:
            log.warning("translate_send_failed seq=%d", it["seq"])
            break  # ws is gone - the rest of the batch has nowhere to go either


def _buffer_drop_sec(combined_len: int, max_buf: int, sr: int) -> float | None:
    """bug-hunter H4: pure math for the rolling-buffer-overflow check, split out so the
    "audio dibuang diam-diam" detection is unit-testable without a live WS connection."""
    if combined_len <= max_buf:
        return None
    return (combined_len - max_buf) / sr


def _normalize_lang_hint(raw: str) -> str | None:
    """UI selector Auto|ID|EN (bug-hunter H3) -> Whisper's language= kwarg. Anything other
    than exactly "id"/"en" (missing, "auto", garbage) falls back to auto-detect - never
    error on an unexpected value here, this is a UX nicety, not a trust boundary."""
    return raw if raw in ("id", "en") else None


@app.websocket("/stream")
async def stream(ws: WebSocket):
    session_id = ws.query_params.get("session", "")
    token = ws.query_params.get("token", "")
    lang_hint = _normalize_lang_hint(ws.query_params.get("lang", ""))

    ok, reason = auth.verify(session_id, token)
    if not ok:
        # WI-B1 (audit v0.3.2): per RFC 6455/ASGI, a close frame can't be delivered before
        # the HTTP Upgrade completes - closing pre-accept() reaches the client as a bare
        # HTTP 403, never the 4401 code WSManager relies on to stop retrying a dead auth.
        await ws.accept()
        await ws.send_json({"type": "error", "code": 4401, "reason": reason})
        await ws.close(code=4401, reason=reason)
        log.warning("ws_rejected session=%s reason=%s", session_id, reason)
        return

    await ws.accept()
    METRICS["sessions_started"] += 1
    channels: dict[int, ChannelState] = {}
    window_len = int(config.SR * config.WINDOW_SEC)
    overlap_len = int(config.SR * config.OVERLAP_SEC)
    max_buf = config.SR * config.MAX_BUF_SEC
    next_utt_seq = 0
    # asyncio only holds a weak ref to a scheduled task - without keeping a strong ref here,
    # a translation task can be garbage-collected mid-flight ("Task was destroyed but it is
    # pending"). The done-callback keeps this set from growing for the life of the connection.
    bg_tasks: set[asyncio.Task] = set()
    log.info("ws_open session=%s", session_id)

    try:
        while True:
            message = await asyncio.wait_for(
                ws.receive(), timeout=config.IDLE_TIMEOUT_SEC
            )
            if message["type"] == "websocket.disconnect":
                break

            data = message.get("bytes")
            if data is None or len(data) <= HEADER_BYTES:
                continue

            # LOW (audit v0.3.2): named frame_seq, not seq, so it can't be confused with the
            # unrelated per-utterance seq assigned later in this same loop iteration.
            frame_seq = int.from_bytes(data[0:4], "big")
            ch_id = data[4]
            # WI-D1 (audit v0.3.2): ch_id is a raw, client-controlled byte (0-255). Only 0
            # (candidate) and 1 (interviewer) are ever meaningful - accepting anything else
            # let a malicious client allocate up to 256 ChannelState buffers per connection
            # (~488 MB) for free.
            if ch_id not in (0, 1):
                log.warning("ws_invalid_channel session=%s ch_id=%d", session_id, ch_id)
                continue
            state = channels.setdefault(ch_id, ChannelState())

            # Reconnect replays the queued frames; frame_seq makes duplicates detectable.
            if frame_seq <= state.last_seq:
                METRICS["frames_rejected_seq"] += 1
                continue
            state.last_seq = frame_seq

            # F-1 batching: checked on every frame, not only when a new segment is produced -
            # the ~4s ceiling must still fire during a pause with no new transcribed text.
            if state.translation_batch.should_flush(time.monotonic()):
                pending = state.translation_batch.drain()
                task = asyncio.create_task(
                    _flush_translation_batch(ws, pending, list(state.history))
                )
                bg_tasks.add(task)
                task.add_done_callback(bg_tasks.discard)

            pcm = np.frombuffer(data[HEADER_BYTES:], dtype=np.int16).astype(np.float32) / 32768.0
            # bug-hunter H4: when inference falls behind real-time, this buffer keeps
            # growing until it hits max_buf, at which point the OLDEST audio is silently
            # cut off - "audio dibuang diam-diam". Surface it instead of hiding it.
            dropped_sec = _buffer_drop_sec(len(state.buf) + len(pcm), max_buf, config.SR)
            if dropped_sec is not None:
                METRICS["windows_dropped"] += 1
                METRICS["buffer_dropped_sec"] += dropped_sec
                try:
                    await ws.send_json(
                        {
                            "type": "buffer_drop",
                            "ch": CHANNEL_NAMES.get(ch_id, "unknown"),
                            "dropped_sec": round(dropped_sec, 2),
                        }
                    )
                except Exception:
                    pass  # best-effort UI notice - never let this break the ASR/WS path
            state.buf = np.concatenate([state.buf, pcm])[-max_buf:]

            if len(state.buf) < window_len:
                continue

            # bug-hunter H4 root-fix (2026-08-12): the original `window = state.buf` used
            # the ENTIRE buffer (up to MAX_BUF_SEC=30s) as one Whisper call.  When inference
            # is slower than real-time (1.3x at 8 threads / model=small) the buffer grows
            # each cycle: 2s→2.6s→3.4s→…→30s, making each call proportionally slower and
            # creating a runaway positive-feedback loop.  A 30s window takes ~39s to
            # transcribe, during which another 30s of audio fills the buffer, which then
            # also overflows and loses audio silently.
            #
            # Fix: always slice exactly WINDOW_SEC of audio.  After the slice, keep the
            # tail starting at (window_len - overlap_len) so the overlap is preserved while
            # the REST of the buffer (if the pipeline is catching up from a backlog) stays
            # in state.buf and is processed on the NEXT loop iteration without being dropped.
            # This bounds inference latency at ~WINDOW_SEC regardless of backlog depth.
            window = state.buf[:window_len]
            state.buf = state.buf[window_len - overlap_len:]

            if not is_audible(window, config.ENERGY_GATE_DB):
                METRICS["windows_gated_silent"] += 1
                continue

            async with asr_lock:
                segments, lang, stats = await asyncio.to_thread(
                    asr.transcribe_clean, window, lang_hint
                )

            METRICS["windows_transcribed"] += 1
            METRICS["asr_latency_ms_last"] = stats["asr_latency_ms"]
            METRICS["segments_filtered"] += (
                stats["rejected_keep"] + stats["rejected_repetitive"]
            )

            for seg in segments:
                text = dedup_boundary(state.last_text, seg["text"])
                if not text:
                    continue
                state.last_text = seg["text"]
                # LOW (audit v0.3.2): utt_seq, not seq - the wire-protocol JSON key below
                # stays "seq" (frontend/translate.py both read that field name), only the
                # Python-local variable is renamed to avoid reading as the frame_seq above.
                utt_seq = next_utt_seq
                next_utt_seq += 1
                await ws.send_json(
                    {
                        "type": "transcript",
                        "seq": utt_seq,
                        "ch": CHANNEL_NAMES.get(ch_id, "unknown"),
                        "text": text,
                        "lang": lang,
                        "final": True,
                        "low_conf": seg["low"],
                        "conf": seg["conf"],
                        "asr_latency_ms": stats["asr_latency_ms"],
                        "t": time.time(),
                    }
                )

                # F-1: English only, queued for the batcher above - never awaited here, and
                # Indonesian speech never touches translate.py at all (nol panggilan API).
                if lang == "en" and text.strip():
                    state.translation_batch.add(utt_seq, text)
                state.history = cap_history(state.history, text)

    except (WebSocketDisconnect, asyncio.TimeoutError):
        pass
    except Exception:
        log.exception("ws_error session=%s", session_id)
    finally:
        # Candidate has left - no point paying for translations of utterances no one reads.
        for t in bg_tasks:
            t.cancel()
        dropped = sum(len(s.translation_batch.items) for s in channels.values())
        if dropped:
            log.warning("translate_batch_dropped_on_close count=%d", dropped)
        log.info("ws_close session=%s", session_id)
