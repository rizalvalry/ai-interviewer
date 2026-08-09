# Panduan "Start Dialog" v2 — Produksi: Performa, Akurasi, Latency, Anti-Halusinasi, Anti-Bug

Revisi menyeluruh dari panduan sebelumnya. Target: pipeline dual-audio (mic kandidat +
audio interviewer) yang **cepat (<1 dtk interim)**, **akurat (label & teks benar)**,
**tidak berhalusinasi**, dan **tahan banting** (recovery otomatis, resource bersih).

> Kejujuran engineering: "zero bug" tidak bisa dijamin oleh dokumen manapun — yang bisa
> dijamin adalah *disiplin* yang membuat bug jarang, cepat terdeteksi, dan tidak fatal.
> Bagian §8–§10 adalah disiplin itu.

---

## 0. Arsitektur target (tetap sama, dipertegas)

```
[Start Dialog]
   ├─ mic (candidate)      ─┐  1 AudioContext bersama, 2 AudioWorkletNode
   └─ tab/system (interviewer) ─┘
            │  PCM16 mono 16kHz, frame 320 ms, seq-number
            ▼  WebSocket biner per channel (auto-reconnect + buffer)
   ┌─────────────────────────────┐
   │ svc-asr (FastAPI, HF Space) │  energy-gate → VAD → Whisper (anti-halusinasi)
   └─────────────┬───────────────┘
                 │ interim + final (ber-label, ber-confidence)
                 ▼
        Timeline UI (2 warna)  →  utterance FINAL interviewer → Claude (async, debounced)
```

---

## 1. Latency: anggaran & cara menekannya

Target anggaran end-to-end (bicara → teks tampil):

| Tahap | Target |
|---|---|
| Capture + resample (worklet) | < 5 ms |
| Buffering frame | 320 ms (trade-off sadar) |
| Network ke HF Space | 50–150 ms (dari Indonesia) |
| ASR inference | 300–700 ms (CPU int8, model kecil) |
| Render UI | < 16 ms |
| **Total interim** | **≈ 0.7–1.2 dtk** |

Teknik penekan latency:

1. **`beam_size=1, best_of=1, temperature=0.0`** untuk pass streaming — beam search besar
   menaikkan latency tanpa gain berarti pada ucapan pendek.
2. **Dua-pass (opsional, hasil terbaik):** interim pakai `tiny`/`base` (cepat, boleh salah),
   lalu koreksi utterance final pakai `small` di background → UI terasa instan, hasil akhir akurat.
3. **`word_timestamps=False`** di pass interim (fitur ini mahal).
4. **Warm-up model saat boot**: transcribe 1 dtk audio dummy di `startup` event supaya
   request pertama tidak kena JIT/alokasi awal.
5. **Health-ping dari frontend saat halaman dibuka** (bukan saat Start Dialog) — cold start
   HF free-tier bisa puluhan detik; jangan biarkan user menunggunya di momen kritis.
6. **Frame 320 ms** (bukan 1–2 dtk): cukup kecil untuk responsif, cukup besar agar
   overhead WS/syscall rendah.
7. Kalau CPU free-tier tetap kurang: **ZeroGPU** (kuota harian) atau streaming ASR cloud
   (Deepgram/AssemblyAI/Azure Speech) yang punya interim bawaan. Itu jalur latency terbaik,
   trade-off biaya.

---

## 2. Akurasi: keputusan yang menentukannya

1. **Dua stream terpisah** → label pembicara 100% deterministik, tanpa diarization.
2. **Headphone wajib** (enforce di UI, bukan sekadar saran): tampilkan blocking modal
   "Gunakan headphone" + deteksi heuristik echo (lihat §5.4).
3. **16 kHz mono PCM** — resample di klien dengan filter, bukan naive drop-sample (kode §4).
   Naive picking menyebabkan aliasing → akurasi ASR turun.
4. **VAD endpointing** (bukan potong tiap N detik) → batas kalimat alami, kata tidak terpotong.
5. **Model**: `base` minimum, `small` bila muat. Auto-detect bahasa per-utterance untuk
   code-switching ID↔EN; jangan pin `language="id"` kalau interviewer bicara English.
6. **Overlap 0.5 dtk** antar window transkripsi + **dedup di boundary** (§3.5) supaya
   overlap tidak menghasilkan teks dobel.

---

## 3. Anti-Halusinasi (bagian terpenting revisi ini)

