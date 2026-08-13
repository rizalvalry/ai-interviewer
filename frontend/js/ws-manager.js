export class WSManager {
  /**
   * urlOrFactory: either a static ws:// string OR an async () => string factory.
   * A factory is called on EVERY open() — including reconnects — so the token it
   * returns is always fresh.  Pass a factory when TOKEN_TTL_SEC < expected session
   * duration; pass a string only for very short-lived connections (tests, etc.).
   */
  constructor(urlOrFactory, { onMessage, onStateChange } = {}) {
    this._urlFactory = typeof urlOrFactory === 'function'
      ? urlOrFactory
      : () => Promise.resolve(urlOrFactory);
    this.onMessage = onMessage;
    this.onStateChange = onStateChange;
    this.q = [];
    this.MAXQ = 30;                  // ~10 s of 320 ms frames
    this.retry = 0;                  // must be a number from the start or 2**retry is NaN
    this.closed = false;
    this.timer = null;
    this.stats = { reconnects: 0, dropped: 0, sent: 0 };
    this.open();
  }

  async open() {
    if (this.closed) return;
    let url;
    try {
      url = await this._urlFactory();
    } catch (err) {
      // Token fetch failed (server unreachable, etc.) — back off and retry.
      if (this.closed) return;
      this.onStateChange?.('error');
      const delay = Math.min(1000 * 2 ** this.retry++, 10000);
      this.timer = setTimeout(() => this.open(), delay);
      return;
    }
    // WI-A3: open() is async - close() can be called during the `await` above (e.g. Stop
    // clicked while a fresh token was still in flight). Without this check the closed
    // manager would open a brand new WebSocket right after being told to shut down.
    if (this.closed) return;
    this.ws = new WebSocket(url);
    this.ws.binaryType = 'arraybuffer';

    this.ws.onopen = () => {
      this.retry = 0;
      this.onStateChange?.('open');
      const pending = this.q;
      this.q = [];
      for (const b of pending) this.ws.send(b);
    };

    this.ws.onmessage = (e) => {
      if (typeof e.data === 'string') {
        try { this.onMessage?.(JSON.parse(e.data)); } catch { /* ignore non-JSON */ }
      }
    };

    this.ws.onclose = (e) => {
      if (this.closed) return;
      this.onStateChange?.('closed', e.code, e.reason);
      if (e.code === 4401) return;  // auth rejection is terminal; retrying just spams
      this.stats.reconnects++;
      const delay = Math.min(1000 * 2 ** this.retry++, 10000);
      this.timer = setTimeout(() => this.open(), delay);
    };

    this.ws.onerror = () => this.onStateChange?.('error');
  }

  send(buf) {
    if (this.closed) return;
    if (this.ws?.readyState === WebSocket.OPEN) {
      if (this.ws.bufferedAmount > 512 * 1024) { this.stats.dropped++; return; }
      this.ws.send(buf);
      this.stats.sent++;
    } else {
      this.q.push(buf);
      if (this.q.length > this.MAXQ) { this.q.shift(); this.stats.dropped++; }
    }
  }

  close() {
    // Without this flag the onclose handler schedules a reconnect after an intentional stop.
    this.closed = true;
    clearTimeout(this.timer);
    this.q = [];
    try { this.ws?.close(); } catch { /* already closing */ }
  }
}
