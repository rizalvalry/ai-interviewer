# ai.interviewer

Real-time interview co-pilot: tangkap audio kandidat + interviewer dua channel, transkrip
streaming (Whisper lokal), terjemahan EN→ID + saran jawaban (Google Gemini free tier). Mode
operasi saat ini: **localhost-first via Docker Compose**, dijalankan on-demand saat interview
— bukan layanan cloud 24/7. Lihat `docs/architecture/deployment-strategy.md` (Addendum
2026-08-11, Addendum 2026-08-11 (2)) untuk alasan pivot topologi & provider LLM.

## Quickstart — laptop baru → siap interview

```
git clone https://github.com/rizalvalry/ai-interviewer.git
cd ai-interviewer
cp .env.example .env      # lalu isi GEMINI_API_KEY (aistudio.google.com/apikey)
docker compose up -d
# buka http://127.0.0.1:5500
```

Prasyarat: Docker Desktop (atau Docker CLI + engine) dan Git terpasang. Tidak ada langkah
manual lain — `.env.example` sudah berisi nilai default mode localhost yang siap pakai,
kecuali `GEMINI_API_KEY` (satu-satunya kredensial wajib) yang harus diisi sendiri per laptop.

## Stop

```
docker compose down
```

## Update di laptop yang sudah pernah dipakai

```
git pull
docker compose up -d --build
```

## Model Whisper — hanya download sekali per laptop

`faster-whisper` mengunduh bobot model saat container pertama kali jalan. Cache-nya
disimpan di named volume (`whisper-cache`, lihat `docker-compose.yml`), jadi `docker compose
down` lalu `up` lagi — atau rebuild image — tidak mengunduh ulang. Volume hanya hilang kalau
dihapus eksplisit (`docker compose down -v` atau `docker volume rm`).

## Mode dev alternatif (tanpa Docker)

`run-dev.ps1` masih tersedia untuk iterasi cepat tanpa build image — lihat komentar di
file itu. Jalur utama untuk pemakaian sehari-hari tetap `docker compose up`.

## Struktur

```
frontend/               — UI capture audio + transkrip (static, disajikan nginx)
services/asr-suggest/   — FastAPI: ASR streaming (/stream) + saran & terjemahan Gemini (/suggest)
services/auth-laravel/  — placeholder, belum dibangun (lihat ADR)
docs/architecture/      — keputusan arsitektur (ADR)
```