### 3.1 Kenali masalahnya
Whisper dilatih dari audio internet ber-subtitle. Saat diberi **hening, noise, musik, atau
audio sangat pendek**, ia cenderung "mengarang" teks yang sering muncul di data latihnya:
"Terima kasih telah menonton", "Thanks for watching", "Subscribe...", atau **mengulang
frasa yang sama berkali-kali**. Di aplikasi interview ini fatal — saran Claude bisa dibangun
dari kalimat yang tidak pernah diucapkan.

### 3.2 Pertahanan berlapis (defense in depth)

**Lapis 1 — Energy gate (sebelum ASR, di server):**
```python
import numpy as np

def is_audible(pcm: np.ndarray, thresh_db: float = -45.0) -> bool:
    rms = np.sqrt(np.mean(pcm ** 2) + 1e-12)
    db = 20 * np.log10(rms + 1e-12)
    return db > thresh_db
# Jika hening → JANGAN panggil Whisper sama sekali. Halusinasi 0% untuk input yang tak diproses.
```

**Lapis 2 — VAD ketat:**
```python
segments, info = asr.transcribe(
    audio,
    vad_filter=True,
    vad_parameters=dict(
        min_silence_duration_ms=500,
        speech_pad_ms=200,
        threshold=0.5,          # naikkan ke 0.6 kalau lingkungan berisik
    ),
    ...
)
```

**Lapis 3 — Parameter decoding anti-karang:**
```python
    temperature=0.0,
    beam_size=1,
    condition_on_previous_text=False,   # KRUSIAL: cegah halusinasi "menular" antar chunk
    no_speech_threshold=0.6,
    log_prob_threshold=-1.0,
    compression_ratio_threshold=2.4,    # teks repetitif ter-compress tinggi → ditolak
```
`condition_on_previous_text=False` adalah tombol paling berpengaruh untuk streaming:
tanpa ini, satu chunk yang berhalusinasi "menyeret" chunk-chunk berikutnya.

**Lapis 4 — Filter hasil per segmen:**
```python
BLOCKLIST = {
    "terima kasih telah menonton", "thanks for watching",
    "subscribe", "sampai jumpa di video berikutnya",
    "thank you for watching", "like dan subscribe",
}

def keep(seg) -> bool:
    t = seg.text.strip().lower()
    if not t: return False
    if seg.no_speech_prob > 0.5: return False
    if seg.avg_logprob < -1.0: return False
    if (seg.end - seg.start) < 0.3: return False        # segmen <300ms = curiga
    if any(b in t for b in BLOCKLIST): return False
    return True
```

**Lapis 5 — Deteksi repetisi:**
```python
def is_repetitive(text: str, max_ratio: float = 0.5) -> bool:
    words = text.lower().split()
    if len(words) < 6: return False
    return (len(set(words)) / len(words)) < max_ratio   # >50% kata sama = loop halusinasi
```

**Lapis 6 — Dedup boundary overlap:** karena tiap window menyisakan 0.5 dtk overlap,
bandingkan awal teks baru dengan akhir teks sebelumnya (suffix–prefix match sederhana)
dan buang bagian yang sama sebelum dikirim ke UI.

**Peringatan `initial_prompt`:** menaruh istilah domain di `initial_prompt` bisa membantu
kosakata, tapi juga **meningkatkan** risiko halusinasi (model "menyalin" prompt ke output
saat hening). Kalau dipakai, wajib bersama Lapis 1–5. Default: jangan pakai.

### 3.3 Anti-halusinasi di sisi Claude
Transkrip bersih ≠ selesai. Kunci LLM agar tidak menambah fakta:

```text
System prompt (inti):
- Kamu HANYA boleh menggunakan isi transkrip yang diberikan. Jangan menambahkan
  fakta, angka, nama, atau klaim yang tidak ada di transkrip/portfolio kandidat.
- Jika transkrip ambigu atau terpotong, katakan bagian mana yang ambigu —
  jangan menebak isinya.
- Jika pertanyaan interviewer tidak terdengar jelas (confidence rendah ditandai
  [low-confidence]), minta klarifikasi alih-alih menyarankan jawaban.
```
Dan di payload, tandai utterance dengan `avg_logprob` rendah sebagai `[low-confidence]`
supaya Claude tahu mana yang boleh diragukan.

---

## 4. Klien: resample yang benar + worklet efisien

Naive drop-sample (versi lama) menimbulkan aliasing. Cara benar & tetap ringan:
**gunakan `AudioContext({ sampleRate: 16000 })`** — browser modern (Chrome/Edge/Firefox)
akan me-resample internal dengan filter yang benar. Fallback: filter rata-rata sederhana.

