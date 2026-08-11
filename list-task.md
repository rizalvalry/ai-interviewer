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
