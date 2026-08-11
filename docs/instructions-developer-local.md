# Instruksi Developer — Mode Localhost-First + Versioning Berkala

> Handoff package dari `project-manager` → `developer` (sonnet). Ditulis: 2026-08-11.
> Keputusan arsitektur yang mendasari dokumen ini milik `solution-architect` — lihat
> addendum 2026-08-11 di `docs/architecture/deployment-strategy.md`. Developer TIDAK
> mengubah keputusan arsitektur; kerjakan di dalam batas yang tercantum di sini.

---

## Konteks keputusan (jangan didebat ulang, sudah diputuskan)

1. **Topologi pivot: localhost-first.** Deploy cloud (Vercel + HF Space) DITUNDA — HF kini
   mensyaratkan PRO ($9/bln) untuk membuat Docker Space, dan kebutuhan user adalah tool
   personal yang dijalankan on-demand saat interview, bukan layanan publik 24/7.
2. **Portabilitas lintas laptop dicapai lewat tiga jalur:**
   - **Kode** → GitHub `https://github.com/rizalvalry/ai-interviewer.git` (remote `origin`
     sudah terpasang, branch `main`).
   - **Runtime** → Docker (image dibangun dari `services/asr-suggest/Dockerfile`).
   - **Secrets** → file `.env` per laptop, TIDAK PERNAH masuk git.
3. **Database: tidak ada.** `services/auth-laravel/` tetap placeholder — jangan dibangun.
   Auth lokal cukup pakai `ALLOW_DEV_TOKEN=true`.
4. Temuan security Critical #2 (`/suggest` tanpa token) dan #3 (fail-open `AUTH_SECRET`)
   **sudah diperbaiki di kode** (`app.py:111`, `config.py` flag `ALLOW_INSECURE_NO_AUTH`).
   Jangan kerjakan ulang; cukup pastikan test yang mengcover keduanya tetap lolos.

---

## Prasyarat per laptop (di luar scope kode — cukup didokumentasikan di README)

| Kebutuhan | Keterangan |
|---|---|
| Docker Desktop (atau Docker CLI + engine) | Menjalankan seluruh stack |
| Git | Clone/pull/push repo |
| API key Anthropic | Diisi manual ke `.env` di tiap laptop |

---

## Work items (urut; setiap item punya done condition)

### WI-1 — `docker-compose.yml` di root repo
Satu perintah `docker compose up` menghidupkan seluruh stack.

- Service `asr`: build dari `services/asr-suggest/`, env dari `.env` root,
  **port binding wajib `127.0.0.1:8000:8000`** (bukan `8000:8000` — default Docker bind ke
  `0.0.0.0` dan itu mengekspos service tanpa auth ke seluruh jaringan LAN).
- Named volume untuk cache model Whisper (`/home/user/.cache/huggingface`, lihat `HF_HOME`
  di Dockerfile) — supaya model tidak di-download ulang setiap container dibuat ulang.
- Service `frontend`: static server untuk `./frontend` di **`127.0.0.1:5500`** (image ringan,
  mis. nginx:alpine dengan mount read-only — pilihan teknis bebas, binding-nya tidak).
- **Done:** `docker compose up` dari clone bersih → `GET http://127.0.0.1:8000/health` OK,
  `http://127.0.0.1:5500` tampil, tanpa langkah manual selain mengisi `.env`.

### WI-2 — `.env.example` di root repo
Template yang tinggal di-copy jadi `.env` di laptop baru.

- Isi semua var yang dibaca `services/asr-suggest/config.py` dengan nilai default mode
  localhost, minimal: `ANTHROPIC_API_KEY=` (kosong, wajib diisi manual),
  `ALLOW_DEV_TOKEN=true`, `ALLOW_INSECURE_NO_AUTH=true`,
  `CORS_ORIGINS=http://127.0.0.1:5500`, plus `WHISPER_MODEL` / `WHISPER_COMPUTE` /
  `WHISPER_DEVICE` sesuai default config.py.
- Beri komentar per baris: mana yang wajib diisi, mana yang boleh dibiarkan.
- **Done:** `cp .env.example .env` + isi API key = konfigurasi lengkap, tanpa menebak.

### WI-3 — README quickstart "laptop baru → siap interview"
Bagian baru di `README.md` root (buat filenya bila belum ada) berisi urutan persis:

```
git clone https://github.com/rizalvalry/ai-interviewer.git
cd ai-interviewer
cp .env.example .env      # lalu isi ANTHROPIC_API_KEY
docker compose up -d
# buka http://127.0.0.1:5500
```

