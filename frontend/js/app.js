import { pipe } from './audio-pipeline.js';
import { EchoDetector } from './echo-detect.js';
import { extractPdfText } from './pdf-extract.js';
import { StateMachine } from './state-machine.js';
import { Timeline } from './timeline.js';
import { WSManager } from './ws-manager.js';

const HTTP_BASE = localStorage.getItem('asrHttp') || 'http://127.0.0.1:8000';
const WS_BASE = HTTP_BASE.replace(/^http/, 'ws');
const SESSION_ID = crypto.randomUUID();

const $ = (id) => document.getElementById(id);
const timeline = new Timeline($('timeline'));

const sm = new StateMachine((next, prev, reason) => {
  $('state').textContent = next + (reason ? ` (${reason})` : '');
  $('state').dataset.state = next;
  $('btnStart').disabled = !sm.can('REQUESTING_MIC');
  $('btnStop').disabled = !sm.can('STOPPING');
  console.info(`[sm] ${prev} -> ${next}${reason ? ' :: ' + reason : ''}`);
});

let ctx = null;
let micStream = null;
let sysStream = null;
let wsCandidate = null;
let wsInterviewer = null;
let nodes = [];
let echo = null;
const utterances = [];
let totalBufferDroppedSec = 0;

// Guide 1 point 5: pay the cold start now, while the user is still reading the page,
// not at the moment they press Start.
(async function healthPing() {
  try {
    const r = await fetch(`${HTTP_BASE}/health`, { cache: 'no-store' });
    const j = await r.json();
    $('health').textContent = `ASR siap · model ${j.model} · auth ${j.auth ? 'on' : 'off'}`;
    $('health').className = 'ok';
  } catch {
    $('health').textContent = 'ASR tidak terjangkau — jalankan server dulu';
    $('health').className = 'bad';
  }
})();

async function getToken() {
  const r = await fetch(`${HTTP_BASE}/dev/token?session=${SESSION_ID}`);
  if (!r.ok) throw new Error('token request failed');
  return (await r.json()).token;
}

function wsUrl(token) {
  // bug-hunter H3: Auto|ID|EN selector, sent once at connect time (backend pins Whisper's
  // language= for the whole session rather than re-detecting per window when not Auto).
  const lang = $('langHint')?.value || 'auto';
  return `${WS_BASE}/stream?session=${SESSION_ID}&token=${encodeURIComponent(token)}&lang=${lang}`;
}

function setChannelStatus(channel, live) {
  const el = $(channel === 'candidate' ? 'statusCandidate' : 'statusInterviewer');
  el.textContent = live ? 'LIVE' : 'DEAD';
  el.className = live ? 'chan-status ok' : 'chan-status bad';
}

function setLevel(channel, rms) {
  const bar = $(channel === 'candidate' ? 'vuCandidate' : 'vuInterviewer');
  bar.style.width = `${Math.min(100, rms * 400)}%`;
  echo?.observe(channel, rms);
}

function onTranscript(msg) {
  if (msg?.type === 'translation') {
    timeline.addTranslation(msg.ref, msg.text);
    return;
  }
  // bug-hunter H4: the backend never silently discards audio without saying so anymore -
  // surface it immediately rather than leaving the user to notice missing transcript later.
  if (msg?.type === 'buffer_drop') {
    totalBufferDroppedSec += msg.dropped_sec || 0;
    $('mBufferDropped').textContent = totalBufferDroppedSec.toFixed(1);
    const warn = $('bufferWarn');
    warn.hidden = false;
    warn.textContent =
      `Pipeline tertinggal — ${msg.dropped_sec}s audio channel ${msg.ch} terlewat. ` +
      `Coba bicara lebih pelan/berjeda, atau turunkan WHISPER_MODEL kalau ini sering terjadi.`;
    return;
  }
  if (!msg?.text) return;
  timeline.add(msg);
  utterances.push(msg);
  if (utterances.length > 50) utterances.shift();
  $('mAsr').textContent = msg.asr_latency_ms ?? '–';

  // Enable Smart Answer button once the interviewer has said something.
  if (msg.ch === 'interviewer' && msg.final) {
    $('btnSmartAnswer').disabled = false;
  }
}

