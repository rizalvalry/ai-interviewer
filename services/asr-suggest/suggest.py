import asyncio
import logging

import config

log = logging.getLogger("suggest")

SYSTEM_PROMPT = """Kamu adalah asisten yang membantu KANDIDAT menjawab pertanyaan interviewer secara real time.

Aturan yang tidak boleh dilanggar:
- Gunakan HANYA isi transkrip dan portfolio yang diberikan. Jangan menambahkan fakta,
  angka, nama perusahaan, teknologi, atau klaim yang tidak ada di sana.
- Jika transkrip ambigu atau terpotong, sebutkan bagian mana yang ambigu. Jangan menebak isinya.
- Jika pertanyaan interviewer ditandai [low-confidence], JANGAN menyarankan jawaban.
  Sarankan kandidat meminta klarifikasi, dan tuliskan kalimat klarifikasinya.
- Jika portfolio tidak memuat pengalaman yang relevan, katakan itu terus terang dan sarankan
  kandidat menjawab jujur "belum pernah, tapi yang paling dekat adalah ...".
- Jawab ringkas: maksimal 4 poin, siap diucapkan, bahasa yang sama dengan pertanyaan.

Keluaran: poin-poin singkat saja, tanpa basa-basi pembuka."""

_client = None


def _get_client():
    global _client
    if _client is None:
        from anthropic import AsyncAnthropic

        _client = AsyncAnthropic(api_key=config.ANTHROPIC_API_KEY)
    return _client


def _build_user_content(question: str, utterances: list[dict], low_confidence: bool) -> str:
    # Only the last 6 turns: the full timeline costs tokens and latency, and adds noise
    # that makes the model drift toward summarizing instead of answering.
    recent = utterances[-6:]
    lines = [
        f"[{u.get('ch', '?')}]{' [low-confidence]' if u.get('low_conf') else ''} {u.get('text', '')}"
        for u in recent
        if u.get("text")
    ]
    marker = " [low-confidence]" if low_confidence else ""
    return (
        "Transkrip 6 giliran terakhir:\n"
        + ("\n".join(lines) if lines else "(belum ada)")
        + f"\n\nPertanyaan interviewer yang harus dijawab{marker}:\n{question}"
    )


async def ask_claude(
    question: str,
    utterances: list[dict],
    portfolio: str = "",
    low_confidence: bool = False,
) -> dict:
    if not config.ANTHROPIC_API_KEY:
        return {"ok": False, "reason": "no-api-key", "text": "Saran tidak tersedia."}
    if not question.strip():
        return {"ok": False, "reason": "empty-question", "text": "Saran tidak tersedia."}

    system: list[dict] = [{"type": "text", "text": SYSTEM_PROMPT}]
    if portfolio.strip():
        # Portfolio is resent every turn and never changes within a session.
        system.append(
            {
                "type": "text",
                "text": f"Portfolio kandidat:\n{portfolio.strip()}",
                "cache_control": {"type": "ephemeral"},
            }
        )

    user_content = _build_user_content(question, utterances, low_confidence)
    client = _get_client()
    last_error = "unknown"

    for attempt in (1, 2):
        try:
            resp = await asyncio.wait_for(
                client.messages.create(
                    model=config.CLAUDE_MODEL,
                    max_tokens=400,
                    system=system,
                    messages=[{"role": "user", "content": user_content}],
                ),
                timeout=config.CLAUDE_TIMEOUT_SEC,
            )
            text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
            return {"ok": True, "text": text.strip(), "attempt": attempt}
        except asyncio.TimeoutError:
            last_error = "timeout"
            log.warning("claude_timeout attempt=%d", attempt)
        except Exception as exc:
            last_error = type(exc).__name__
            log.warning("claude_error attempt=%d err=%s", attempt, exc)

    return {"ok": False, "reason": last_error, "text": "Saran tidak tersedia."}
