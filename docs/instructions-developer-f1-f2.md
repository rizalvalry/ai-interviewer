# Instruksi Developer — Migrasi Provider ke Gemini + F-1 Terjemahan Realtime + F-2 Upload Portfolio PDF

> ⚠️ **REVISI TOTAL 2026-08-11 (sore): provider berubah Anthropic → Google Gemini free tier.**
> Kalau kamu sempat membaca/mengerjakan versi sebelumnya (berbasis claude-haiku/cache_control),
> BUANG versi itu — dokumen ini menggantikannya sepenuhnya.
> Keputusan provider: `solution-architect` (ADR Addendum 2026-08-11 (2)). Strategi model:
> `ai-engineer`. Jangan diganti tanpa kembali ke PM.

---

## Konteks keputusan (sudah diputuskan & diuji)

- Provider utama: **Gemini API free tier** (key user sudah terpasang di `.env` sebagai
  `GEMINI_API_KEY`). Uji nyata 2026-08-11: auth ✓, burst 15/15 ✓, kualitas ✓.
- Pemetaan model (JANGAN diubah):
  - `/suggest` → **`gemini-3.5-flash`**
  - Terjemahan F-1 → **`gemini-3.5-flash-lite`** (flash penuh membakar ratusan token
    thinking per translasi — lambat & boros kuota)
- `gemini-2.5-flash` TIDAK tersedia untuk akun ini (ditutup untuk akun baru) — jangan dipakai.
- Panggil via **REST `generativelanguage.googleapis.com/v1beta` dengan `httpx`** yang sudah
  ada di requirements — JANGAN menambah SDK `google-genai` (hemat dependency & image).
  Endpoint terverifikasi: `POST /v1beta/models/{model}:generateContent?key=...` dengan
  `systemInstruction` + `contents`.
- F-1: terjemahan tampil BERSEBELAHAN dengan transkrip. EN → terjemahan ID; percakapan ID →
  tanpa terjemahan. Hanya utterance FINAL. Async, non-blocking.
- F-2: PDF text-based → ekstraksi client-side → full inject ke field `portfolio` yang sudah
  ada. TANPA chunking/RAG, TANPA endpoint upload backend.

---

## Work items

### WI-7 — Migrasi `/suggest` ke Gemini
- Ganti implementasi `suggest.py`: SDK `anthropic` → panggilan REST Gemini
  (`gemini-3.5-flash`) via `httpx` (async, timeout dari env). Pertahankan kontrak fungsi
  `ask_claude(...)`-nya (boleh rename ke `ask_llm`, update pemanggil) dan bentuk respons
  `/suggest` — frontend TIDAK berubah.
- System prompt yang ada dipindahkan ke `systemInstruction`; blok portfolio tetap terpisah
  dan stabil urutannya (prefix stabil = kena implicit caching Gemini otomatis).
- Config: `GEMINI_API_KEY`, `GEMINI_SUGGEST_MODEL` (default `gemini-3.5-flash`),
  `GEMINI_TRANSLATE_MODEL` (default `gemini-3.5-flash-lite`) di `config.py`.
  `ANTHROPIC_API_KEY`/`CLAUDE_MODEL` dihapus dari config; dependency `anthropic` dihapus
  dari `requirements.txt`. Perilaku key-kosong tetap graceful (ok:false, reason:no-api-key).
- Error mapping: HTTP 429 (kuota) → respons `ok:false, reason:"quota"` — bukan crash.
- **Done:** `/suggest` dengan token valid + portfolio → saran berbahasa Indonesia grounded
  ke portfolio; tanpa key → graceful; 22 test lama tetap lolos (sesuaikan test yang
  menyentuh provider).

### WI-8 — F-1 backend: terjemahan per utterance final (Gemini flash-lite)
- Titik pasang: setelah utterance final terkirim di WS `/stream` (`app.py`); bahasa sudah
  tersedia dari `asr.transcribe_clean` (`asr.py:93`). `language == "en"` → jadwalkan task
  async; `id` → tidak ada panggilan sama sekali.
- **Batching wajib** (proteksi kuota harian free tier): kumpulkan utterance final EN dalam
  jendela pendek (mis. 2–3 utterance atau maks ~4 detik, mana yang tercapai dulu) → satu
  panggilan `gemini-3.5-flash-lite` menerjemahkan batch → kirim hasil per-utterance sebagai
  pesan WS terpisah `{type:"translation", ref: <id utterance>, text: ...}`.
