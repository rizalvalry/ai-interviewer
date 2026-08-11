# Instruksi — Bug ASR: ucapan Indonesia tidak tertranskrip + halusinasi frasa pendek

> Handoff dari `project-manager`. Ditulis: 2026-08-11. Prioritas: TINGGI — memblokir
> pemakaian nyata untuk interview berbahasa Indonesia (requirement bisnis: ID adalah warga
> kelas satu, setara EN).
> Disiplin: **diagnosis dulu (bug-hunter), baru fix (developer)**. Jangan langsung menambal
> sebelum hipotesis tervalidasi dengan bukti.

## Gejala (laporan user, live mic, v0.3.0)
- User mengucapkan "selamat sore" → TIDAK muncul di timeline.
- Yang muncul: "Hello." (en, low-conf), "I'm sorry." (en, low-conf), "Hallo!" (de,
  low-conf), "Sorry" — frasa pendek yang tidak pernah diucapkan.
- Kondisi: `WHISPER_MODEL=base`, `language=None` (auto-detect per window ~2s).

## Fase 1 — Diagnosis (validasi hipotesis dengan bukti, bukan tebakan)

Reproduksi: rekam beberapa klip WAV 16kHz pendek (bisa minta user merekam, atau pakai TTS)
berisi ucapan Indonesia ("selamat sore", kalimat interview ID), ucapan EN, dan keheningan/
noise ruangan. Jalankan lewat `transcribe_clean` langsung (test harness kecil) dan catat:
`text`, `language`, `language_probability` (dari `info`), `avg_logprob`, dan keputusan
filter (`filters.keep`, `is_repetitive`, energy gate, VAD).

| # | Hipotesis | Prediksi yang bisa difalsifikasi |
|---|---|---|
| H1 | Model `base` lemah untuk ID → transkrip salah/kosong; `small` menyelesaikan | Klip ID yang gagal di `base` menjadi benar di `small` dengan setting lain identik |
| H2 | Jendela hening/noise lolos energy gate/VAD → halusinasi frasa klasik ("Hello", "I'm sorry", "Thank you") | Klip hening menghasilkan frasa tsb dengan `avg_logprob` rendah / `no_speech_prob` tinggi; menaikkan gate/VAD atau memfilter berdasarkan `language_probability` menghilangkannya |
| H3 | Auto-detect bahasa per window pendek tidak stabil (en→de flapping) | `language_probability` rendah (<~0.6) pada window yang salah deteksi; ucapan lebih panjang terdeteksi benar |

Tulis hasil: hipotesis mana yang terkonfirmasi (dengan angka), mana yang gugur, confidence
rating. Jika ketiganya berkontribusi, sebutkan porsinya.

## Fase 2 — Fix (hanya setelah Fase 1; spesifikasi arah, detail mengikuti temuan)

Kandidat fix yang SUDAH disetujui arah-nya (pilih kombinasi sesuai bukti Fase 1):
1. **Default model naik ke `small`** (`WHISPER_MODEL=small` sebagai default baru di
   config/.env.example) — bila H1 terkonfirmasi. Dokumentasikan dampak CPU di README;
   `base` tetap bisa dipilih via env (runtime tunable, jangan hardcode).
2. **Gating halusinasi lebih ketat** — bila H2: manfaatkan `no_speech_prob` /
   `avg_logprob` / `language_probability` sebagai ambang drop (env-tunable, ikuti pola
   `LOW_CONF_LOGPROB`), dan/atau daftar frasa halusinasi umum yang di-drop bila low-conf.
   Utterance yang di-drop TIDAK ditampilkan di timeline (bukan sekadar badge low-conf).
3. **Stabilisasi deteksi bahasa** — bila H3: ambang `language_probability` (di bawahnya →
   perlakukan sebagai low-conf/drop), dan **selector bahasa di UI**: `Auto | ID | EN`
   (default Auto) yang mengirim hint ke backend → diteruskan sebagai `language=` ke
   Whisper saat bukan Auto. Selector = jalan keluar deterministik saat auto-detect nakal.
4. F-1 tetap konsisten: utterance ID tidak diterjemahkan; pastikan logika arah terjemahan
   memakai bahasa final yang sudah melalui gating (bukan deteksi mentah).

## Batasan
- Semua ambang baru WAJIB env-tunable dengan default aman — jangan hardcode.
- Jangan menurunkan akurasi EN demi ID — eval dua arah.
- Jangan menyentuh arsitektur pipeline (window/overlap) tanpa bukti bahwa itu akarnya.

## Verifikasi & acceptance PM
- [ ] Laporan Fase 1: tabel bukti per hipotesis + confidence.
- [ ] Eval mini ASR dua bahasa: ≥10 klip ID + ≥10 klip EN + ≥5 klip hening/noise →
      transkrip benar untuk ID & EN, NOL frasa halusinasi tampil dari klip hening.
- [ ] "selamat sore" (klip nyata) muncul benar di timeline dengan bahasa `id`.
- [ ] Timeline tidak lagi menampilkan utterance yang di-drop.
- [ ] Suite test hijau (tambah test untuk gating baru); commit per perubahan, push.
- [ ] Tag `v0.3.1` (bugfix) — terpisah dari track portfolio (v0.4.0).
