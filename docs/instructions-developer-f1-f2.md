# Instruksi Developer — F-1 Terjemahan Realtime & F-2 Upload Portfolio PDF

> Handoff dari `project-manager` + strategi dari `ai-engineer`. Ditulis: 2026-08-11.
> Prasyarat: stack localhost (WI-1..5) sudah accepted. Kerjakan di atasnya.
> Keputusan strategi AI di bawah milik `ai-engineer` — jangan diganti tanpa kembali ke PM.

---

## Konteks keputusan (sudah diputuskan)

- **F-1:** terjemahan tampil BERSEBELAHAN dengan transkrip (bukan menggantikan).
  Percakapan Inggris → terjemahan Indonesia. Percakapan Indonesia → tanpa terjemahan.
  Model: **`claude-haiku-4-5`**, async, non-blocking, hanya utterance final.
- **F-2:** PDF text-based multi-halaman → ekstraksi teks **client-side** → full inject ke
  field `portfolio` yang sudah ada. TANPA chunking, TANPA RAG, TANPA endpoint upload baru.
- API key: user memakai Anthropic Console (bukan Claude Pro). `ANTHROPIC_API_KEY` di `.env`
  sudah menjadi jalurnya — tidak ada perubahan konfigurasi.

---

## Work items

### WI-7 — F-1 backend: terjemahan per utterance final
- Titik pasang: setelah utterance final dikirim di WS `/stream` (`app.py`), bila
  `language == "en"` (sudah tersedia dari `asr.transcribe_clean`, lihat `asr.py:93`),
  jadwalkan task async terjemahan; kirim hasil sebagai pesan WS terpisah yang mereferensikan
  utterance-nya (mis. `{type: "translation", ref_seq: ..., text_id: ...}`).
- Panggilan Claude: `claude-haiku-4-5`, system prompt pendek (versi file, bukan string
  inline) dengan `cache_control: {"type": "ephemeral"}`, konteks = utterance + maks 2
  utterance sebelumnya, `max_tokens` kecil (≤300).
- WAJIB non-blocking: kegagalan/timeout terjemahan TIDAK boleh menyentuh jalur ASR/WS
  utama; tanpa retry blocking; log warning saja.
- **Done:** percakapan EN memunculkan terjemahan ID di samping transkrip ≤3s setelah
  utterance final; percakapan ID tidak memicu panggilan API sama sekali; mematikan
  `ANTHROPIC_API_KEY` tidak merusak transkrip.

### WI-8 — F-1 frontend: kolom terjemahan
- Timeline menampilkan terjemahan bersebelahan/di bawah utterance yang sama (ikuti pola
  batching rAF yang sudah ada di `timeline.js` — jangan render per pesan WS).
- **Done:** terjemahan muncul menempel pada utterance yang benar, tanpa menggeser/merusak
  urutan transkrip.

### WI-9 — F-2: upload/browse PDF portfolio
- Input file di `index.html` (menggantikan/melengkapi textarea `#portfolio`), ekstraksi
  teks client-side (pdf.js atau setara — pilihan dan pinning versi milikmu, catat sebagai
  assumption; ingat CSP/serving lokal, bundel librarynya, jangan CDN agar tetap offline-friendly).
- Hasil ekstraksi diisikan ke textarea (tetap editable) → mengalir ke field `portfolio`
  `/suggest` yang sudah ada. Backend TIDAK berubah untuk jalur data.
- Guard: bila hasil ekstraksi >30.000 karakter, potong + tampilkan peringatan di UI.
- **Done:** pilih PDF text-based multi-halaman → teks muncul di textarea → `/suggest`
  menjawab dengan mengutip isi CV; PDF hasil scan (tanpa teks) menghasilkan pesan error
  yang jelas, bukan kegagalan diam-diam.

### WI-10 — Optimasi biaya `/suggest` (satu perubahan kecil, wajib)
- Di `suggest.py`, tambahkan `cache_control: {"type": "ephemeral"}` pada blok system
  portfolio (dan blok SYSTEM_PROMPT) supaya CV yang menumpang di setiap panggilan
  ter-cache (~0.1× harga baca).
- **Done:** dua panggilan `/suggest` berurutan dengan portfolio sama menunjukkan
  `cache_read_input_tokens > 0` pada panggilan kedua (log usage-nya).

### WI-11 — Housekeeping (temuan Low dari acceptance sebelumnya)
- `.env.example`: ubah `ALLOW_INSECURE_NO_AUTH=true` → `false` dan koreksi komentarnya
  (flag `true` justru MEMATIKAN guard fail-loud; dengan `AUTH_SECRET` default non-kosong,
  `false` adalah nilai aman).
- **Done:** satu baris berubah, komentar akurat, stack tetap start normal dari
  `cp .env.example .env`.

### WI-12 — Verifikasi
- Test suite lolos penuh (baseline 22, tambah test unit untuk fungsi baru yang murni —
  mis. pemotongan 30K char, pemilihan konteks utterance).
- Smoke end-to-end via compose: alur interview EN dengan terjemahan + upload CV + saran.
- **Done:** bukti output test + smoke dicantumkan di laporan.

---

## Batasan
- JANGAN menerjemahkan hasil interim; hanya final.
- JANGAN memblokir pipeline ASR/WS demi terjemahan — augmentasi, bukan jalur kritis.
- JANGAN menambah chunking/embedding/RAG untuk portfolio.
- JANGAN membuat endpoint upload file di backend.
- JANGAN mengubah model `/suggest` (`CLAUDE_MODEL` tetap dari env).
- Prompt terjemahan disimpan sebagai file/konstanta terversi, bukan string sebar.
- Disiplin versioning sama seperti sebelumnya: pull dulu, satu commit per WI, push per WI
  selesai, tag `v0.3.0` saat WI-7..12 terverifikasi end-to-end.

## Acceptance criteria PM
- [ ] Interview EN: terjemahan ID tampil di samping ≤3s, urutan transkrip utuh.
- [ ] Interview ID: nol panggilan API terjemahan (verifikasi via log/metrics).
- [ ] API mati ≠ transkrip mati (graceful degrade terbukti).
- [ ] CV PDF multi-halaman terbaca dan dikutip benar oleh `/suggest`.
- [ ] `cache_read_input_tokens > 0` pada panggilan `/suggest` kedua.
- [ ] `.env.example` fix WI-11 masuk.
- [ ] Semua commit ter-push + tag `v0.3.0`.
