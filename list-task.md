# Task List — Project (PM-owned)

> Master ledger. PM owns this file. Skill-level task lists are sub-logs.
> Checklist: [ ] = belum, [x] = done, [!] = perlu perbaikan/fixing

---

## [2026-08-09 18:00] — Evaluasi deployment strategy (Vercel/Hugging Face/Hostinger) untuk project ai.interviewer

**Intake class:** Single-owner
**Status keseluruhan:** `done`
**RAG:** 🟢 Green

### Delegation
| # | Work item | Owner skill | Subagent (model) | Depends on | DoR | Status |
|---|-----------|-------------|-------------------|------------|-----|--------|
| 1 | Evaluasi topologi cloud (Vercel/HF/Hostinger) + tradeoff | solution-architect | inherits caller | codebase existing (server/, web/, .env.example, guide doc) | [x] | done |

### Handoff artifacts required
- [x] Solution Architect decision (7 domain + tradeoff table) — dari `solution-architect` → PM: **accepted**, semua domain diisi, sacrifices eksplisit ada.

### RAID
- **A:** Skala target (personal tool vs multi-user) belum dikonfirmasi user — confidence L — verify by: tanya user langsung sebelum commit ke HF free tier jangka panjang.
- **D:** Custom domain HF Space butuh HF PRO (berbayar) — blocked on: keputusan budget dari user.
- **I:** `/dev/token` endpoint tanpa guard environment, `AUTH_SECRET` fail-open bila kosong — owner: security-reviewer (belum dijadwalkan) | due: sebelum go-live publik.

### Gate log
- [x] DoR passed — 2026-08-09 18:00
- [x] DoD passed — 2026-08-09 18:10 (7 domain lengkap, tradeoff table ada, hand-off jelas)
- [x] Go / No-go — **Go** untuk lanjut ke dokumentasi + restrukturisasi. Belum go untuk deploy publik (lihat RAID di atas).

---

## [2026-08-09 18:15] — Tuangkan keputusan arsitektur ke dokumen .md dan rapikan struktur workspace sesuai mapping fungsional

**Intake class:** Multi-skill
**Status keseluruhan:** `done`
**RAG:** 🟢 Green

### Delegation
| # | Work item | Owner skill | Subagent (model) | Depends on | DoR | Status |
|---|-----------|-------------|-------------------|------------|-----|--------|
| 1 | Tulis `docs/architecture/deployment-strategy.md` | solution-architect | — (persist keputusan existing) | Task #1 di atas (keputusan sudah ada) | [x] | done |
| 2 | Restrukturisasi folder (`web/`→`frontend/`, `server/`→`services/asr-suggest/`, placeholder `services/auth-laravel/`, guide→`docs/`) + update `run-dev.ps1`/`.env.example` | developer | `skill-ai:developer` (sonnet) | Artifact #1 (dokumen mapping) | [x] | done |

### Handoff artifacts required
- [x] `docs/architecture/deployment-strategy.md` — dari `solution-architect` → `developer`: **present**, jadi kontrak mapping folder.
- [x] Repository search + change impact analysis + assumptions + verification checklist — dari `developer` → PM: **accepted**. Test suite 22/22 passed, live health-check 200 OK, PowerShell syntax OK, tidak ada breaking reference tersisa.

### RAID
- **R:** Repo tanpa git (tidak ada `.git` di root project, hanya di `skill_ai/`) — tidak ada safety net rollback otomatis untuk move ini — detection: manual verify (sudah dilakukan) | mitigation: pertimbangkan `git init` di root project sebelum perubahan besar berikutnya.
- **A:** `skill_ai/` di root workspace adalah repo terpisah (plugin cache), bukan bagian dari `ai.interviewer` — confidence H — diverifikasi developer via `.git`/marketplace.json miliknya sendiri.

### Gate log
- [x] DoR passed — 2026-08-09 18:15 (mapping doc ada sebelum developer mulai)
- [x] DoD passed — 2026-08-09 18:40 (structure diverifikasi PM langsung via file listing, sesuai mapping di dokumen)
- [x] Go / No-go — **Go**, restrukturisasi selesai dan terverifikasi.

### Catatan Perbaikan
- (tidak ada — tidak ada [!] item)

---

## [2026-08-09 19:00] — Scaffold deploy config (Vercel/HF Space) + security review + terjemahkan seluruh dokumentasi ke Bahasa Indonesia