```js
// ==== worklets/pcm-processor.js ====
class PCMProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this.buf = new Float32Array(0);
    this.FRAME = 5120;                    // 320 ms @16k
  }
  process(inputs) {
    const ch = inputs[0]?.[0];
    if (ch?.length) {
      const merged = new Float32Array(this.buf.length + ch.length);
      merged.set(this.buf); merged.set(ch, this.buf.length);
      this.buf = merged;
      while (this.buf.length >= this.FRAME) {
        const frame = this.buf.slice(0, this.FRAME);
        this.buf = this.buf.slice(this.FRAME);
        // Transferable → zero-copy antar thread
        this.port.postMessage(frame.buffer, [frame.buffer]);
      }
    }
    return true;
  }
}
registerProcessor('pcm-processor', PCMProcessor);
```

```js
// ==== main thread ====
function f32ToI16(f32) {
  const out = new Int16Array(f32.length);
  for (let i = 0; i < f32.length; i++) {
    const s = Math.max(-1, Math.min(1, f32[i]));
    out[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
  }
  return out;
}

async function pipe(stream, channel, wsMgr, ctx) {
  await ctx.audioWorklet.addModule('/worklets/pcm-processor.js');
  const src  = ctx.createMediaStreamSource(stream);
  const node = new AudioWorkletNode(ctx, 'pcm-processor');
  let seq = 0;

  node.port.onmessage = (e) => {
    const f32 = new Float32Array(e.data);
    const i16 = f32ToI16(f32);
    // header 8 byte: [seq:uint32][ch:uint8][pad:3] + payload PCM
    const buf = new ArrayBuffer(8 + i16.byteLength);
    const dv = new DataView(buf);
    dv.setUint32(0, seq++);
    dv.setUint8(4, channel === 'candidate' ? 0 : 1);
    new Int16Array(buf, 8).set(i16);
    wsMgr.send(buf);                       // manajer WS dengan queue (lihat §5.2)
  };

  src.connect(node);   // JANGAN connect ke destination (feedback!)
  return node;
}

// Start Dialog:
const ctx = new AudioContext({ sampleRate: 16000 });  // SATU ctx untuk dua stream
await ctx.resume();
```

Catatan performa klien:
- **Satu `AudioContext`** untuk kedua stream (dua node) — dua context boros.
- **Transferable buffer** (`postMessage(buf, [buf])`) — zero-copy, bebas GC-churn.
- Render timeline via **`requestAnimationFrame` batching**, bukan re-render per pesan WS.
- Batasi array timeline di memori (mis. 500 entri; sisanya di IndexedDB bila perlu review).

---

## 5. Ketahanan koneksi & sesi (anti-bug kategori jaringan)

### 5.1 State machine eksplisit (wajib)
Sumber bug #1 aplikasi media adalah state implisit. Definisikan:

```
IDLE → REQUESTING_MIC → REQUESTING_DISPLAY → CONNECTING → LIVE
LIVE → (RECONNECTING ↔ LIVE) → STOPPING → STOPPED
setiap state error → ERROR(reason) → IDLE
```
Semua tombol UI hanya mengubah state lewat transisi sah. Tidak ada `startDialog()` yang
bisa dipanggil dua kali (guard: hanya valid dari IDLE).

### 5.2 WebSocket manager: reconnect + queue + backpressure
```js
class WSManager {
  constructor(url) { this.url = url; this.q = []; this.MAXQ = 30; this.open(); }
  open() {
    this.ws = new WebSocket(this.url);
    this.ws.binaryType = 'arraybuffer';
    this.ws.onopen = () => { this.q.forEach(b => this.ws.send(b)); this.q = []; this.retry = 0; };
    this.ws.onclose = () => setTimeout(() => this.open(),
      Math.min(1000 * 2 ** (this.retry++ || 0), 10000));   // exponential backoff, cap 10s
  }
  send(buf) {
    if (this.ws.readyState === WebSocket.OPEN) {
      if (this.ws.bufferedAmount > 512 * 1024) return;      // backpressure: drop frame lama
      this.ws.send(buf);
    } else {
      this.q.push(buf);
      if (this.q.length > this.MAXQ) this.q.shift();        // buffer max ~10 dtk audio
    }
  }
}
```
- **Seq number** di header (§4) membuat server bisa mendeteksi gap/duplikat setelah reconnect.
- **Heartbeat**: server kirim ping tiap 15 dtk; klien yang 2x tidak balas dianggap mati
  (bersihkan buffer server → tidak ada memory leak per koneksi zombie).

