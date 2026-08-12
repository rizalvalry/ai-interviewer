import os

SR = 16000

# bug-hunter H1 (2026-08-11, confirmed): `base` measurably mis-hears short/ambiguous
# Indonesian utterances ("selamat sore" -> "Selamat sori."); `small` gets the same clip right
# without regressing English (12/12 identical on both in the eval harness). `base` remains
# selectable via env for lower-CPU laptops - see README for the latency/CPU tradeoff.
MODEL_SIZE = os.getenv("WHISPER_MODEL", "small")
COMPUTE_TYPE = os.getenv("WHISPER_COMPUTE", "int8")
DEVICE = os.getenv("WHISPER_DEVICE", "cpu")

# ctranslate2 spawns this many threads per inference. Keep threads*concurrency <= cores,
# otherwise the two inferences fight for the same cores and both miss the latency budget.
#
# bug-hunter H4 (2026-08-11, confirmed): the old default of 2 was tuned for a 2-vCPU cloud
# instance (see docs/architecture/deployment-strategy.md) and starves `small` on real
# hardware - measured 4297ms per 2.0s window (2.15x real-time, i.e. falling behind) on a
# 32-core box. 8 threads measured best (2602ms, 1.30x) - 16 was WORSE (2936ms), a real
# scaling ceiling in this backend/model, not a guess. Even at 8 threads the pipeline can
# still fall behind during sustained fast/continuous speech or when both channels talk at
# once (measured ~2x slower per call when 2 inferences run concurrently) - this is why
# METRICS.buffer_dropped_sec below exists: the residual risk is made visible, not hidden.
CPU_THREADS = int(os.getenv("WHISPER_CPU_THREADS", "8"))
MAX_CONCURRENT_ASR = int(os.getenv("MAX_CONCURRENT_ASR", "2"))

# Guide 1 targets <1.2s interim but guide 6 only fires once 2.0s has accumulated, so a
# word spoken just after a boundary waits WINDOW-OVERLAP before inference even starts.
# Lower WINDOW_SEC to close that gap at the cost of proportionally more CPU.
WINDOW_SEC = float(os.getenv("WINDOW_SEC", "2.0"))
OVERLAP_SEC = float(os.getenv("OVERLAP_SEC", "0.5"))

MAX_BUF_SEC = int(os.getenv("MAX_BUF_SEC", "30"))
IDLE_TIMEOUT_SEC = int(os.getenv("IDLE_TIMEOUT_SEC", "30"))

ENERGY_GATE_DB = float(os.getenv("ENERGY_GATE_DB", "-45.0"))
VAD_THRESHOLD = float(os.getenv("VAD_THRESHOLD", "0.5"))
# bug-hunter RC-1 (2026-08-11): -0.7 was the documented default but never reached keep() -
# now that asr.py actually wires this in, avg_logprob turned out to be too noisy a signal to
# split hairs on for this one hard case: re-synthesizing the SAME "selamat sore" text twice
# gave `small`'s CORRECT output -0.747 and -0.767 (Whisper itself is deterministic per exact
# audio bytes - the variance is TTS re-render noise, which stands in for real mic-to-mic
# variance). `base`'s WRONG mis-hear of the same clip scored -0.761/-0.802 - overlapping the
# correct range, so NO fixed threshold reliably separates them by avg_logprob alone. -0.85
# stays clear of every correct case observed (worst: -0.767) while still catching clearly
# catastrophic output (-1.0 and below). The hallucination-phrase gate below (no_speech_prob,
# a cleaner signal here: 0.015 correct vs 0.122 wrong, 8x apart) is the actual defense for
# the originally reported "Hello."/"Sorry" fillers - it does not depend on this threshold.
# Residual, accepted trade-off: `base` may still occasionally show a wrong-but-moderate-
# confidence SHORT utterance ("selamat sore"-class) - use `small` (default) to avoid it.
LOW_CONF_LOGPROB = float(os.getenv("LOW_CONF_LOGPROB", "-0.85"))

# Empty secret disables WS auth. Acceptable on localhost only: a public HF Space without
# this is an open CPU faucet for anyone who finds the URL.
AUTH_SECRET = os.getenv("AUTH_SECRET", "")
# 120 s caused permanent channel death on interviews > 2 min: WS reconnect with
# expired token -> backend 4401 -> WSManager stops retrying but channel stays DEAD.
# 7200 (2 h) covers any real interview session at localhost where the security
# trade-off is acceptable. WSManager also fetches a fresh token on every reconnect
# as a second layer of defence (ws-manager.js factory pattern).
TOKEN_TTL_SEC = int(os.getenv("TOKEN_TTL_SEC", "7200"))

# GET /dev/token mints a valid session token with no login check - it's a stand-in for the
# Laravel issuer that doesn't exist yet. Even with AUTH_SECRET set, a public Space leaves
# this reachable so anyone could self-mint a token and consume compute for free unless it's
# explicitly opted into. Default false everywhere, including localhost - set it in your own
# .env to keep using it during local dev.
ALLOW_DEV_TOKEN = os.getenv("ALLOW_DEV_TOKEN", "false").strip().lower() == "true"

# An empty AUTH_SECRET makes auth.verify() fail-open (every token accepted). That is fine on
# localhost but fatal on a public Space, so lifespan startup refuses to run with an empty
# AUTH_SECRET unless this is explicitly true. Default false everywhere, including localhost -
# set it in your own .env to keep the old no-auth localhost behavior.
ALLOW_INSECURE_NO_AUTH = os.getenv("ALLOW_INSECURE_NO_AUTH", "false").strip().lower() == "true"

# ADR Addendum 2026-08-11 (2): provider utama Gemini free tier, REST via httpx (no SDK).
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_SUGGEST_MODEL = os.getenv("GEMINI_SUGGEST_MODEL", "gemini-3.5-flash")
# flash-lite for translation: flash burns ~440 thinking tokens per one-sentence translation,
# flash-lite finishes in ~49 total - materially faster and cheaper against the free-tier
# daily quota (docs/instructions-developer-f1-f2.md).
GEMINI_TRANSLATE_MODEL = os.getenv("GEMINI_TRANSLATE_MODEL", "gemini-3.5-flash-lite")
GEMINI_TIMEOUT_SEC = float(os.getenv("GEMINI_TIMEOUT_SEC", "15"))

CORS_ORIGINS = [o for o in os.getenv("CORS_ORIGINS", "*").split(",") if o]

# ADR Addendum 2026-08-11 (3): riwayat portfolio di SQLite (stdlib), file di named volume
# (docker-compose.yml) - never a bind-mount into the repo tree, so a CV can never land in git.
PORTFOLIO_DB_PATH = os.getenv("PORTFOLIO_DB_PATH", "/home/user/data/portfolios.db")