**Intake class:** Multi-skill
**Status keseluruhan:** `needs-fix`
**RAG:** 🔴 Red

### Delegation
| # | Work item | Owner skill | Subagent (model) | Depends on | DoR | Status |
|---|-----------|-------------|-------------------|------------|-----|--------|
| 1 | Scaffold Dockerfile/README HF Space, vercel.json, .gitignore, git init, checklist env var, guard `/dev/token` | developer | `skill-ai:developer` (sonnet) | mapping folder sudah ada | [x] | done |
| 2 | Review keamanan perubahan auth (`/dev/token` guard) sebelum diterima | security-reviewer | inherits caller | diff dari item #1 | [x] | done |
| 3 | Terjemahkan `docs/deployment-checklist.md`, `services/asr-suggest/README.md`, sinkronkan `docs/architecture/deployment-strategy.md` ke path final + status keamanan terkini | (dokumentasi langsung, tidak ada konflik owner) | — | hasil review #2 | [x] | done |

### Handoff artifacts required
- [x] Verification checklist dari `developer` — **accepted**, 22/22 test lolos, Docker build tidak terverifikasi (Docker tidak tersedia di environment ini, sudah didisclosure eksplisit, bukan diklaim berhasil).
- [x] Finding report dari `security-reviewer` — **accepted**, format lengkap (severity, evidence, fix guidance, verification steps).

### RAID
- **I (Critical, live):** `POST /suggest` di `services/asr-suggest/app.py:98-113` tidak ada pengecekan token sama sekali — owner: `developer` | due: sebelum Space diset Public.
- **I (Critical, live):** `AUTH_SECRET` fail-open (`auth.py:20-21`) hanya menghasilkan warning log, tidak menolak start — owner: `developer` | due: sebelum Space diset Public.
- **I (High, live):** Trap sequencing — `/dev/token` harus aktif (`ALLOW_DEV_TOKEN=true`) agar app berfungsi untuk user asli selama Laravel belum ada, tapi itu sama terbukanya untuk siapa pun — owner: `solution-architect` (putuskan strategi mitigasi) + `project-manager`/user (keputusan scope: Space Private dulu). Mitigasi sementara sudah didokumentasikan: **gunakan Space Private**.
- **D:** Perbaikan #2 dan #3 di atas memblokir langkah "buat Space Public" di `docs/deployment-checklist.md` — blocked on: developer fix + re-review security-reviewer.

### Gate log
- [x] DoR passed — 2026-08-09 19:00
- [!] DoD **FAIL** — security-reviewer verdict: FAIL (2 Critical, 1 High). Scaffolding secara teknis lengkap dan terverifikasi, tapi tidak "done" untuk tujuan deploy publik.
- [x] Go / No-go — **Go untuk Space Private/testing terbatas. No-go untuk Space Public** sampai RAID Critical di atas selesai.

### Catatan Perbaikan
- [!] `services/asr-suggest/app.py` — tambahkan pengecekan token di `/suggest` (samakan dengan `/stream`). Owner: `developer`.
- [!] `services/asr-suggest/app.py` / `config.py` — startup harus fail-loud (bukan cuma warning) saat `AUTH_SECRET` kosong di environment non-lokal. Owner: `developer`.
- [!] Keputusan strategi mitigasi trap sequencing (`/dev/token` vs Laravel belum ada) — Owner: `solution-architect` + konfirmasi user.

---

## [2026-08-11 11:30] — Pivot topologi ke localhost-first (Docker on-demand) + instruksi developer + disiplin versioning GitHub

**Intake class:** Multi-skill
**Status keseluruhan:** `in-progress`
**RAG:** 🟢 Green
**Refs:** #2026-08-09 (deployment strategy — keputusan cloud DITUNDA via addendum ADR)