### 5.3 Track lifecycle (sumber bug senyap)
```js
// User menutup share tab / mencabut mic → track "ended", TANPA error JS
sysStream.getAudioTracks()[0].onended = () => sm.transition('ERROR', 'display-ended');
micStream.getAudioTracks()[0].onended = () => sm.transition('ERROR', 'mic-ended');
```
UI harus menampilkan status per-channel (VU meter + LIVE/DEAD) — user harus *melihat*
kalau salah satu sumber mati.

### 5.4 Deteksi echo/bleed (enforce headphone)
Heuristik murah: kalau **kedua channel** aktif suara bersamaan >70% waktu selama 10 dtk
pertama, kemungkinan besar suara interviewer bocor ke mic (tanpa headphone) → tampilkan
peringatan blocking "Pakai headphone, transkrip Anda sedang tercampur."

### 5.5 Cleanup total saat Stop (anti resource-leak)
```js
async function stopDialog() {
  sm.transition('STOPPING');
  [micStream, sysStream].forEach(s => s?.getTracks().forEach(t => t.stop()));
  nodes.forEach(n => n.disconnect());
  wsA.close(); wsB.close();
  await ctx.close();                    // lepaskan audio hardware
  sm.transition('STOPPED');
}
// + window.addEventListener('beforeunload', stopDialog)
```
Lupa `ctx.close()` / `track.stop()` = indikator mic browser tetap merah, baterai boros,
dan sesi berikutnya bisa gagal `getUserMedia`.

---

## 6. Server: versi produksi (lengkap dengan semua lapis)

```python
import asyncio, time
import numpy as np
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from faster_whisper import WhisperModel

app = FastAPI()
SR = 16000
MAX_BUF_SEC = 30                     # hard cap buffer per koneksi (anti-OOM)
asr = WhisperModel("base", device="cpu", compute_type="int8")
asr_lock = asyncio.Semaphore(2)      # batasi inference paralel di CPU kecil

@app.on_event("startup")
async def warmup():
    asr.transcribe(np.zeros(SR, dtype=np.float32))   # hangatkan model

@app.get("/health")
async def health(): return {"ok": True}

def transcribe_clean(audio: np.ndarray):
    segs, info = asr.transcribe(
        audio, language=None,
        temperature=0.0, beam_size=1,
        condition_on_previous_text=False,
        vad_filter=True,
        vad_parameters=dict(min_silence_duration_ms=500, speech_pad_ms=200, threshold=0.5),
        no_speech_threshold=0.6, log_prob_threshold=-1.0,
        compression_ratio_threshold=2.4,
    )
    out = []
    for s in segs:
        if not keep(s):            # filter §3.2 lapis 4
            continue
        if is_repetitive(s.text):  # lapis 5
            continue
        out.append({"text": s.text.strip(),
                    "conf": float(s.avg_logprob),
                    "low": s.avg_logprob < -0.7})
    return out, info.language

@app.websocket("/stream")
async def stream(ws: WebSocket):
    await ws.accept()
    buf = np.zeros(0, dtype=np.float32)
    last_seq, last_text = -1, ""
    try:
        while True:
            data = await asyncio.wait_for(ws.receive_bytes(), timeout=30)  # idle timeout
            seq = int.from_bytes(data[0:4], "big")
            ch  = "candidate" if data[4] == 0 else "interviewer"
            if seq <= last_seq:                    # duplikat pasca-reconnect → buang
                continue
            last_seq = seq
            pcm = np.frombuffer(data[8:], dtype=np.int16).astype(np.float32) / 32768.0
            buf = np.concatenate([buf, pcm])[-SR * MAX_BUF_SEC:]   # hard cap

            if len(buf) >= SR * 2:
                window, buf = buf, buf[-SR // 2:].copy()           # sisakan overlap 0.5s
                if not is_audible(window):                          # lapis 1: energy gate
                    continue
                async with asr_lock:
                    segs, lang = await asyncio.to_thread(transcribe_clean, window)
                for s in segs:
                    text = dedup_boundary(last_text, s["text"])     # lapis 6
                    if not text:
                        continue
                    last_text = s["text"]
                    await ws.send_json({"ch": ch, "text": text, "lang": lang,
                                        "final": True, "low_conf": s["low"],
                                        "t": time.time()})
    except (WebSocketDisconnect, asyncio.TimeoutError):
        pass   # buffer lokal ter-GC otomatis; tidak ada state global per-koneksi
```