- Sertakan juga: cara stop (`docker compose down`), cara update di laptop lama
  (`git pull` lalu `docker compose up -d --build`), dan catatan bahwa download model
  Whisper hanya terjadi sekali per laptop (tersimpan di volume).
- **Done:** seseorang tanpa konteks proyek bisa sampai ke UI yang jalan hanya dengan
  mengikuti bagian ini.

### WI-4 — Selaraskan `run-dev.ps1`
Mode venv lama tetap boleh hidup sebagai alternatif dev cepat, tapi tambahkan header
komentar yang menyatakan jalur utama sekarang `docker compose up`. Jangan hapus.

- **Done:** tidak ada dua "sumber kebenaran" yang saling bertentangan tentang cara start.

### WI-5 — Verifikasi (wajib sebelum commit terakhir)
1. Seluruh test suite lolos (`pytest` di `services/asr-suggest/` — baseline saat ini
   22 test, jangan turun).
2. Smoke test end-to-end via stack compose: `GET /dev/token` → buka WS `/stream` dengan
   token → `POST /suggest` dengan token yang sama → respons wajar; `POST /suggest` TANPA
   token → 401.
3. `git status` bersih dari artefak (`.env`, cache model, `__pycache__`) — bila ada yang
   bocor, perbaiki `.gitignore` dulu.
- **Done:** ketiga bukti di atas dicantumkan di laporan akhir (output test + hasil smoke).

### WI-6 (OPSIONAL — kerjakan hanya setelah WI-1..5 diterima)
Bake model Whisper ke dalam image dan push ke Docker Hub (`rizalvalry/<nama-image>`),
supaya laptop baru cukup `docker pull` tanpa build + download model. Kalau dikerjakan,
dokumentasikan varian quickstart-nya di README.

---

## Disiplin versioning berkala (WAJIB — ini bagian dari DoD, bukan saran)

Tujuan: repo GitHub selalu dalam keadaan bisa di-clone dan langsung jalan di device lain.

1. **Mulai kerja di laptop mana pun: `git pull` dulu.** Tidak ada pengecualian.
2. **Satu commit per work item selesai** — pesan commit menyebut WI-nya
   (mis. `WI-1: docker-compose untuk stack localhost`). Jangan menumpuk beberapa WI
   dalam satu commit raksasa.
3. **Push ke `origin main` setiap kali sebuah WI selesai** dan di akhir setiap sesi kerja —
   bukan "nanti sekalian". Laptop yang tidak ter-push = pekerjaan yang tidak ada.
4. **Tag milestone** ketika stack compose pertama kali terverifikasi end-to-end:
   `git tag v0.2.0 && git push origin v0.2.0` (baseline `v0.1.x` = kondisi saat ini).
5. **Yang HARAM masuk git:** `.env` (API key), cache model, `.venv/`, `__pycache__/`.
   `.gitignore` saat ini sudah mengcover — verifikasi sebelum setiap commit.
6. Commit yang menyentuh perilaku harus lolos test dulu (WI-5 poin 1) — jangan push merah.

---

## Batasan (hard rules untuk developer)

- JANGAN membangun `services/auth-laravel/` atau menambah database — di luar scope.
- JANGAN mengubah port binding dari `127.0.0.1` — `ALLOW_DEV_TOKEN=true` +
  `ALLOW_INSECURE_NO_AUTH=true` hanya aman selama service tidak terjangkau dari luar mesin.
- JANGAN menambah dependency baru tanpa mencatat alasannya sebagai assumption di laporan.
- JANGAN menyentuh keputusan arsitektur (platform, topologi) — kalau menemukan hambatan
  yang memaksa perubahan arsitektur, STOP dan kembalikan ke `project-manager`.
- Catat setiap assumption secara eksplisit di laporan akhir (format standar skill
  `developer`), terpisah dari fakta.

## Acceptance criteria (yang akan dipakai PM untuk menerima/menolak)

- [ ] Clone bersih di mesin lain (atau folder lain) + `.env` terisi → `docker compose up`
      → UI hidup dan bisa buka sesi WS. Ini KRITERIA UTAMA — portabilitas adalah delivery-nya.
- [ ] Seluruh test lolos; smoke test 401-tanpa-token terbukti.
- [ ] `.env` dan artefak tidak pernah muncul di riwayat git.
- [ ] README quickstart akurat terhadap kenyataan (diverifikasi dengan mengikutinya, bukan
      dengan membacanya).
- [ ] Semua commit ter-push ke `origin main` + tag milestone terpasang.
