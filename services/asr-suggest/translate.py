import asyncio
import logging

import config

log = logging.getLogger("translate")

# ai-engineer decision (docs/instructions-developer-f1-f2.md): fixed to haiku regardless of
# CLAUDE_MODEL - translation is a cheap, high-volume side call and must not inherit whatever
# (possibly larger/pricier) model /suggest is configured with.
MODEL = "claude-haiku-4-5"
MAX_TOKENS = 300

SYSTEM_PROMPT = """Terjemahkan ucapan wawancara kerja berikut dari Bahasa Inggris ke Bahasa Indonesia.

Aturan yang tidak boleh dilanggar:
- Giliran-giliran sebelumnya hanya konteks untuk disambiguasi. JANGAN menerjemahkannya ulang -
  keluarkan HANYA terjemahan giliran TERAKHIR yang ditandai [terjemahkan].
- Terjemahkan makna, bukan kata per kata. Pertahankan istilah teknis, nama produk, dan
  singkatan apa adanya (jangan diterjemahkan atau dijelaskan).
- Jangan menambah, mengurangi, atau menafsirkan di luar isi ucapan aslinya.

Keluaran: teks terjemahan saja, tanpa tanda kutip, tanpa embel-embel pembuka."""


_client = None


def _get_client():
    global _client
    if _client is None:
        from anthropic import AsyncAnthropic

        _client = AsyncAnthropic(api_key=config.ANTHROPIC_API_KEY)
    return _client


def _build_user_content(text: str, context: list[str]) -> str:
    lines = [f"[konteks] {c}" for c in context]
    lines.append(f"[terjemahkan] {text}")
    return "\n".join(lines)


async def ask_translate(text: str, context: list[str]) -> dict:
    """Translate one final EN utterance to ID. Never raises - the WS loop that schedules this
    as a fire-and-forget task must not see an exception from a background translation."""
    if not config.ANTHROPIC_API_KEY:
        return {"ok": False, "reason": "no-api-key"}
    if not text.strip():
        return {"ok": False, "reason": "empty-text"}

    system = [{"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}]
    user_content = _build_user_content(text, context)
    client = _get_client()

    try:
        resp = await asyncio.wait_for(
            client.messages.create(
                model=MODEL,
                max_tokens=MAX_TOKENS,
                system=system,
                messages=[{"role": "user", "content": user_content}],
            ),
            timeout=config.CLAUDE_TIMEOUT_SEC,
        )
        out = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
        return {"ok": True, "text": out.strip()}
    except asyncio.TimeoutError:
        log.warning("translate_timeout")
        return {"ok": False, "reason": "timeout"}
    except Exception as exc:
        log.warning("translate_error err=%s", exc)
        return {"ok": False, "reason": type(exc).__name__}
