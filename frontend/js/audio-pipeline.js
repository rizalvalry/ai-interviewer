export const CHANNEL_ID = { candidate: 0, interviewer: 1 };

export function f32ToI16(f32) {
  const out = new Int16Array(f32.length);
  for (let i = 0; i < f32.length; i++) {
    const s = Math.max(-1, Math.min(1, f32[i]));
    out[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
  }
  return out;
}

export function framePacket(seq, channel, i16) {
  const buf = new ArrayBuffer(8 + i16.byteLength);
  const dv = new DataView(buf);
  dv.setUint32(0, seq);                     // big-endian, matches int.from_bytes(..., "big")
  dv.setUint8(4, CHANNEL_ID[channel]);
  new Int16Array(buf, 8).set(i16);
  return buf;
}

export async function pipe(stream, channel, wsMgr, ctx, onLevel) {
  const src = ctx.createMediaStreamSource(stream);
  const node = new AudioWorkletNode(ctx, 'pcm-processor');
  let seq = 0;

  node.port.onmessage = (e) => {
    const { pcm, rms } = e.data;
    onLevel?.(channel, rms);
    wsMgr.send(framePacket(seq++, channel, f32ToI16(new Float32Array(pcm))));
  };

  src.connect(node);   // deliberately not connected to ctx.destination: that is a feedback loop
  return { node, src };
}
