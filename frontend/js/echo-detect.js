// Guide 5.4: if both channels carry speech at the same time for most of the opening
// window, the interviewer's voice is almost certainly bleeding into the candidate's mic.
const SPEECH_RMS = 0.02;

export class EchoDetector {
  constructor({ windowMs = 10000, ratio = 0.7, onDetect } = {}) {
    this.windowMs = windowMs;
    this.ratio = ratio;
    this.onDetect = onDetect;
    this.startedAt = null;
    this.active = { candidate: false, interviewer: false };
    this.samples = 0;
    this.both = 0;
    this.fired = false;
  }

  observe(channel, rms) {
    if (this.fired) return;
    if (this.startedAt === null) this.startedAt = performance.now();

    this.active[channel] = rms > SPEECH_RMS;
    this.samples++;
    if (this.active.candidate && this.active.interviewer) this.both++;

    if (performance.now() - this.startedAt < this.windowMs) return;

    this.fired = true;
    if (this.samples > 0 && this.both / this.samples > this.ratio) {
      this.onDetect?.(this.both / this.samples);
    }
  }
}
