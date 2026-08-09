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
import suggest
from filters import dedup_boundary, is_audible

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
    "claude_calls": 0,
    "claude_errors": 0,
    "asr_latency_ms_last": 0,
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

    METRICS["claude_calls"] += 1
    t0 = time.perf_counter()
    result = await suggest.ask_claude(
        question=req.question,
        utterances=req.utterances,
        portfolio=req.portfolio,
        low_confidence=req.low_confidence,
    )
    result["latency_ms"] = int((time.perf_counter() - t0) * 1000)
    if not result.get("ok"):
        METRICS["claude_errors"] += 1
        # Guide 10 point 7: a Claude failure must never look like a transcription failure.
        return JSONResponse(result, status_code=200)
    return result


@app.websocket("/stream")
async def stream(ws: WebSocket):
    session_id = ws.query_params.get("session", "")
    token = ws.query_params.get("token", "")

    ok, reason = auth.verify(session_id, token)
    if not ok:
        await ws.close(code=4401, reason=reason)
        log.warning("ws_rejected session=%s reason=%s", session_id, reason)
        return

    await ws.accept()
    METRICS["sessions_started"] += 1
    channels: dict[int, ChannelState] = {}
    window_len = int(config.SR * config.WINDOW_SEC)
    overlap_len = int(config.SR * config.OVERLAP_SEC)
    max_buf = config.SR * config.MAX_BUF_SEC
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

            seq = int.from_bytes(data[0:4], "big")
            ch_id = data[4]
            state = channels.setdefault(ch_id, ChannelState())

            # Reconnect replays the queued frames; seq makes duplicates detectable.
            if seq <= state.last_seq:
                METRICS["frames_rejected_seq"] += 1
                continue
            state.last_seq = seq

            pcm = np.frombuffer(data[HEADER_BYTES:], dtype=np.int16).astype(np.float32) / 32768.0
            state.buf = np.concatenate([state.buf, pcm])[-max_buf:]

            if len(state.buf) < window_len:
                continue

            window = state.buf
            state.buf = state.buf[-overlap_len:].copy()

            if not is_audible(window, config.ENERGY_GATE_DB):
                METRICS["windows_gated_silent"] += 1
                continue

            async with asr_lock:
                segments, lang, stats = await asyncio.to_thread(asr.transcribe_clean, window)

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
                await ws.send_json(
                    {
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

    except (WebSocketDisconnect, asyncio.TimeoutError):
        pass
    except Exception:
        log.exception("ws_error session=%s", session_id)
    finally:
        log.info("ws_close session=%s", session_id)
