class PCMProcessor extends AudioWorkletProcessor {
  constructor(options) {
    super();
    this.FRAME = (options?.processorOptions?.frameSamples) || 5120; // 320 ms @ 16k
    this.buf = new Float32Array(0);
  }

  process(inputs) {
    const ch = inputs[0]?.[0];
    if (!ch?.length) return true;

    const merged = new Float32Array(this.buf.length + ch.length);
    merged.set(this.buf);
    merged.set(ch, this.buf.length);
    this.buf = merged;

    while (this.buf.length >= this.FRAME) {
      const frame = this.buf.slice(0, this.FRAME);
      this.buf = this.buf.slice(this.FRAME);

      let sum = 0;
      for (let i = 0; i < frame.length; i++) sum += frame[i] * frame[i];
      const rms = Math.sqrt(sum / frame.length);

      // Transferable: the buffer moves rather than copies, so long sessions do not churn GC.
      this.port.postMessage({ pcm: frame.buffer, rms }, [frame.buffer]);
    }
    return true;
  }
}

registerProcessor('pcm-processor', PCMProcessor);