- Non-blocking mutlak: kegagalan/timeout/429 → log warning, transkrip jalan terus, tanpa
  retry blocking.
- Prompt terjemahan = konstanta/file terversi, bukan string sebar.
- **Done:** percakapan EN memunculkan terjemahan ID ≤5s setelah utterance final (batching
  boleh menambah ~2s vs spec lama); percakapan ID = nol panggilan API (buktikan via
  log/metrics); mencabut `GEMINI_API_KEY` tidak merusak transkrip.

### WI-9 — F-1 frontend: kolom terjemahan
- Timeline menampilkan terjemahan menempel pada utterance yang benar (pakai `ref`), ikuti
  pola batching rAF yang sudah ada di `timeline.js`.
- **Done:** terjemahan muncul di utterance yang tepat tanpa merusak urutan transkrip.

### WI-10 — F-2: upload/browse PDF portfolio
- Input file di `index.html` (melengkapi textarea `#portfolio`), ekstraksi teks client-side
  (pdf.js atau setara — pilihan & pinning versi milikmu, catat sebagai assumption; bundel
  library lokal, jangan CDN, agar tetap jalan offline).
- Hasil ekstraksi mengisi textarea (tetap editable) → mengalir ke field `portfolio`
  `/suggest` yang sudah ada. Backend tidak berubah untuk jalur data.
- Guard: >30.000 karakter → potong + peringatan di UI. PDF hasil scan (tanpa teks) → pesan
  error jelas, bukan kegagalan diam.
- **Done:** PDF multi-halaman → teks di textarea → `/suggest` mengutip isi CV dengan benar.

### WI-11 — Housekeeping env
- `.env.example`: tambah `GEMINI_API_KEY=` (kosong, wajib isi), `GEMINI_SUGGEST_MODEL`,
  `GEMINI_TRANSLATE_MODEL`; hapus `ANTHROPIC_API_KEY`/`CLAUDE_MODEL`; ubah
  `ALLOW_INSECURE_NO_AUTH=true` → `false` + koreksi komentarnya (flag `true` justru
  MEMATIKAN guard fail-loud; dengan `AUTH_SECRET` default non-kosong, `false` yang aman).
- README: sebutkan `GEMINI_API_KEY` sebagai satu-satunya kredensial yang perlu diisi.
- **Done:** `cp .env.example .env` + isi `GEMINI_API_KEY` = konfigurasi lengkap.

### WI-12 — Verifikasi + eval mini
- Test suite lolos penuh (baseline 22 + test baru untuk logika murni: batching window,
  pemotongan 30K char, error mapping 429).
- Smoke end-to-end via compose: interview EN → transkrip + terjemahan + upload CV + saran.
- **Eval mini F-1 (dari `ai-engineer`):** 20 utterance EN domain interview → terjemahan ID;
  spot-check manual, catat yang janggal. Bukan test otomatis — lampirkan tabelnya di laporan.
- **Done:** bukti test + smoke + tabel eval dicantumkan di laporan.

---

## Batasan
- JANGAN pakai model selain pemetaan di atas; JANGAN pakai `gemini-2.5-flash`.
- JANGAN menambah SDK Google; REST via `httpx`.
- JANGAN menerjemahkan interim; JANGAN memblokir pipeline ASR/WS.
- JANGAN chunking/embedding/RAG untuk portfolio; JANGAN endpoint upload backend.
- Key TIDAK pernah dikirim ke frontend/browser — semua panggilan Gemini dari backend.
- Disiplin versioning: pull dulu, satu commit per WI, push per WI selesai, tag `v0.3.0`
  saat WI-7..12 terverifikasi end-to-end.

## Acceptance criteria PM
- [ ] `/suggest` jalan penuh di Gemini; dependency `anthropic` hilang dari requirements.
- [ ] Interview EN: terjemahan ID tampil ≤5s, urutan transkrip utuh; interview ID: nol
      panggilan terjemahan.
- [ ] 429/kuota habis/key dicabut → transkrip tetap hidup (graceful degrade terbukti).
- [ ] CV PDF multi-halaman terbaca dan dikutip benar oleh `/suggest`.
- [ ] `.env.example` bersih (Gemini-only + fix ALLOW_INSECURE_NO_AUTH).
- [ ] Tabel eval mini 20 terjemahan terlampir.
- [ ] Semua commit ter-push + tag `v0.3.0`.
