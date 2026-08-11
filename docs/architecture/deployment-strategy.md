# Deployment Strategy — ai.interviewer

> Architecture decision record. Owner: `solution-architect`. Ditulis: 2026-08-09.
> **⚠️ ADDENDUM 2026-08-11 — keputusan di bawah DITUNDA, topologi aktif berubah ke
> localhost-first. Lihat bagian "Addendum 2026-08-11" di akhir dokumen.**
> Konteks: real-time interview co-pilot (dual-audio capture → streaming ASR → Claude suggestion),
> saat ini berjalan di localhost, perlu dipetakan ke topologi cloud produksi.

## Ringkasan keputusan

| Komponen | Kode saat ini | Target platform | Alasan |
|---|---|---|---|
| Frontend (audio capture UI) | `frontend/` (dulu `web/`) | **Vercel** (static hosting/CDN) | Static assets, tidak ada compute server-side, HTTPS + deploy dari git gratis |
| ASR streaming + Claude suggestion | `services/asr-suggest/` (dulu `server/`) | **Hugging Face Space** (Docker SDK) | Lihat "Kenapa bukan Vercel" di bawah |
| Auth (token issuance) + domain + data kandidat | `services/auth-laravel/` — placeholder, belum ada kode, didesain untuk Laravel (lihat `auth.py` comment) | **Hostinger cPanel** (Laravel, PHP-FPM, MySQL) | Shared hosting cukup andal untuk REST ringan + relational data, tidak untuk compute/WS |

> Restrukturisasi folder (`web/`→`frontend/`, `server/`→`services/asr-suggest/`) sudah
> **selesai dieksekusi** oleh `developer` dan terverifikasi (22/22 test lolos, path di
> `run-dev.ps1` sudah diupdate). Referensi path di dokumen ini sudah mengikuti struktur final.

## Kenapa bukan all-Vercel

`services/asr-suggest/asr.py` memuat model Whisper sebagai singleton in-process yang
di-*warmup* sekali saat startup (`_model` global). `services/asr-suggest/app.py` mengekspos
endpoint **WebSocket** (`/stream`) dengan state per-koneksi (`ChannelState.buf`, `last_seq`)
yang hidup selama durasi sesi interview.

Ini bukan soal preferensi — ini keterbatasan platform:
- Runtime Python di Vercel **tidak mendukung WebSocket** (hanya runtime Node.js Vercel yang punya
  dukungan WS terbatas via Fluid Compute).
- Vercel Python function adalah **serverless per-invocation** — tidak ada jaminan proses tetap
  *warm* antar-request; model Whisper akan reload berulang kali, melanggar target latency interim
  <1.2s (lihat `panduan-start-dialog-audio-realtime.md`).
- Ukuran deployment (`faster-whisper` + `ctranslate2` + bobot model + `numpy`) berpotensi melebihi
  batas ukuran function Vercel (250MB unzipped di Hobby tier). Vercel bukan container host untuk
  proses persisten — beda kelas dengan Hugging Face Spaces/Fly.io/Railway.

**Kesimpulan:** svc-asr harus tetap di Hugging Face Space, persis seperti yang sudah didesain di
`panduan-start-dialog-audio-realtime.md`. `/suggest` (Claude) ikut di service yang sama karena
stateless dan tidak butuh compute berat — memisahkannya ke Vercel hanya menambah network hop dan
duplikasi secret tanpa manfaat skalabilitas nyata.

## Kenapa Hostinger cPanel (PHP/Laravel) cukup andal — dengan batasan

Hostinger Business+ mendukung Laravel via hPanel (PHP 8.1+, Composer, SSH, MySQL included, cron
job untuk `queue:work --stop-when-empty` bila perlu job async ringan). Ini cukup untuk:
- Menerbitkan token bertanda-tangan (`auth.py` sudah didesain menerima token yang ditandatangani
  Laravel dengan secret yang sama — lihat `AUTH_SECRET` di `.env.example`).
- Login/session kandidat, penyimpanan data kandidat/portfolio di MySQL.
- Landing page + DNS/domain.

**Tidak andal** untuk: WebSocket (shared hosting tidak mendukung proses daemon persisten) atau
proses background jangka panjang tanpa Supervisor. Karena itu perannya dibatasi ke auth/domain/data
saja — bukan compute real-time.

## Integrasi lintas provider

```
Frontend (Vercel)
   ├─ wss://<space>.hf.space/stream        → audio real-time (ASR)
   ├─ https://<space>.hf.space/suggest     → saran Claude (proxied, API key server-side)
   └─ https://<domain>.hostinger/api/token → auth (Laravel), data kandidat
```

Frontend **tidak pernah** memanggil Claude langsung — `ANTHROPIC_API_KEY` hanya ada di HF Space.
`config.CORS_ORIGINS` (env-driven, lihat `services/asr-suggest/config.py`) tinggal diisi origin
Vercel saat deploy.

## Alternatif yang dipertimbangkan: self-host semua di Biznet Gio/Hostinger?