async function requestSuggestion() {
  // Find the most recent interviewer utterance to use as the question.
  const lastInterviewer = [...utterances].reverse().find((u) => u.ch === 'interviewer' && u.final);
  if (!lastInterviewer) {
    $('suggestion').textContent = 'Belum ada pertanyaan interviewer di timeline.';
    $('suggestion').className = 'muted';
    return;
  }

  const box = $('suggestion');
  box.textContent = 'Menyiapkan saran…';
  box.className = 'muted';
  const btn = $('btnSmartAnswer');
  btn.disabled = true;
  btn.textContent = 'Memproses…';

  const t0 = performance.now();
  try {
    // Always fetch a fresh token — the session token (set at WS-connect time) may have
    // expired by TOKEN_TTL_SEC=120 before the user decides to press Smart Answer.
    const token = await getToken();
    const r = await fetch(`${HTTP_BASE}/suggest`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        session: SESSION_ID,
        token,
        question: lastInterviewer.text,
        utterances: utterances.slice(-8),
        portfolio: $('portfolio').value,
        low_confidence: !!lastInterviewer.low_conf,
      }),
    });
    const j = await r.json();
    box.textContent = j.text || 'Saran tidak tersedia.';
    box.className = j.ok ? '' : 'muted';
  } catch {
    // Transcription must survive the LLM being down (guide 10 point 7).
    box.textContent = 'Saran tidak tersedia.';
    box.className = 'muted';
  }
  $('mClaude').textContent = Math.round(performance.now() - t0);
  btn.disabled = false;
  btn.textContent = 'Smart Answer ✦';
}

async function startDialog() {
  if (!sm.transition('REQUESTING_MIC')) return;
  try {
    micStream = await navigator.mediaDevices.getUserMedia({
      audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
    });

    sm.transition('REQUESTING_DISPLAY');
    sysStream = await navigator.mediaDevices.getDisplayMedia({ video: true, audio: true });
    if (sysStream.getAudioTracks().length === 0) {
      throw new Error('tab audio tidak dibagikan — centang "Share tab audio"');
    }
    sysStream.getVideoTracks().forEach((t) => t.stop());   // only the audio is needed

    sm.transition('CONNECTING');
    // Pass a factory so every reconnect fetches a fresh token — if the session
    // outlives TOKEN_TTL_SEC the old token would be rejected (4401) and the
    // channel would go permanently DEAD (ws_reconnects spam + frames dropped).
    const wsUrlFactory = () => getToken().then((t) => wsUrl(t));
    wsCandidate = new WSManager(wsUrlFactory, {
      onMessage: onTranscript,
      onStateChange: (s) => setChannelStatus('candidate', s === 'open'),
    });
    wsInterviewer = new WSManager(wsUrlFactory, {
      onMessage: onTranscript,
      onStateChange: (s) => setChannelStatus('interviewer', s === 'open'),
    });

    // One context for both streams; asking for 16 kHz lets the browser resample with a
    // proper filter instead of the aliasing-prone naive decimation in the old guide.
    ctx = new AudioContext({ sampleRate: 16000 });
    await ctx.resume();
    await ctx.audioWorklet.addModule('./worklets/pcm-processor.js');

    echo = new EchoDetector({
      onDetect: (r) => {
        $('echoWarn').hidden = false;
        $('echoWarn').textContent =
          `Pakai headphone — transkrip Anda sedang tercampur (${Math.round(r * 100)}% tumpang tindih).`;
      },
    });

    nodes = [
      await pipe(micStream, 'candidate', wsCandidate, ctx, setLevel),
      await pipe(sysStream, 'interviewer', wsInterviewer, ctx, setLevel),
    ];

    micStream.getAudioTracks()[0].onended = () => sm.transition('ERROR', 'mic-ended');
    sysStream.getAudioTracks()[0].onended = () => sm.transition('ERROR', 'display-ended');

    sm.transition('LIVE');
  } catch (err) {
    sm.transition('ERROR', err.message || String(err));
    await stopDialog();
  }
}

async function stopDialog() {
  if (sm.is('IDLE', 'STOPPED')) return;
  sm.transition('STOPPING');

  [micStream, sysStream].forEach((s) => s?.getTracks().forEach((t) => t.stop()));
  nodes.forEach(({ node, src }) => { try { src.disconnect(); node.disconnect(); } catch {} });
  wsCandidate?.close();
  wsInterviewer?.close();
  clearTimeout(suggestTimer);
  if (ctx && ctx.state !== 'closed') await ctx.close();   // releases the audio hardware

  micStream = sysStream = ctx = null;
  wsCandidate = wsInterviewer = null;
  nodes = [];
  echo = null;
  setChannelStatus('candidate', false);
  setChannelStatus('interviewer', false);

  sm.transition('STOPPED');
  sm.transition('IDLE');
}

setInterval(() => {
  $('mDropped').textContent =
    (wsCandidate?.stats.dropped || 0) + (wsInterviewer?.stats.dropped || 0);
  $('mReconnects').textContent =
    (wsCandidate?.stats.reconnects || 0) + (wsInterviewer?.stats.reconnects || 0);
}, 1000);

$('btnStart').addEventListener('click', startDialog);
$('btnStop').addEventListener('click', stopDialog);
$('btnClear').addEventListener('click', () => {
  timeline.clear();
  utterances.length = 0;
  $('btnSmartAnswer').disabled = true;
  $('suggestion').textContent = 'Tekan "Smart Answer" setelah interviewer bertanya.';
  $('suggestion').className = 'muted';
});
$('btnSmartAnswer').addEventListener('click', requestSuggestion);
window.addEventListener('beforeunload', () => { stopDialog(); });

