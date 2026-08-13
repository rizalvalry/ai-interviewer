import json
import logging
import time

import httpx

import config

log = logging.getLogger("translate")

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

SYSTEM_PROMPT = """Terjemahkan tiap ucapan wawancara kerja berbahasa Inggris berikut ke Bahasa
Indonesia. Setiap ucapan diberi angka "seq". Kembalikan HANYA array JSON berisi satu objek
{"seq": <angka>, "text": "<terjemahan>"} untuk SETIAP seq yang diberikan - tanpa penjelasan,
tanpa markdown, tanpa teks lain di luar array JSON itu.

Aturan:
- Terjemahkan makna, bukan kata per kata. Pertahankan istilah teknis, nama produk, dan
  singkatan apa adanya (jangan diterjemahkan atau dijelaskan).
- Baris [konteks] (bila ada) hanya untuk disambiguasi - JANGAN diterjemahkan ulang, jangan
  dimasukkan ke keluaran.
- Jangan menambah, mengurangi, atau menafsirkan di luar isi ucapan aslinya."""

# WI-B2 (audit v0.3.2): separate singleton from suggest.py's - different service, different
# lifecycle, no reason to share a connection pool between two logically distinct clients.
_http_client: httpx.AsyncClient | None = None


def get_http_client() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None or _http_client.is_closed:
        _http_client = httpx.AsyncClient(timeout=config.GEMINI_TIMEOUT_SEC)
    return _http_client


async def close_http_client() -> None:
    global _http_client
    if _http_client and not _http_client.is_closed:
        await _http_client.aclose()
        _http_client = None


class TranslationBatch:
    """F-1 batching (proteksi kuota harian free tier): kumpulkan utterance EN final sampai
    `max_items` tercapai atau `max_wait_sec` terlewati sejak item pertama masuk, mana dulu.

    Keputusan flush adalah fungsi murni dari state + `now` yang di-inject oleh caller, jadi
    unit-testable tanpa asyncio/timer/network nyata.
    """

    def __init__(self, max_items: int = 3, max_wait_sec: float = 4.0):
        self.max_items = max_items
        self.max_wait_sec = max_wait_sec
        self.items: list[dict] = []
        self.started_at: float | None = None

    def add(self, seq: int, text: str) -> None:
        if not self.items:
            self.started_at = time.monotonic()
        self.items.append({"seq": seq, "text": text})

    def should_flush(self, now: float) -> bool:
        if not self.items:
            return False
        if len(self.items) >= self.max_items:
            return True
        return (now - self.started_at) >= self.max_wait_sec

    def drain(self) -> list[dict]:
        items, self.items, self.started_at = self.items, [], None
        return items


def _build_batch_content(items: list[dict], context: list[str]) -> str:
    lines = [f"[konteks] {c}" for c in context]
    lines += [f'[seq={it["seq"]}] {it["text"]}' for it in items]
    return "\n".join(lines)


async def ask_translate_batch(items: list[dict], context: list[str]) -> dict:
    """items: [{"seq": int, "text": str}, ...]. Never raises - the caller schedules this as a
    fire-and-forget task and must not see an exception from a background translation."""
    if not config.GEMINI_API_KEY:
        return {"ok": False, "reason": "no-api-key"}
    if not items:
        return {"ok": False, "reason": "empty-batch"}

    body = {
        "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
        "contents": [{"role": "user", "parts": [{"text": _build_batch_content(items, context)}]}],
        "generationConfig": {
            "maxOutputTokens": 200 * len(items),
            "responseMimeType": "application/json",
        },
    }
    url = GEMINI_URL.format(model=config.GEMINI_TRANSLATE_MODEL)

    # WI-B8 (audit v0.3.2): suggest.py already retries once; this had zero attempts, so one
    # transient network blip threw away an entire batch of subtitles. Retry only on timeout
    # (a request that plausibly never reached Gemini) - not on 429 (retrying just burns more
    # quota against the same limit) and not on a bad/unparseable response (retrying an
    # already-answered request wastes a call without fixing a malformed reply).
    for attempt in (1, 2):
        try:
            client = get_http_client()
            resp = await client.post(url, params={"key": config.GEMINI_API_KEY}, json=body)
        except httpx.TimeoutException:
            log.warning("translate_timeout batch_size=%d attempt=%d", len(items), attempt)
            if attempt == 2:
                return {"ok": False, "reason": "timeout"}
            continue
        except Exception as exc:
            log.warning("translate_error batch_size=%d attempt=%d err=%s", len(items), attempt, exc)
            return {"ok": False, "reason": type(exc).__name__}

        if resp.status_code == 429:
            log.warning("translate_quota batch_size=%d attempt=%d", len(items), attempt)
            return {"ok": False, "reason": "quota"}

        try:
            resp.raise_for_status()
            data = resp.json()
            raw = data["candidates"][0]["content"]["parts"][0]["text"]
            parsed = json.loads(raw)
            translations = {int(o["seq"]): o["text"] for o in parsed}
            return {"ok": True, "translations": translations}
        except Exception as exc:
            log.warning(
                "translate_bad_response batch_size=%d attempt=%d err=%s", len(items), attempt, exc
            )
            return {"ok": False, "reason": "bad-response"}

    return {"ok": False, "reason": "timeout"}  # unreachable in practice, satisfies type checkers