Poin produksi:
- `asyncio.to_thread` → inference tidak memblokir event loop (koneksi lain tetap hidup).
- `Semaphore(2)` → dua sesi bersamaan tidak saling membunuh CPU.
- **Hard cap buffer 30 dtk** dan **idle timeout 30 dtk** → tidak ada OOM/koneksi zombie.
- Tidak ada state global per user → restart Space aman kapan saja.

---

## 7. Integrasi Claude yang tidak menambah latency & tidak halusinasi

- Panggil **hanya** pada utterance `final` channel interviewer, **debounce 800 ms**
  (tunggu interviewer benar-benar selesai).
- **Async & non-blocking** — transkripsi tidak pernah menunggu Claude.
- Kirim konteks minimal: 6 utterance terakhir + pertanyaan final + (opsional) ringkasan
  portfolio. Jangan kirim seluruh timeline (biaya + latency + noise).
- System prompt anti-karang (§3.3) + tanda `[low-confidence]`.
- **Prompt caching** untuk system prompt + portfolio (dikirim berulang tiap sesi) → biaya
  input turun drastis.
- Timeout 15 dtk + retry 1x; kalau gagal, UI menampilkan "saran tidak tersedia" —
  aplikasi inti (transkrip) tetap jalan penuh.

---

## 8. Disiplin anti-bug: checklist pengujian sebelum rilis

**Unit/komponen**
- [ ] `f32ToI16`: nilai -1, 0, +1, clipping.
- [ ] `dedup_boundary`: overlap penuh, sebagian, tanpa overlap.
- [ ] `is_repetitive` & `keep`: kasus blocklist, segmen pendek, logprob rendah.
- [ ] Resample: sine 440 Hz masuk → 440 Hz keluar (bukti tanpa aliasing kasar).

**Integrasi (wajib manual, media sulit di-mock)**
- [ ] Mic-only 10 menit nonstop: memori klien & server datar (tidak menanjak).
- [ ] Hening total 2 menit: **nol** teks muncul (bukti anti-halusinasi bekerja).
- [ ] Musik/noise 1 menit: nol atau nyaris nol teks.
- [ ] Matikan WiFi 10 dtk saat LIVE → nyala lagi: reconnect otomatis, tidak ada teks dobel
      (seq-dedup bekerja), state UI benar.
- [ ] Tutup share-tab di tengah sesi: channel interviewer DEAD terlihat di UI, mic tetap jalan.
- [ ] Cabut/ganti mic di tengah sesi.
- [ ] Stop → Start lagi 5x berturut-turut: tidak ada error `getUserMedia`, indikator mic
      browser padam saat stop (bukti cleanup benar).
- [ ] Dua tab aplikasi sekaligus (user tak sengaja): tidak crash server (semaphore bekerja).
- [ ] Code-switching ID↔EN dalam satu kalimat: hasil tetap terbaca.
- [ ] Tanpa headphone (sengaja): peringatan echo muncul.

**Beban**
- [ ] 2 sesi paralel × 10 menit di CPU free-tier: latency masih dalam anggaran §1?
      Kalau tidak → putuskan sekarang: ZeroGPU / ASR cloud, jangan saat demo.

---

## 9. Observability minimum (bug yang terukur = bug yang cepat mati)

Log terstruktur per sesi (cukup stdout Space + tampilan debug di UI):
- `asr_latency_ms` per window, `ws_reconnects`, `frames_dropped` (backpressure),
  `segments_filtered` (per lapis anti-halusinasi), `claude_latency_ms`, `claude_errors`.
- UI dev-mode: overlay kecil menampilkan angka-angka ini live. Saat ada keluhan
  "kok lambat/aneh", kamu melihat *di tahap mana* masalahnya dalam hitungan detik.

---

## 10. Definisi "sempurna" yang realistis (acceptance criteria)

Rilis layak disebut beres bila semua ini terpenuhi:
1. Interim text tampil **< 1.2 dtk** setelah kata diucapkan (jaringan normal).
2. Sesi hening 2 menit menghasilkan **0 teks** (anti-halusinasi terbukti).
3. Label pembicara **tidak pernah** tertukar (dual-stream by design).
4. Putus jaringan 10 dtk → pulih sendiri tanpa teks hilang/dobel.
5. 10 menit sesi: penggunaan memori klien & server stabil.
6. Stop membebaskan mic (indikator browser padam) dan sesi berikutnya langsung bisa mulai.
7. Kegagalan Claude tidak pernah menghentikan transkripsi.

Kalau ketujuh poin ini hijau, aplikasi sudah "smooth & akurat" dalam arti yang bisa
dipertanggungjawabkan — sisanya adalah iterasi kualitas model (base → small → cloud ASR)
sesuai budget.
