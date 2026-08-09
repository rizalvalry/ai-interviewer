# Checklist Deployment — ai.interviewer

Referensi praktis untuk go-live: frontend di Vercel + backend ASR/suggest di Hugging Face
Space (`services/asr-suggest`). Alasan arsitekturnya ada di
`docs/architecture/deployment-strategy.md` — dokumen ini tidak mengulang alasannya, hanya
berisi langkah manual konkret dan daftar env var.

> **Status keamanan saat ini (per review `security-reviewer`, 2026-08-09):** service ini
> **belum aman untuk dipublikasikan** ke publik. Ada 2 temuan Critical yang harus diperbaiki
> `developer` dulu sebelum lanjut ke langkah "buat Space publik" di bawah:
> 1. Endpoint `/suggest` belum ada pengecekan token sama sekali.
> 2. `AUTH_SECRET` kosong membuat semua verifikasi token otomatis lolos (fail-open).
>
> Sampai dua item itu selesai, checklist ini aman dipakai untuk **Space privat** (opsi
> "Private" saat membuat Space di Hugging Face) atau testing terbatas — jangan diaktifkan
> sebagai Space publik dulu.

## Daftar env var / secret per platform

### Vercel (`frontend/`) — tidak perlu env var

`frontend/js/app.js:7` mengambil alamat backend ASR saat runtime lewat
`localStorage.getItem('asrHttp')` (fallback ke `http://127.0.0.1:8000` untuk testing lokal).
Tidak ada proses build, jadi tidak perlu inject env var saat build. Alamat backend cukup
diisi sekali dari browser console setelah halaman pertama kali dibuka (atau nanti dibuatkan
UI pengaturan). Tidak ada yang perlu dikonfigurasi di dashboard Vercel selain project itu
sendiri.

### Hugging Face Space (`services/asr-suggest/`) — isi di Settings → Repository secrets

| Variabel | Fungsi | Dibaca di |
|---|---|---|
| `ANTHROPIC_API_KEY` | API key Claude untuk endpoint `/suggest` | `services/asr-suggest/config.py:39` |
| `AUTH_SECRET` | Secret HMAC untuk verifikasi token `/stream` — nanti harus sama persis dengan secret di Laravel begitu Laravel sudah ada | `services/asr-suggest/config.py:29` |
| `ALLOW_DEV_TOKEN` | **Wajib tetap kosong/`false`** di Space publik — lihat catatan "/dev/token" di bawah | `services/asr-suggest/config.py:37` |
| `WHISPER_MODEL` | Ukuran model Whisper | `services/asr-suggest/config.py:5` |
| `WHISPER_COMPUTE` | Tipe compute ctranslate2 | `services/asr-suggest/config.py:6` |
| `WHISPER_DEVICE` | Device inference (`cpu` di tier gratis) | `services/asr-suggest/config.py:7` |
| `WHISPER_CPU_THREADS` | Jumlah thread per inference | `services/asr-suggest/config.py:11` |
| `MAX_CONCURRENT_ASR` | Slot inference bersamaan | `services/asr-suggest/config.py:12` |
| `WINDOW_SEC` / `OVERLAP_SEC` | Ukuran window ASR | `services/asr-suggest/config.py:17-18` |
| `MAX_BUF_SEC` | Buffer maksimum per channel | `services/asr-suggest/config.py:20` |
| `IDLE_TIMEOUT_SEC` | Timeout idle WebSocket | `services/asr-suggest/config.py:21` |
| `ENERGY_GATE_DB` | Ambang gerbang keheningan | `services/asr-suggest/config.py:23` |
| `VAD_THRESHOLD` | Sensitivitas VAD | `services/asr-suggest/config.py:24` |
| `LOW_CONF_LOGPROB` | Ambang confidence rendah | `services/asr-suggest/config.py:25` |
| `TOKEN_TTL_SEC` | Umur token sesi | `services/asr-suggest/config.py:30` |
| `CLAUDE_MODEL` | ID model Claude | `services/asr-suggest/config.py:40` |
| `CLAUDE_TIMEOUT_SEC` | Timeout request Claude | `services/asr-suggest/config.py:41` |
| `CORS_ORIGINS` | Origin yang diizinkan, dipisah koma — isi dengan origin Vercel yang sudah live | `services/asr-suggest/config.py:43` |

### Hostinger / Biznet Gio / Laravel (`services/auth-laravel/`) — belum dibangun

Masih placeholder, lihat `docs/architecture/deployment-strategy.md`. `AUTH_SECRET` nanti
harus diisi sama persis di sini begitu service ini sudah ada kodenya — di luar cakupan
checklist ini untuk saat ini.

## Langkah manual (harus kamu lakukan sendiri — tidak bisa diotomatisasi dari sini)

1. **Review lalu commit** file-file yang sudah disiapkan di sesi ini (`git status` di root
   repo), lalu push ke remote GitHub.
2. **Buat project Vercel** — Import repo GitHub, set **Root Directory = `frontend`**,
   framework preset = Other/static (tanpa build command). Deploy.
3. **Buat Hugging Face Space** — New Space → SDK = **Docker** → hubungkan ke repo GitHub yang
   sama (atau push langsung ke git remote milik Space) dengan **Root Directory / lokasi
   Dockerfile = `services/asr-suggest`**. **Pilih visibility "Private" dulu** sampai dua
   temuan Critical di atas selesai diperbaiki.
4. **Isi semua secret** dari tabel di atas lewat **Settings → Repository secrets** milik
   Space. Biarkan `ALLOW_DEV_TOKEN` kosong.
