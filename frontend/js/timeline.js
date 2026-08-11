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
    const row = document.createElement('div');
    row.className = `utt utt--${e.ch}${e.low_conf ? ' utt--low' : ''}`;
    if (e.seq != null) {
      row.dataset.seq = e.seq;
      this.rowsBySeq.set(e.seq, row);
    }

    const who = document.createElement('span');
    who.className = 'utt__who';
    who.textContent = e.ch === 'candidate' ? 'Kandidat' : 'Interviewer';

    const textCol = document.createElement('span');
    textCol.className = 'utt__text';
    const text = document.createElement('span');
    text.textContent = e.text;
    const translation = document.createElement('span');
    translation.className = 'utt__translation';
    translation.hidden = true;
    textCol.append(text, translation);
    row._translationEl = translation;

    const meta = document.createElement('span');
    meta.className = 'utt__meta';
    meta.textContent = `${e.lang || '?'}${e.low_conf ? ' · low-conf' : ''}`;

    row.append(who, textCol, meta);
    return row;
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
