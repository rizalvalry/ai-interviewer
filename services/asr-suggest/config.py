import os

SR = 16000

MODEL_SIZE = os.getenv("WHISPER_MODEL", "base")
COMPUTE_TYPE = os.getenv("WHISPER_COMPUTE", "int8")
DEVICE = os.getenv("WHISPER_DEVICE", "cpu")

# ctranslate2 spawns this many threads per inference. Keep threads*concurrency <= cores,
# otherwise the two inferences fight for the same cores and both miss the latency budget.
CPU_THREADS = int(os.getenv("WHISPER_CPU_THREADS", "2"))
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
LOW_CONF_LOGPROB = float(os.getenv("LOW_CONF_LOGPROB", "-0.7"))

# Empty secret disables WS auth. Acceptable on localhost only: a public HF Space without
# this is an open CPU faucet for anyone who finds the URL.
AUTH_SECRET = os.getenv("AUTH_SECRET", "")
TOKEN_TTL_SEC = int(os.getenv("TOKEN_TTL_SEC", "120"))

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

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-5")
CLAUDE_TIMEOUT_SEC = float(os.getenv("CLAUDE_TIMEOUT_SEC", "15"))

CORS_ORIGINS = [o for o in os.getenv("CORS_ORIGINS", "*").split(",") if o]