Sempat dipertimbangkan: kalau sudah ada hosting berjalan di Hostinger/Biznet Gio, kenapa tidak
langsung arahkan domain ke sana saja tanpa Vercel/HF Space? **Dikonfirmasi ke user: keduanya
adalah shared hosting/cPanel**, bukan VPS/Cloud Server dengan root access. Shared hosting tidak
mendukung proses persisten atau WebSocket — sama seperti alasan Vercel ditolak untuk ASR service
(lihat "Kenapa bukan all-Vercel" di atas), batasan ini bukan soal domain, tapi soal jenis hosting.

**Ditolak** untuk alasan itu. Kalau di masa depan salah satu provider di-upgrade ke VPS/Cloud
Server (root access, bisa jalankan proses systemd/Docker persisten), keputusan ini layak
dievaluasi ulang — itu bisa menghilangkan kebutuhan HF Space (dan biaya HF PRO untuk custom
domain) sepenuhnya dengan menjalankan semua service dalam satu server. Trade-off-nya: kamu yang
menanggung sendiri uptime, resource sizing, TLS cert, dan process supervision — yang saat ini
otomatis ditangani gratis oleh HF Space (dengan batas CPU/cold-start sebagai kompensasinya).

## Biaya custom domain per provider

- **Vercel** — gratis di semua tier (Hobby maupun Pro). DNS pointing (CNAME/A record) ke Vercel
  tidak dikenakan biaya tambahan dari Vercel.
- **Hugging Face Space** — custom domain untuk Space memerlukan **HF PRO** (berbayar, kisaran
  $9/bulan per informasi terakhir — cek halaman pricing HF untuk angka terkini, tidak dijamin
  akurat pada saat dokumen ini dibaca). Tanpa PRO, Space tetap bisa diakses via URL default
  `*.hf.space` — fungsional, hanya tidak branded dengan domain sendiri.
- **Hostinger/Biznet Gio (auth layer)** — domain di sini memang domain utama yang sudah dimiliki
  user; tidak ada biaya tambahan untuk memakainya sebagai auth API endpoint, di luar biaya hosting
  yang memang sudah berjalan.

## Load-bearing decisions (validasi sebelum go-live)

1. **`AUTH_SECRET` harus identik** antara Laravel (Hostinger) dan FastAPI (HF Space) — test
   end-to-end: token terbit dari Laravel harus lolos verifikasi di FastAPI.
2. **Custom domain untuk HF Space memerlukan HF PRO** (berbayar). Tanpa itu, frontend memanggil URL
   default `*.hf.space`. Perlu konfirmasi budget dari user.
3. **Skala target belum dikonfirmasi** (tool personal vs multi-user) — menentukan apakah HF free
   tier CPU cukup jangka panjang, atau perlu ZeroGPU/tier berbayar.

## Status keamanan (per review `security-reviewer`, 2026-08-09)

**Verdict: FAIL — 2 temuan Critical, 1 High, masih memblokir deployment ke Space publik.**
Checklist lengkap dan status terkini ada di `docs/deployment-checklist.md`. Ringkasannya:

| # | Temuan | Severity | Status |
|---|---|---|---|
| 1 | `GET /dev/token` (`services/asr-suggest/app.py:81-88`) bisa menerbitkan token tanpa login | Critical (awal) | **Selesai diperbaiki** — sekarang dijaga flag `ALLOW_DEV_TOKEN` (default `false`), mengembalikan `404` kecuali diaktifkan eksplisit |
| 2 | `POST /suggest` (`services/asr-suggest/app.py:98-113`) **sama sekali tidak ada pengecekan token**, beda dengan `/stream` | **Critical — belum diperbaiki** | Ditemukan saat review, di luar cakupan perbaikan #1. Siapa pun bisa memanggil endpoint ini langsung dan menghabiskan budget `ANTHROPIC_API_KEY` tanpa token apa pun |
| 3 | `auth.verify()` *fail-open* bila `AUTH_SECRET` kosong (`services/asr-suggest/auth.py:20-21`) | **Critical — belum diperbaiki** | Bukan lagi "risiko masa depan" — start-up hanya mencatat warning log, tidak menolak jalan. Harus fail-loud sebelum Space publik dibuka |
| 4 | Trap sequencing: `ALLOW_DEV_TOKEN` harus `true` agar app berfungsi untuk user asli (belum ada Laravel), tapi itu berarti sama terbukanya untuk siapa pun | High | Bukan bug kode — ini keterbatasan desain sampai `services/auth-laravel/` benar-benar ada. Mitigasi sementara: **Space tetap Private**, jangan Public dulu |

**Implikasi langsung:** jangan set visibility Space ke **Public** sampai temuan #2 dan #3
selesai diperbaiki oleh `developer` dan divalidasi ulang oleh `security-reviewer`. Untuk
testing/demo terbatas sekarang, gunakan Space **Private**.

## Struktur folder (sudah diterapkan)

