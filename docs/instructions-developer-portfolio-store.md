# Instruksi Developer — Penyimpanan Riwayat Portfolio (SQLite + volume)

> Handoff dari `project-manager`. Ditulis: 2026-08-11. Prasyarat: v0.3.0 (Gemini) accepted.
> Keputusan storage: `solution-architect` (ADR Addendum 2026-08-11 (3)) — SQLite stdlib +
> named volume. JANGAN mengganti dengan localStorage, MySQL, atau ORM.

## Tujuan
Upload CV sekali → tersimpan → interview berikutnya tinggal pilih dari riwayat, tanpa
re-upload. Riwayat per-laptop (volume), CV tidak pernah menyentuh git.

## Work items

### WI-13 — Backend: portfolio store (SQLite, nol dependency baru)
- Modul baru `portfolio_store.py`: stdlib `sqlite3`, file DB di path env
  `PORTFOLIO_DB_PATH` (default `/home/user/data/portfolios.db`); buat dir & schema saat
  startup. Tabel: `id INTEGER PK`, `name TEXT NOT NULL`, `content TEXT NOT NULL`,
  `created_at TEXT NOT NULL`. Nama duplikat → replace isi (upsert by name) supaya
  "update CV" natural.
- Endpoint di `app.py`, SEMUA dijaga `auth.verify()` (session+token, pola sama `/suggest`):
  - `GET /portfolios` → daftar `{id, name, created_at, size}` (tanpa content — hemat).
  - `GET /portfolios/{id}` → satu record lengkap (content).
  - `POST /portfolios` → `{name, content}`; validasi: name non-kosong ≤100 char,
    content non-kosong ≤30.000 char (konsisten guard F-2).
  - `DELETE /portfolios/{id}` → hapus.
- SQLite akses via thread aman (koneksi per-request atau `check_same_thread=False` +
  lock — pilihanmu, catat sebagai assumption; volume tulisannya kecil & single-user).
- **Done:** CRUD jalan via curl dengan token; tanpa token → 401; data selamat dari
  `docker compose down && up`.

### WI-14 — Compose: volume data
- `docker-compose.yml`: named volume baru (mis. `portfolio-data:/home/user/data`) di
  service `asr` + env `PORTFOLIO_DB_PATH`. JANGAN menaruh DB di bind-mount folder repo
  (risiko masuk git).
- **Done:** `docker compose down` lalu `up` → riwayat masih ada; `git status` bersih.

### WI-15 — Frontend: picker riwayat portfolio
- Di atas textarea `#portfolio`: dropdown "Pilih dari riwayat" (diisi dari
  `GET /portfolios` setelah token tersedia) + tombol hapus untuk item terpilih.
- Alur simpan: setelah ekstraksi PDF (atau isi manual), field nama (default: nama file
  PDF tanpa ekstensi) + tombol "Simpan ke riwayat" → `POST /portfolios`.
- Pilih item → `GET /portfolios/{id}` → isi textarea (tetap editable; edit tidak
  auto-save — simpan ulang eksplisit).
- Ikuti pola fetch + token yang sudah ada di `app.js`; tanpa framework baru.
- **Done:** upload CV → simpan → reload halaman → pilih dari dropdown → textarea terisi →
  `/suggest` mengutip CV; hapus item → hilang dari daftar.

### WI-16 — Verifikasi
- Test unit untuk `portfolio_store.py` (CRUD, upsert-by-name, guard 30K/nama kosong) +
  test endpoint auth-gate (401 tanpa token) — total suite tetap hijau (baseline 41).
- Smoke end-to-end via compose termasuk siklus down/up untuk bukti persistensi.
- **Done:** bukti test + smoke di laporan.

## Batasan
- Nol dependency baru (sqlite3 stdlib; tanpa ORM, tanpa alembic — schema dibuat idempoten
  saat startup).
- Endpoint portfolio TIDAK boleh tanpa auth — meski localhost, konsisten dengan `/suggest`.
- CV/DB tidak pernah masuk git (volume di luar tree repo).
- Kontrak `/suggest` tidak berubah — frontend tetap mengirim `portfolio` sebagai string.
- Versioning: pull dulu, satu commit per WI, push per WI, tag `v0.4.0` saat WI-13..16
  terverifikasi.

## Acceptance criteria PM
- [ ] Simpan CV → `docker compose down && up` → pilih dari riwayat tanpa re-upload → saran
      mengutip CV.
- [ ] Semua endpoint portfolio: tanpa token → 401.
- [ ] `git status` bersih — tidak ada file DB/CV yang ter-track.
- [ ] Suite test hijau (≥41 + test baru).
- [ ] Commit per-WI ter-push + tag `v0.4.0`.