5. Setelah Space aktif, salin URL `https://<nama-space>.hf.space`-nya, lalu:
   - set sebagai `CORS_ORIGINS` (gabungkan dengan origin lain yang diizinkan) di secrets Space,
   - set sebagai alamat backend ASR di frontend (`localStorage.setItem('asrHttp', ...)` atau
     lewat UI pengaturan nanti) supaya frontend yang sudah live bisa bicara ke Space yang
     sudah live.
6. **Setup domain di cPanel** — lihat panduan detail langkah-demi-langkah di bawah.
7. Kalau nanti mau pakai domain sendiri juga untuk Space (bukan cuma frontend), pastikan
   sudah siapkan budget HF PRO dulu — lihat bagian "Biaya custom domain" di dokumen
   arsitektur.
8. Begitu `services/auth-laravel/` sudah jadi dan bisa menerbitkan token asli: hapus
   ketergantungan frontend pada `/dev/token` sepenuhnya, dan `ALLOW_DEV_TOKEN` tetap kosong
   selamanya di Space publik.

---

## Panduan detail: setup domain di cPanel (Hostinger / Biznet Gio)

Bagian ini menjelaskan langkah paling konkret — mengarahkan `interviewer.rafancloud.com` ke
Vercel, tanpa memindahkan domain `rafancloud.com` ke mana pun. Domain tetap terdaftar dan
dikelola di hosting cPanel-mu; yang berubah cuma satu record DNS untuk satu subdomain.

### Langkah 1 — Ambil target CNAME dari Vercel dulu

1. Buka dashboard project Vercel yang sudah kamu deploy (langkah 2 di atas).
2. Masuk ke **Settings → Domains**.
3. Ketik `interviewer.rafancloud.com` di kolom tambah domain, klik **Add**.
4. Vercel akan menampilkan instruksi DNS — biasanya berupa **CNAME record** dengan target
   `cname.vercel-dns.com` (catat persis apa yang ditampilkan di layar kamu, karena nilainya
   bisa berbeda tergantung tipe project).
5. Biarkan tab ini terbuka — status domain akan tertulis "Invalid Configuration" dulu, itu
   normal sampai langkah 2 selesai.

### Langkah 2 — Masuk ke Zone Editor di cPanel

1. Login ke panel hosting (Hostinger: hPanel, Biznet Gio: cPanel langsung — biasanya di URL
   seperti `https://namadomain:2083` atau lewat portal member hosting-mu).
2. Cari menu **"Zone Editor"** atau **"DNS Zone Editor" / "Advanced Zone Editor"** — biasanya
   ada di bagian **Domains**.
3. Kalau ada beberapa domain terdaftar, pilih **`rafancloud.com`** dari daftar, klik
   **Manage**.

### Langkah 3 — Tambahkan CNAME record

1. Klik tombol **"+ Add Record"** atau **"Add CNAME Record"** (tergantung tampilan
   provider).
2. Isi field-nya:
   - **Name / Host**: ketik `interviewer` saja (bukan `interviewer.rafancloud.com` lengkap —
     cPanel otomatis menambahkan `.rafancloud.com` di belakang; kalau tampilan minta domain
     lengkap dengan titik di akhir, isi `interviewer.rafancloud.com.`).
   - **Type**: pilih **CNAME**.
   - **TTL**: biarkan default (biasanya 14400 detik). Kalau mau tes cepat, boleh diganti ke
     300 detik dulu, lalu naikkan lagi setelah semua terkonfirmasi jalan.
   - **Record / Points to / Target**: tempel persis nilai yang ditampilkan Vercel di Langkah
     1 (contoh: `cname.vercel-dns.com`).
3. **Cek dulu apakah sudah ada record lama** dengan nama host `interviewer` (misalnya A
   record peninggalan setup lama) — kalau ada, **hapus dulu**, karena satu nama host tidak
   boleh punya CNAME sekaligus record lain yang bentrok.
4. Klik **Save / Add Record**.

### Langkah 4 — Tunggu propagasi & verifikasi

1. Propagasi DNS biasanya makan waktu beberapa menit sampai beberapa jam (jarang lebih dari
   24 jam). Cek statusnya lewat situs seperti `whatsmydns.net` (masukkan
   `interviewer.rafancloud.com`, tipe CNAME), atau command:
   ```
   nslookup interviewer.rafancloud.com
   ```
   Kalau hasilnya sudah menunjuk ke target Vercel, berarti sudah propagasi.
2. Balik ke tab Vercel (Langkah 1) — status domain akan otomatis berubah dari "Invalid
   Configuration" jadi tanda centang hijau begitu Vercel mendeteksi DNS-nya benar. Vercel
   otomatis menerbitkan sertifikat SSL (HTTPS) gratis di titik ini — tidak perlu setup
   manual apa pun untuk HTTPS.
3. Buka `https://interviewer.rafancloud.com` di browser — harus menampilkan frontend yang
   sama persis dengan yang sudah kamu deploy di Vercel.

### Catatan penting

- **Root domain `rafancloud.com` tidak terpengaruh sama sekali** — record yang kamu tambah
  cuma untuk subdomain `interviewer`, jadi apa pun yang sekarang jalan di `rafancloud.com`
  (misalnya website utama di hosting cPanel) tetap jalan seperti biasa.
- **Belum perlu buat subdomain untuk backend ASR** (`asr-interviewer.rafancloud.com` atau
  sejenisnya) — itu cuma perlu kalau nanti upgrade ke HF PRO. Untuk sekarang, frontend cukup
  memanggil URL default `*.hf.space` langsung sebagai alamat backend (diisi lewat
  `localStorage.setItem('asrHttp', 'https://<nama-space>.hf.space')`).
- **Belum perlu buat subdomain untuk auth/Laravel** — service itu belum ada kodenya
  (`services/auth-laravel/` masih placeholder).