// F-2: extraction is client-side only; the result just fills the existing #portfolio
// textarea (still editable) — /suggest and its payload shape are unchanged.
$('portfolioFile')?.addEventListener('change', async (e) => {
  const file = e.target.files[0];
  e.target.value = ''; // allow re-selecting the same file name after an error
  if (!file) return;

  const status = $('portfolioStatus');
  status.textContent = 'Mengekstrak PDF…';
  status.className = 'muted';
  try {
    const { text, truncated, pages } = await extractPdfText(file);
    $('portfolio').value = text;
    if (!$('portfolioName').value.trim()) {
      $('portfolioName').value = file.name.replace(/\.pdf$/i, '');
    }
    status.textContent = truncated
      ? `Diekstrak ${pages} halaman — dipotong ke ${text.length.toLocaleString('id-ID')} karakter.`
      : `Diekstrak ${pages} halaman.`;
    status.className = 'ok';
  } catch (err) {
    status.textContent = err.message || 'Gagal mengekstrak PDF.';
    status.className = 'bad';
  }
});

// Riwayat portfolio (ADR Addendum 2026-08-11 (3)): a fresh token is fetched for every
// portfolio call rather than reusing `sessionToken` (only set once Start Dialog runs, and
// TOKEN_TTL_SEC=120 could have lapsed by the time the user acts on the picker/save/delete).
async function loadPortfolioList() {
  const picker = $('portfolioPicker');
  try {
    const token = await getToken();
    const r = await fetch(`${HTTP_BASE}/portfolios?session=${SESSION_ID}&token=${encodeURIComponent(token)}`);
    if (!r.ok) throw new Error('list failed');
    const rows = await r.json();
    const keep = picker.value;
    picker.innerHTML = '<option value="">— pilih dari riwayat —</option>';
    for (const row of rows) {
      const opt = document.createElement('option');
      opt.value = row.id;
      opt.textContent = row.name;
      picker.appendChild(opt);
    }
    picker.value = rows.some((row) => String(row.id) === keep) ? keep : '';
    $('btnDeletePortfolio').disabled = !picker.value;
  } catch {
    // Convenience layer only - a failed list load must never block manual paste or PDF
    // upload into #portfolio, so this stays silent beyond leaving the dropdown as-is.
  }
}

loadPortfolioList();

$('portfolioPicker')?.addEventListener('change', async (e) => {
  const id = e.target.value;
  $('btnDeletePortfolio').disabled = !id;
  if (!id) return;

  const status = $('portfolioStatus');
  try {
    const token = await getToken();
    const r = await fetch(`${HTTP_BASE}/portfolios/${id}?session=${SESSION_ID}&token=${encodeURIComponent(token)}`);
    if (!r.ok) throw new Error('gagal memuat CV dari riwayat');
    const record = await r.json();
    $('portfolio').value = record.content;
    $('portfolioName').value = record.name;
    status.textContent = `Dimuat dari riwayat: ${record.name}`;
    status.className = 'ok';
  } catch (err) {
    status.textContent = err.message || 'Gagal memuat dari riwayat.';
    status.className = 'bad';
  }
});

$('btnSavePortfolio')?.addEventListener('click', async () => {
  const status = $('portfolioStatus');
  const name = $('portfolioName').value.trim();
  const content = $('portfolio').value;
  if (!name) {
    status.textContent = 'Isi nama CV dulu sebelum menyimpan.';
    status.className = 'bad';
    return;
  }
  if (!content.trim()) {
    status.textContent = 'Textarea portfolio masih kosong.';
    status.className = 'bad';
    return;
  }
  try {
    const token = await getToken();
    const r = await fetch(`${HTTP_BASE}/portfolios`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session: SESSION_ID, token, name, content }),
    });
    if (!r.ok) throw new Error('gagal menyimpan CV ke riwayat');
    status.textContent = `Tersimpan sebagai "${name}".`;
    status.className = 'ok';
    await loadPortfolioList();
  } catch (err) {
    status.textContent = err.message || 'Gagal menyimpan.';
    status.className = 'bad';
  }
});

$('btnDeletePortfolio')?.addEventListener('click', async () => {
  const picker = $('portfolioPicker');
  const id = picker.value;
  if (!id) return;

  const status = $('portfolioStatus');
  try {
    const token = await getToken();
    const r = await fetch(
      `${HTTP_BASE}/portfolios/${id}?session=${SESSION_ID}&token=${encodeURIComponent(token)}`,
      { method: 'DELETE' }
    );
    if (!r.ok) throw new Error('gagal menghapus item riwayat');
    if ($('portfolioName').value.trim() && picker.selectedOptions[0]?.textContent === $('portfolioName').value.trim()) {
      $('portfolio').value = '';
      $('portfolioName').value = '';
    }
    status.textContent = 'Item riwayat dihapus.';
    status.className = 'ok';
    await loadPortfolioList();
  } catch (err) {
    status.textContent = err.message || 'Gagal menghapus.';
    status.className = 'bad';
  }
});
