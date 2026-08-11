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

    try:
        async with httpx.AsyncClient(timeout=config.GEMINI_TIMEOUT_SEC) as client:
            resp = await client.post(url, params={"key": config.GEMINI_API_KEY}, json=body)
    except httpx.TimeoutException:
        log.warning("translate_timeout batch_size=%d", len(items))
        return {"ok": False, "reason": "timeout"}
    except Exception as exc:
        log.warning("translate_error batch_size=%d err=%s", len(items), exc)
        return {"ok": False, "reason": type(exc).__name__}

    if resp.status_code == 429:
        log.warning("translate_quota batch_size=%d", len(items))
        return {"ok": False, "reason": "quota"}

    try:
        resp.raise_for_status()
        data = resp.json()
        raw = data["candidates"][0]["content"]["parts"][0]["text"]
        parsed = json.loads(raw)
        translations = {int(o["seq"]): o["text"] for o in parsed}
        return {"ok": True, "translations": translations}
    except Exception as exc:
        log.warning("translate_bad_response batch_size=%d err=%s", len(items), exc)
        return {"ok": False, "reason": "bad-response"}
