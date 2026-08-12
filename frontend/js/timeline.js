const MAX_ENTRIES = 500;

export class Timeline {
  constructor(el) {
    this.el = el;
    this.entries = [];
    this.pending = [];
    this.scheduled = false;
    this.rowsBySeq = new Map(); // seq -> row element, so a late translation can find its utterance
  }

  add(entry) {
    this.entries.push(entry);
    if (this.entries.length > MAX_ENTRIES) this.entries.shift();
    this.pending.push({ kind: 'utt', data: entry });
    this._schedule();
  }

  // F-1: translation arrives as a separate WS message, up to ~3s after the utterance it
  // refers to. Routed through the same pending/rAF queue as new utterances so a burst of
  // translations never forces per-message synchronous layout either.
  addTranslation(refSeq, textId) {
    this.pending.push({ kind: 'translation', refSeq, textId });
    this._schedule();
  }

  _schedule() {
    // Guide 4: batch through rAF. Rendering per WS message drops frames once the
    // transcript grows, because every message forces a synchronous layout.
    if (!this.scheduled) {
      this.scheduled = true;
      requestAnimationFrame(() => this.flush());
    }
  }

  flush() {
    this.scheduled = false;
    const frag = document.createDocumentFragment();
    for (const item of this.pending) {
      if (item.kind === 'utt') {
        frag.appendChild(this.render(item.data));
      } else {
        this._applyTranslation(item.refSeq, item.textId);
      }
    }
    this.pending = [];

    this.el.appendChild(frag);
    while (this.el.childElementCount > MAX_ENTRIES) {
      const first = this.el.firstElementChild;
      this.rowsBySeq.delete(Number(first?.dataset.seq));
      this.el.removeChild(first);
    }
    this.el.scrollTop = this.el.scrollHeight;
  }

  render(e) {
    // Bubble wrapper: full-width, aligned by speaker (candidate=left, interviewer=right)
    const wrap = document.createElement('div');
    wrap.className = `utt-wrap utt-wrap--${e.ch}`;

    const bubble = document.createElement('div');
    bubble.className = `utt utt--${e.ch}${e.low_conf ? ' utt--low' : ''}`;
    if (e.seq != null) {
      bubble.dataset.seq = e.seq;
      this.rowsBySeq.set(e.seq, bubble);
    }

    // Speaker label + meta on one line above the text
    const header = document.createElement('div');
    header.className = 'utt__header';
    const who = document.createElement('span');
    who.className = 'utt__who';
    who.textContent = e.ch === 'candidate' ? 'Kandidat' : 'Interviewer';
    const meta = document.createElement('span');
    meta.className = 'utt__meta';
    meta.textContent = `${e.lang || '?'}${e.low_conf ? ' · low-conf' : ''}`;
    header.append(who, meta);

    // Main transcript text
    const text = document.createElement('p');
    text.className = 'utt__text';
    text.textContent = e.text;

    // Translation appears below main text when available (F-1)
    const translation = document.createElement('p');
    translation.className = 'utt__translation';
    translation.hidden = true;
    bubble._translationEl = translation;

    bubble.append(header, text, translation);
    wrap.append(bubble);
    return wrap;
  }

  _applyTranslation(refSeq, textId) {
    const row = this.rowsBySeq.get(refSeq);
    if (!row || !row._translationEl) return; // row already scrolled out of the 500-entry window
    row._translationEl.textContent = `🇮🇩 ${textId}`;
    row._translationEl.hidden = false;
  }

  clear() {
    this.entries = [];
    this.pending = [];
    this.rowsBySeq.clear();
    this.el.replaceChildren();
  }
}