```
frontend/               (dulu web/)             — deploy target: Vercel
services/asr-suggest/   (dulu server/)          — deploy target: Hugging Face Space
services/auth-laravel/                          — deploy target: Hostinger, belum ada kode (placeholder)
docs/architecture/                              — dokumen ini
docs/deployment-checklist.md                    — checklist env var + langkah manual + panduan domain cPanel
```

## Hand off

→ `developer` — perbaiki temuan #2 (auth check di `/suggest`) dan #3 (fail-loud saat
`AUTH_SECRET` kosong di environment non-lokal).
→ `security-reviewer` — validasi ulang setelah #2 dan #3 diperbaiki; putuskan strategi
mitigasi untuk temuan #4 (Space Private vs stand-in passphrase) bersama `solution-architect`.
→ `qa-analysis` — test plan end-to-end lintas 3 origin (CORS, token issuance→verify, reconnect/seq
dedup saat WS terputus jaringan lintas provider), plus skenario negatif untuk #2 dan #3.

---

## Addendum 2026-08-11 — Pivot ke localhost-first (keputusan aktif)

Dua fakta baru mengubah keputusan di atas:

1. **Kebijakan Hugging Face berubah** (diverifikasi 2026-08-11 dari docs resmi HF):
   membuat **Docker Space kini mensyaratkan paid plan — PRO $9/bln** untuk akun personal.
   Hardware CPU Basic tetap $0/jam, tapi gerbang pembuatannya berbayar. Asumsi "HF Space
   gratis" yang mendasari keputusan 2026-08-09 tidak lagi berlaku.
2. **Kebutuhan user dikonfirmasi**: tool personal yang dijalankan on-demand saat interview,
   berpindah-pindah laptop — bukan layanan publik 24/7.

**Keputusan baru:** seluruh stack berjalan **localhost via Docker Compose**, di-start saat
dibutuhkan. Portabilitas lintas device dicapai lewat git (kode, `origin` =
`github.com/rizalvalry/ai-interviewer.git`), Docker image (runtime + model), dan `.env`
per laptop (secrets). Vercel/HF Space/tunnel: tidak dipakai; ditinjau ulang hanya jika
kebutuhan berubah jadi multi-user/publik (kandidat saat itu: VPS ~$4–9/bln yang sekaligus
menampung Laravel auth — lihat "Alternatif yang dipertimbangkan" di atas).

**Database:** tidak ada untuk mode ini. `services/auth-laravel/` tetap placeholder;
auth lokal memakai `ALLOW_DEV_TOKEN=true` + binding `127.0.0.1` (bukan `0.0.0.0`).

**Koreksi status keamanan:** temuan #2 (`/suggest` tanpa token) dan #3 (fail-open
`AUTH_SECRET`) **sudah diperbaiki di kode** — `/suggest` memverifikasi token
(`app.py`), dan startup menolak `AUTH_SECRET` kosong kecuali `ALLOW_INSECURE_NO_AUTH`
di-set eksplisit (`config.py`). Tabel status di atas dibiarkan sebagai catatan historis.

**Hand off:** → `developer`, instruksi lengkap di `docs/instructions-developer-local.md`.

---

## Addendum 2026-08-11 (2) — Provider LLM: Google Gemini (free tier)

**Keputusan:** provider LLM utama berpindah **Anthropic → Google Gemini API (free tier, AI Studio)**.
Dikonfirmasi user 2026-08-11 setelah uji empiris dengan key user sendiri.

| Fungsi | Model | Alasan |
|---|---|---|
| `/suggest` (saran interview) | `gemini-3.5-flash` | Uji kualitas gaya /suggest: saran grounded ke portfolio, bahasa Indonesia rapi |
| Terjemahan realtime (F-1) | `gemini-3.5-flash-lite` | `3.5-flash` membakar ~441 token thinking untuk translasi 1 kalimat; flash-lite selesai 49 token total — lebih cepat & hemat kuota |

**Bukti uji (2026-08-11):** autentikasi ✓; `gemini-2.5-flash` ditutup untuk akun baru;
burst 15 panggilan beruntun → 15/15 sukses (rate limit per-menit aman); kualitas terjemahan ✓.

**Alternatif ditolak:** Anthropic PAYG (kredit min $5; kualitas teruji, tapi user memilih Rp0),
ChatGPT Go / Claude Pro (langganan chat konsumen — bukan API).

**Sacrifice yang diterima secara sadar oleh user:** (1) kebijakan data free tier — *"content
used to improve our products"* — berlaku atas transkrip interview + CV; (2) kuota harian free
tier (angka per-akun di AI Studio) — dimitigasi dengan batching terjemahan 2–3 utterance per
panggilan; (3) kualitas saran vs Claude Sonnet belum dieval formal — eval 20 contoh menjadi
bagian acceptance F-1/F-2.

`ANTHROPIC_API_KEY` menjadi tidak terpakai. Revisit ke provider berbayar bila: kuota harian
mulai tertabrak, kualitas saran mengecewakan di pemakaian nyata, atau kebijakan data menjadi
masalah. Handoff: `docs/instructions-developer-f1-f2.md` (direvisi total untuk Gemini).
