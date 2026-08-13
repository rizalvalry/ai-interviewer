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

> **Port 5500 bentrok dengan VS Code Live Server?** Ekstensi Live Server juga default ke
> port 5500 — kalau sedang aktif, `docker compose up` untuk `frontend` akan gagal bind port.
> Matikan Live Server dulu, atau ubah pemetaan port `frontend` di `docker-compose.yml`
> (mis. `"127.0.0.1:5501:80"`) dan sesuaikan URL yang dibuka.

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

**Default `WHISPER_MODEL=small`** (sejak bugfix ASR Indonesia 2026-08-11) — `base` terbukti
salah dengar utterance Indonesia pendek/ambigu (lihat `docs/instructions-bugfix-asr-indonesian.md`).
`small` lebih akurat tapi lebih berat: kira-kira 2× waktu inferensi & RAM dibanding `base` pada
CPU yang sama. Kalau laptop tertinggal mengejar audio real-time (interim tersendat, `asr_latency_ms`
di footer UI terus naik), turunkan ke `WHISPER_MODEL=base` di `.env` lalu `docker compose up -d --build`
— akurasi ID akan sedikit menurun sebagai trade-off-nya.

## Selector bahasa (Auto | ID | EN)

Dropdown "Bahasa" di UI (default **Auto**) mengunci `language=` yang dikirim ke Whisper untuk
seluruh sesi WS — jalan keluar deterministik kalau auto-detect salah tebak pada ucapan pendek.
Pilih **ID** atau **EN** sebelum menekan Start Dialog bila interview didominasi satu bahasa.

## Indikator audio tertinggal (bug-hunter H4, 2026-08-11)

Kalau inferensi ASR tidak mengejar audio real-time (bicara kontinu di kedua channel
sekaligus, atau laptop lambat), buffer internal (`MAX_BUF_SEC=30`) pada akhirnya membuang
audio tertua — sekarang **tidak lagi diam-diam**: banner peringatan muncul di UI dan counter
`audio_dropped_sec` di footer bertambah setiap kali ini terjadi. Kalau sering muncul: turunkan
`WHISPER_MODEL` ke `base`, atau kurangi intensitas bicara bersamaan di kedua channel.

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
