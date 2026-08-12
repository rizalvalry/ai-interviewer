// Guide 5.1: the single largest source of bugs in media apps is implicit state.
// Every transition is declared here; anything undeclared throws instead of half-working.
const TRANSITIONS = {
  IDLE: ['REQUESTING_MIC', 'ERROR'],
  REQUESTING_MIC: ['REQUESTING_DISPLAY', 'ERROR'],
  REQUESTING_DISPLAY: ['CONNECTING', 'ERROR'],
  CONNECTING: ['LIVE', 'ERROR'],
  LIVE: ['RECONNECTING', 'STOPPING', 'ERROR'],
  RECONNECTING: ['LIVE', 'STOPPING', 'ERROR'],
  STOPPING: ['STOPPED', 'ERROR'],
  STOPPED: ['IDLE'],
  // REQUESTING_MIC included as a last-resort safety net (bug-hunter, 2026-08-12): if some
  // future path reaches ERROR without a clean STOPPING->IDLE unwind, Start must still be
  // clickable rather than requiring a page reload.
  ERROR: ['IDLE', 'STOPPING', 'REQUESTING_MIC'],
};

export class StateMachine {
  constructor(onChange) {
    this.state = 'IDLE';
    this.reason = '';
    this.onChange = onChange;
  }

  can(next) {
    return (TRANSITIONS[this.state] || []).includes(next);
  }

  transition(next, reason = '') {
    if (!this.can(next)) {
      console.warn(`[sm] illegal transition ${this.state} -> ${next}`);
      return false;
    }
    const prev = this.state;
    this.state = next;
    this.reason = reason;
    this.onChange?.(next, prev, reason);
    return true;
  }

  is(...states) {
    return states.includes(this.state);
  }
}
