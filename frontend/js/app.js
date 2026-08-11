import { pipe } from './audio-pipeline.js';
import { EchoDetector } from './echo-detect.js';
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
let suggestTimer = null;
let sessionToken = null;
const utterances = [];

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
  return `${WS_BASE}/stream?session=${SESSION_ID}&token=${encodeURIComponent(token)}`;
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
    timeline.addTranslation(msg.ref_seq, msg.text_id);
    return;
  }
  if (!msg?.text) return;
  timeline.add(msg);
  utterances.push(msg);
  if (utterances.length > 50) utterances.shift();
  $('mAsr').textContent = msg.asr_latency_ms ?? '–';

  // Guide 7: only the interviewer's finals trigger Claude, and only after they stop talking.
  if (msg.ch === 'interviewer' && msg.final) {
    clearTimeout(suggestTimer);
    suggestTimer = setTimeout(() => requestSuggestion(msg), 800);
  }
}

async function requestSuggestion(msg) {
  const box = $('suggestion');
  box.textContent = 'Menyiapkan saran…';
  const t0 = performance.now();
  try {
    const r = await fetch(`${HTTP_BASE}/suggest`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        session: SESSION_ID,
        token: sessionToken,
        question: msg.text,
        utterances: utterances.slice(-6),
        portfolio: $('portfolio').value,
        low_confidence: !!msg.low_conf,
      }),
    });
    const j = await r.json();
    box.textContent = j.text || 'Saran tidak tersedia.';
    box.className = j.ok ? '' : 'muted';
  } catch {
    // Transcription must survive Claude being down (guide 10 point 7).
    box.textContent = 'Saran tidak tersedia.';
    box.className = 'muted';
  }
  $('mClaude').textContent = Math.round(performance.now() - t0);
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
    const token = await getToken();
    sessionToken = token;
    wsCandidate = new WSManager(wsUrl(token), {
      onMessage: onTranscript,
      onStateChange: (s) => setChannelStatus('candidate', s === 'open'),
    });
    wsInterviewer = new WSManager(wsUrl(token), {
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
  sessionToken = null;
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
$('btnClear').addEventListener('click', () => timeline.clear());
window.addEventListener('beforeunload', () => { stopDialog(); });