### Konteks keputusan
- HF berubah kebijakan: Docker Space kini butuh PRO $9/bln (diverifikasi dari docs resmi HF, 2026-08-11). Asumsi "HF gratis" gugur.
- User memutuskan: jalankan semua di localhost via Docker, start on-demand saat interview, berpindah-pindah laptop. Vercel/HF/tunnel tidak dipakai.
- Database: TIDAK diperlukan (asr-suggest stateless; auth-laravel tetap placeholder). MySQL cPanel baru relevan jika kelak butuh data persisten lintas laptop.
- Koreksi RAID lama: 2 temuan Critical (#/suggest tanpa token, #AUTH_SECRET fail-open) ternyata SUDAH diperbaiki di kode (app.py:111 verifikasi token; config.py ALLOW_INSECURE_NO_AUTH fail-loud gate). Entri Catatan Perbaikan 2026-08-09 dianggap selesai; validasi ulang formal oleh security-reviewer tidak lagi memblokir karena tidak ada eksposur publik.

### Delegation
| # | Work item | Owner skill | Subagent (model) | Depends on | DoR | Status |
|---|-----------|-------------|------------------|-----------|-----|--------|
| 1 | Addendum ADR pivot localhost-first | solution-architect | inherits caller | fakta pricing HF + konfirmasi user | [x] | done |
| 2 | Instruksi developer (docs/instructions-developer-local.md) | project-manager | — | #1 | [x] | done |
| 3 | WI-1..5: docker-compose, .env.example, README quickstart, run-dev.ps1, verifikasi | developer | developer (sonnet) | #2 | [x] | **done — accepted 2026-08-11** |
| 4 | WI-6 (opsional): bake model + Docker Hub | developer | developer (sonnet) | #3 diterima | [ ] | deferred |

### Handoff artifacts required
- [x] Addendum ADR — dari `solution-architect` → semua: ada di docs/architecture/deployment-strategy.md (Addendum 2026-08-11)
- [x] Handoff package — dari `project-manager` → `developer`: docs/instructions-developer-local.md (work items, done conditions, acceptance criteria, aturan versioning)

### RAID
- **R:** Port binding compose default 0.0.0.0 akan mengekspos service tanpa-auth ke LAN — detection: `docker ps` menunjukkan binding | mitigation: instruksi mewajibkan `127.0.0.1:...` (hard rule di instruksi developer).
- **A:** Kebutuhan tetap personal/single-user — confidence H (dikonfirmasi user 2026-08-11) — verify by: revisit jika user menyebut kandidat/multi-user mengakses langsung.
- **A:** Laptop-laptop target sanggup inference Whisper `base` int8 CPU — confidence M — verify by: smoke test di laptop kedua saat WI-5.
- **D:** WI-3..5 bergantung pada WI-1/WI-2 (compose + env template harus ada dulu).

### Scope control
- **In:** compose stack localhost, .env template, README quickstart, disiplin git push berkala ke origin.
- **Deferred:** WI-6 bake model/Docker Hub (opsional, setelah WI-1..5 diterima); MySQL/Laravel auth (tunggu kebutuhan data lintas laptop nyata); deploy cloud apa pun (revisit: VPS ~$4–9/bln bila jadi multi-user).
- **Rejected:** Vercel sebagai host backend Docker (3 blocker teknis: no container runtime, no WS Python, size/state limit — lihat ADR).

### Gate log
- [x] DoR untuk delegasi ke developer — 2026-08-11 11:30 (owner tunggal jelas, artefak input lengkap, done condition konkret, model pinned: sonnet)
- [x] DoD **PASS** — 2026-08-11. Diverifikasi independen oleh PM (bukan hanya laporan): compose binding 127.0.0.1 kedua service, .env ter-gitignore, 22/22 test in-container, smoke 401/403 negatif, 4 commit per-WI ter-push, tag v0.2.0 ter-push. Handoff contract developer lengkap (repo search, impact analysis, assumptions terpisah dari fakta, verification checklist dieksekusi nyata).
- [x] Go / No-go — **Go untuk pemakaian**. Catatan residual: bukti final portabilitas = setup nyata di laptop kedua (baru disimulasikan via copy-env); bila gagal di sana, itu regresi acceptance.

### Temuan pasca-acceptance (tidak memblokir)
- **Low:** `ALLOW_INSECURE_NO_AUTH=true` di `.env.example` mematikan guard fail-loud config.py; dengan `AUTH_SECRET` kini default non-kosong, nilai benar = `false`. Akar: instruksi WI-2 PM ditulis dengan asumsi secret kosong. Owner fix: `developer` (satu baris + koreksi komentar), pass berikutnya.

### Status keseluruhan (update 2026-08-11 sore): `done` — kecuali item deferred
- WI-6 (bake model + Docker Hub): deferred, menunggu keputusan user.
- Test otomatis auth gate `/suggest` + `/stream` handshake: kandidat `qa-analysis` (gap dicatat developer, smoke manual sudah membuktikan perilaku).

### Next action
Keputusan user: (a) kerjakan WI-6 opsional, (b) commission `qa-analysis` untuk test auth gate permanen, atau (c) cukup — pakai stack untuk interview.

---

## [2026-08-11 14:00] — Fitur F-1 (terjemahan realtime side-by-side) & F-2 (upload portfolio PDF) + klarifikasi akun API

**Intake class:** Multi-skill (ai-engineer → developer)
**Status keseluruhan:** `in-progress`
**RAG:** 🟢 Green
**Refs:** #2026-08-11 11:30

### Keputusan / jawaban
- Claude Pro TIDAK bisa dipakai sebagai API aplikasi — butuh Anthropic Console (pay-as-you-go, kredit min ~$5). Estimasi biaya /suggest ±$0.10–0.30/sesi (claude-sonnet-5, harga intro s/d 2026-08-31). API key hanya hidup di .env lokal, tidak pernah di-share ke chat/git.
- F-1 (ai-engineer): Generation; claude-haiku-4-5; hanya utterance final; EN→ID tampil bersebelahan, ID tanpa terjemahan; async non-blocking p95<3s; biaya ±$0.10–0.15/sesi.
- F-2 (ai-engineer): bukan AI call — ekstraksi client-side (PDF text-based, dikonfirmasi user), full inject TANPA chunking/RAG; guard 30K char; WAJIB cache_control pada blok portfolio di suggest.py.

### Delegation
| # | Work item | Owner skill | Subagent (model) | Depends on | DoR | Status |
|---|-----------|-------------|------------------|-----------|-----|--------|
| 1 | Strategi F-1/F-2 | ai-engineer | inherits caller | konfirmasi user (arah bahasa, PDF text-based) | [x] | done |
| 2 | Handoff docs/instructions-developer-f1-f2.md (WI-7..12) | project-manager | — | #1 | [x] | done |
| 3 | WI-7..12 implementasi | developer | developer (sonnet) | #2 | [x] | delegated (via user → claude dev) |

### RAID
- **A:** Arah bahasa F-1 = EN→ID saja (ID tidak diterjemahkan) — confidence M, kalimat user ambigu — verify by: konfirmasi user saat review hasil; perubahan ke dua-arah = perubahan kecil.
- **A:** PDF user text-based — confidence H (dikonfirmasi) — mitigasi: WI-9 wajib error jelas untuk PDF hasil scan.
- **R:** Terjemahan memblokir pipeline ASR bila diimplementasi sinkron — detection: latency transkrip naik | mitigation: hard rule non-blocking di instruksi + acceptance criteria graceful-degrade.
- **D:** F-1/F-2 butuh ANTHROPIC_API_KEY terisi — blocked on: user membuat akun Console + isi kredit.

### Gate log
- [x] DoR delegasi developer — 2026-08-11 14:00
- [ ] DoD — menunggu laporan developer (acceptance criteria di instructions-developer-f1-f2.md)
- [ ] Go / No-go — belum

### Next action
User: buat API key di console.anthropic.com → isi ke .env. Developer: kerjakan WI-7..12.

---

## [2026-08-11 15:30] — Keputusan: Gemini free tier jadi provider utama; revisi total handoff F-1/F-2

**Intake class:** Multi-skill (solution-architect → developer)
**Status keseluruhan:** `in-progress`
**RAG:** 🟢 Green
**Refs:** #2026-08-11 14:00 (menggantikan strategi provider Anthropic di entri itu)

### Keputusan
- User memilih Opsi B setelah uji empiris key Gemini miliknya: auth ✓, burst 15/15 ✓, kualitas terjemahan & saran ✓. Trade-off data free tier ("content used to improve our products" atas transkrip interview + CV) DIKONFIRMASI diterima user secara eksplisit.
- Pemetaan model (ai-engineer): /suggest → gemini-3.5-flash; terjemahan F-1 → gemini-3.5-flash-lite (flash penuh boros ~441 token thinking per translasi). gemini-2.5-flash tidak tersedia utk akun baru.
- Mitigasi kuota harian: batching terjemahan 2–3 utterance/panggilan (wajib, WI-8).
- ANTHROPIC_API_KEY tidak terpakai; WI-10 lama (cache_control Anthropic) gugur — digantikan implicit caching Gemini via prefix stabil.

### Artefak
- [x] ADR Addendum 2026-08-11 (2) — docs/architecture/deployment-strategy.md
- [x] docs/instructions-developer-f1-f2.md — REVISI TOTAL (WI-7..12 versi Gemini, ada peringatan supersession di header utk claude dev)
- [x] .env lokal: GEMINI_API_KEY + model vars terpasang (gitignored, terverifikasi)

### RAID
- **R:** Kuota harian free tier tertabrak saat interview panjang — detection: HTTP 429 di log | mitigation: batching (WI-8) + graceful degrade + revisit provider berbayar bila berulang.
- **R:** Claude dev sempat mengerjakan versi Anthropic dari handoff lama — detection: laporan dev menyebut claude-haiku/cache_control | mitigation: header supersession di dokumen; PM tolak deliverable berbasis versi lama.
- **A:** Key `AQ.` format baru tetap berlaku jangka panjang — confidence M — verify by: kegagalan auth mendadak → cek AI Studio.
- **I:** Key Gemini & Anthropic sempat transit via chat — owner: user | mitigasi: rotate di console masing-masing setelah stack stabil (non-blocking).

### Gate log
- [x] DoR delegasi developer (Gemini) — 2026-08-11 15:30
- [ ] DoD — menunggu laporan developer
- [ ] Go / No-go — belum

### Next action
User: serahkan docs/instructions-developer-f1-f2.md (versi Gemini) ke claude dev. PM: gate DoD saat laporan masuk.

### Update insiden [2026-08-11 15:45]
- **I (resolved):** Claude dev menemukan plaintext API key di file lokal `docs/auth/` dan meremediasi (gitignore + hapus). Audit PM atas seluruh riwayat git (`--diff-filter=A`, pencarian string kedua key): file TIDAK PERNAH ter-commit/ter-push — key TIDAK bocor via GitHub. Rotasi karena jalur git tidak diperlukan; anjuran rotasi karena transit chat tetap berlaku (non-blocking). Catatan proses: dev juga sudah mengerjakan WI-11 lama (fix ALLOW_INSECURE_NO_AUTH) — tetap valid di handoff baru.

---

## [2026-08-11 16:30] — Gate DoD: migrasi Gemini + F-1 + F-2 (WI-7..12) — ACCEPTED

**Intake class:** Governance-only (acceptance review)
**Status keseluruhan:** `done`
**RAG:** 🟢 Green
**Refs:** #2026-08-11 15:30

### Verifikasi independen PM (dieksekusi sendiri, bukan membaca laporan)
- [x] Commit per-WI ter-push (7349ecc WI-7, 81f0100 WI-8, 6991138 WI-9, b65a9e9 WI-11; WI-10 PDF dari siklus sebelumnya df2a5c1 dengan pdfjs vendored)
- [x] `anthropic` hilang dari requirements & kode; config GEMINI_* lengkap; .env.example Gemini-only + ALLOW_INSECURE_NO_AUTH=false (temuan Low CLOSED)
- [x] pytest in-container: 41 passed (naik dari baseline 22)
- [x] Live gate: /health OK; /suggest tanpa token → 401; /suggest + token → real Gemini, ok:true, latency 3.8s, saran grounded ke portfolio
- [x] Wiring F-1: batching per-channel + flush non-blocking di app.py; frontend kontrak ref/text
- [x] Eval mini 20/20 terjemahan (tabel di laporan dev): 0 error, istilah teknis dipertahankan sesuai aturan prompt
- [x] Anomali "saran berbahasa EN" diaudit: aturan "bahasa yang sama dengan pertanyaan" warisan commit awal — perilaku BENAR; redaksi done-condition PM yang imprecise. Bukan defect.

### Gate log
- [x] DoD **PASS** — 2026-08-11 16:30
- [x] Go / No-go — **Go**. Tag v0.3.0 dipasang & ter-push oleh PM atas persetujuan acceptance.

### Residual (owner: user — satu-satunya yang bisa membuktikan)
- [ ] Uji live di browser dgn mic asli (http://127.0.0.1:5500): percakapan EN → transkrip + terjemahan ID ≤5s; percakapan ID → tanpa terjemahan; upload CV PDF → saran mengutip CV. Bila ada yang janggal → laporkan, jadi entri needs-fix baru.

---

## [2026-08-11 17:00] — Fitur: riwayat portfolio tersimpan (pilih dari history, tanpa re-upload)

**Intake class:** Multi-skill (solution-architect → developer)
**Status keseluruhan:** `in-progress`
**RAG:** 🟢 Green
**Refs:** #2026-08-11 16:30

### Keputusan (solution-architect, ADR Addendum (3))
- Storage: SQLite stdlib + Docker named volume (nol dependency baru, pola whisper-cache). Ditolak: localStorage (bukan DB, rapuh), MySQL/hosted (overkill, reintroduksi cloud).
- Trade-off diterima: riwayat per-laptop; CV tidak pernah masuk git. Revisit hosted DB hanya bila butuh sinkron lintas laptop.

### Delegation
| # | Work item | Owner skill | Subagent (model) | Depends on | DoR | Status |
|---|-----------|-------------|------------------|-----------|-----|--------|
| 1 | Keputusan storage + ADR | solution-architect | inherits caller | kebutuhan user | [x] | done |
| 2 | Handoff docs/instructions-developer-portfolio-store.md (WI-13..16) | project-manager | — | #1 | [x] | done |
| 3 | WI-13..16 implementasi | developer | developer (sonnet) | #2 | [x] | delegated (via user → claude dev) |

### RAID
- **R:** DB file tak sengaja masuk git bila ditaruh di tree repo — mitigation: hard rule volume di luar tree + acceptance "git status bersih".
- **R:** Endpoint portfolio tanpa auth — mitigation: hard rule auth.verify di semua endpoint + acceptance 401.
- **A:** Single-user, konkurensi tulis rendah — confidence H — sqlite tanpa pooling cukup.

### Gate log
- [x] DoR delegasi developer — 2026-08-11 17:00
- [ ] DoD — menunggu laporan (acceptance criteria di instructions-developer-portfolio-store.md)
- [ ] Go / No-go — belum

### Next action
User: serahkan docs/instructions-developer-portfolio-store.md ke claude dev. Target tag v0.4.0.

---

## [2026-08-11 18:00] — BUG: ucapan Indonesia tidak tertranskrip; halusinasi frasa pendek EN/DE (live test user)

**Intake class:** Multi-skill (bug-hunter → developer)
**Status keseluruhan:** `needs-fix`
**RAG:** 🟡 Amber — residual acceptance v0.3.0 GAGAL untuk jalur bahasa Indonesia; requirement bisnis baru dicatat: percakapan ID setara EN (warga kelas satu)
**Refs:** #2026-08-11 16:30 (residual live-mic test)

### Gejala
"selamat sore" tidak muncul; timeline berisi halusinasi "Hello."/"I'm sorry."/"Hallo!"(de)/"Sorry" ber-tag low-conf. Kondisi: WHISPER_MODEL=base, language auto-detect.

### Delegation
| # | Work item | Owner skill | Subagent (model) | Depends on | DoR | Status |
|---|-----------|-------------|------------------|-----------|-----|--------|
| 1 | Diagnosis H1/H2/H3 (bukti, confidence) | bug-hunter | inherits caller | klip audio repro | [x] | delegated (via user → claude dev) |
| 2 | Fix per temuan (model default, gating halusinasi, selector bahasa) | developer | developer (sonnet) | #1 | [ ] | blocked by #1 |

### Handoff artifacts
- [x] docs/instructions-bugfix-asr-indonesian.md — hipotesis, prediksi falsifiable, arah fix yang disetujui, acceptance eval ID+EN+hening

### RAID
- **I (live):** ASR gagal untuk ID → aplikasi belum layak untuk interview berbahasa Indonesia — owner: bug-hunter/developer | due: sebelum pemakaian interview ID nyata.
- **A:** WHISPER_MODEL=small menyelesaikan sebagian besar H1 — confidence M — user diminta uji mitigasi runtime (.env, tanpa kode) sebagai bukti awal diagnosis.
- **R:** Fix menurunkan akurasi EN — mitigation: acceptance eval dua bahasa wajib.

### Gate log
- [x] DoR — 2026-08-11 18:00 (gejala jelas, jalur repro didefinisikan, arah fix disetujui)
- [ ] DoD — menunggu laporan diagnosis + fix
- [ ] Go / No-go — No-go untuk interview ID sampai fix diverifikasi. Track portfolio (WI-13..16) jalan paralel, tidak terblokir.

### Next action
User: (a) coba mitigasi cepat WHISPER_MODEL=small di .env + compose up -d, laporkan hasil "selamat sore"; (b) serahkan docs/instructions-bugfix-asr-indonesian.md ke claude dev. Target tag v0.3.1.
