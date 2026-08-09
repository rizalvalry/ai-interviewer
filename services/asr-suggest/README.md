---
title: ai-interviewer-asr
emoji: 🎙️
colorFrom: blue
colorTo: purple
sdk: docker
app_port: 8000
pinned: false
---

# ai.interviewer — Service ASR + Suggest

Service FastAPI yang menerima streaming audio interview dua channel lewat WebSocket
(`/stream`), mentranskrip tiap channel dengan model Whisper lokal (`faster-whisper`), dan
meneruskan permintaan saran jawaban interview ke Claude (`/suggest`). Target deploy:
Hugging Face Space (SDK Docker). Alasan lengkapnya ada di
`docs/architecture/deployment-strategy.md` di root repo.

> **Peringatan sebelum deploy publik:** per hasil review keamanan (2026-08-09), service ini
> **belum aman untuk Space publik** — endpoint `/suggest` belum ada pengecekan token, dan
> `AUTH_SECRET` kosong membuat verifikasi token `/stream` otomatis lolos. Gunakan visibility
> **Private** dulu sampai dua item ini diperbaiki. Detail di
> `docs/deployment-checklist.md`.

## Secret / environment variable yang wajib diisi

Isi semua ini lewat panel Space **Settings → Repository secrets** — jangan pernah commit ke
`.env` atau ikut ter-bundle di dalam image Docker.

| Variabel | Fungsi | Default |
|---|---|---|
| `ANTHROPIC_API_KEY` | API key Claude yang dipakai `/suggest` | *(wajib diisi agar `/suggest` berfungsi)* |
| `AUTH_SECRET` | Secret HMAC untuk tanda-tangan/verifikasi token sesi `/stream`. Kalau kosong, verifikasi WS otomatis nonaktif — jangan pernah dibiarkan kosong di Space publik | *(kosong = auth nonaktif)* |
| `ALLOW_DEV_TOKEN` | Wajib tetap `false`/kosong di deployment publik mana pun. Lihat catatan "dev token" di bawah | `false` |
| `WHISPER_MODEL` | Ukuran model faster-whisper (`tiny`, `base`, `small`, ...) | `base` |
| `WHISPER_COMPUTE` | Tipe compute ctranslate2 | `int8` |
| `WHISPER_DEVICE` | Device inference | `cpu` |
| `WHISPER_CPU_THREADS` | Jumlah thread per inference | `2` |
| `MAX_CONCURRENT_ASR` | Slot inference bersamaan | `2` |
| `WINDOW_SEC` | Panjang window ASR (detik) | `2.0` |
| `OVERLAP_SEC` | Overlap antar window (detik) | `0.5` |
| `MAX_BUF_SEC` | Buffer audio maksimum per channel (detik) | `30` |
| `IDLE_TIMEOUT_SEC` | Timeout idle WebSocket (detik) | `30` |
| `ENERGY_GATE_DB` | Ambang gerbang keheningan | `-45.0` |
| `VAD_THRESHOLD` | Sensitivitas VAD | `0.5` |
| `LOW_CONF_LOGPROB` | Ambang confidence rendah | `-0.7` |
| `TOKEN_TTL_SEC` | Umur token sesi (detik) | `120` |
| `CLAUDE_MODEL` | ID model Claude untuk `/suggest` | `claude-sonnet-5` |
| `CLAUDE_TIMEOUT_SEC` | Timeout request Claude (detik) | `15` |
| `CORS_ORIGINS` | Origin yang diizinkan, dipisah koma (isi dengan origin frontend Vercel) | `*` |

### `/dev/token` — jangan diaktifkan di Space publik

`GET /dev/token` menerbitkan token sesi yang valid tanpa pengecekan login sama sekali.
Endpoint ini ada hanya karena `services/auth-laravel/` (penerbit token yang sebenarnya)
belum dibangun. Sudah dijaga lewat flag `ALLOW_DEV_TOKEN` dan akan mengembalikan `404`
kecuali flag itu diset eksplisit ke `true`. Biarkan tetap kosong di Space ini sampai service
auth Laravel menggantikannya — mengaktifkannya di URL publik memungkinkan siapa saja
menerbitkan token sendiri dan memakai compute ASR/Claude secara gratis.
