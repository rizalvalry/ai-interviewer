const MAX_ENTRIES = 500;

export class Timeline {
  constructor(el) {
    this.el = el;
    this.entries = [];
    this.pending = [];
    this.scheduled = false;
  }

  add(entry) {
    this.entries.push(entry);
    if (this.entries.length > MAX_ENTRIES) this.entries.shift();
    this.pending.push(entry);
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
    for (const e of this.pending) frag.appendChild(this.render(e));
    this.pending = [];

    this.el.appendChild(frag);
    while (this.el.childElementCount > MAX_ENTRIES) this.el.removeChild(this.el.firstElementChild);
    this.el.scrollTop = this.el.scrollHeight;
  }

  render(e) {
    const row = document.createElement('div');
    row.className = `utt utt--${e.ch}${e.low_conf ? ' utt--low' : ''}`;

    const who = document.createElement('span');
    who.className = 'utt__who';
    who.textContent = e.ch === 'candidate' ? 'Kandidat' : 'Interviewer';

    const text = document.createElement('span');
    text.className = 'utt__text';
    text.textContent = e.text;

    const meta = document.createElement('span');
    meta.className = 'utt__meta';
    meta.textContent = `${e.lang || '?'}${e.low_conf ? ' · low-conf' : ''}`;

    row.append(who, text, meta);
    return row;
  }

  clear() {
    this.entries = [];
    this.pending = [];
    this.el.replaceChildren();
  }
}
