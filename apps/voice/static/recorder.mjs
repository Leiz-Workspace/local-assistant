/** Own explicit consent, bounded PCM capture and immediate microphone release without uploading audio. */
export const RATE = 16000;
export const MAX_SAMPLES = 30 * RATE;

/** Encode admitted mono samples as a standard PCM16 WAV without mutating source buffers. */
export function waveBlob(chunks, count) {
  if (!Number.isInteger(count) || count < 1 || count > MAX_SAMPLES) throw new Error("invalid_pcm");
  const bytes = new ArrayBuffer(44 + count * 2);
  const view = new DataView(bytes);
  const text = new TextEncoder();
  new Uint8Array(bytes, 0, 4).set(text.encode("RIFF"));
  view.setUint32(4, 36 + count * 2, true);
  new Uint8Array(bytes, 8, 8).set(text.encode("WAVEfmt "));
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, 1, true);
  view.setUint32(24, RATE, true);
  view.setUint32(28, RATE * 2, true);
  view.setUint16(32, 2, true);
  view.setUint16(34, 16, true);
  new Uint8Array(bytes, 36, 4).set(text.encode("data"));
  view.setUint32(40, count * 2, true);
  let index = 0;
  for (const chunk of chunks) {
    for (const sample of chunk) {
      if (!Number.isFinite(sample) || index >= count) throw new Error("invalid_pcm");
      const value = Math.max(-1, Math.min(1, sample));
      view.setInt16(44 + index * 2, Math.round(value * (value < 0 ? 32768 : 32767)), true);
      index += 1;
    }
  }
  if (index !== count) throw new Error("invalid_pcm");
  return new Blob([bytes], {type: "audio/wav"});
}

/** Coordinate one user-requested microphone acquisition with stale-request disposal and bounded cleanup. */
export class ExplicitRecorder {
  /** Inject native browser capabilities or test doubles without acquiring any device. */
  constructor(env, onState) {
    this.env = env;
    this.onState = onState;
    this.state = "idle";
    this.generation = 0;
    this.session = null;
    this.url = null;
    this.blob = null;
  }

  /** Publish finite lifecycle audit events without audio, device identifiers or exception content. */
  publish(state) {
    this.state = state;
    this.env.audit(state);
    this.onState(state);
  }

  /** Revoke the previous preview and release all application references to captured audio. */
  discard() {
    if (this.url) this.env.revokeURL(this.url);
    this.url = null;
    this.blob = null;
  }

  /** Stop every acquired track synchronously, then retire graph nodes and close the context asynchronously. */
  release(session) {
    this.env.clearTimer(session.timer);
    for (const track of session.stream?.getTracks() ?? []) {
      track.onended = null;
      track.stop();
    }
    if (session.node) session.node.port.onmessage = null;
    if (session.node) session.node.onprocessorerror = null;
    session.node?.disconnect();
    session.source?.disconnect();
    const closing = session.context?.close();
    closing?.catch(() => this.env.audit("context_close_failed"));
    session.chunks = [];
    this.env.audit("capture_resources_released");
  }

  /** Request a fresh device only after an explicit UI action and dispose of cancelled late acquisitions. */
  async start() {
    if (!["idle", "ready", "cancelled", "error"].includes(this.state)) return;
    this.discard();
    const id = ++this.generation;
    const session = {chunks: [], count: 0, stream: null, context: null, source: null, node: null};
    this.session = session;
    this.publish("requesting");
    session.timer = this.env.setTimer(() => this.cancel("permission_timeout"), 10000);
    try {
      session.stream = await this.env.getUserMedia({audio: {channelCount: 1, echoCancellation: false, noiseSuppression: false, autoGainControl: false}, video: false});
      if (id !== this.generation) { this.release(session); return; }
      session.context = this.env.createContext({sampleRate: RATE});
      if (session.context.sampleRate !== RATE) throw new Error("unsupported_rate");
      await session.context.audioWorklet.addModule("/capture-worklet.js");
      if (id !== this.generation) { this.release(session); return; }
      session.source = session.context.createMediaStreamSource(session.stream);
      session.node = this.env.createNode(session.context);
      session.node.port.onmessage = event => this.accept(id, event.data);
      session.node.onprocessorerror = () => this.cancel("processor_failed");
      for (const track of session.stream.getTracks()) track.onended = () => this.cancel("device_lost");
      session.source.connect(session.node);
      session.node.connect(session.context.destination);
      await session.context.resume();
      if (id !== this.generation) { this.release(session); return; }
      this.env.clearTimer(session.timer);
      session.timer = this.env.setTimer(() => this.stop(), 30000);
      this.publish("recording");
    } catch {
      if (id !== this.generation) return;
      ++this.generation;
      this.release(session);
      this.session = null;
      this.publish("error");
    }
  }

  /** Admit bounded native frames only for the current explicitly active capture. */
  accept(id, data) {
    if (id !== this.generation || this.state !== "recording") return;
    if (data === "limit") { this.stop(); return; }
    const session = this.session;
    if (!(data instanceof Float32Array) || !data.length || data.length > 2048 || data.some(value => !Number.isFinite(value)) || session.count + data.length > MAX_SAMPLES) {
      this.cancel("invalid_frame");
      return;
    }
    session.chunks.push(data.slice());
    session.count += data.length;
  }

  /** Stop capture immediately and expose only the PCM already admitted before the stop action. */
  stop() {
    if (this.state === "requesting") { this.cancel(); return; }
    if (this.state !== "recording") return;
    ++this.generation;
    const session = this.session;
    const chunks = session.chunks;
    const count = session.count;
    this.release(session);
    this.session = null;
    try {
      this.blob = count ? waveBlob(chunks, count) : null;
      this.url = this.blob ? this.env.createURL(this.blob) : null;
    } catch {
      this.discard();
      this.publish("error");
      return;
    } finally {
      chunks.length = 0;
    }
    this.publish(this.blob ? "ready" : "idle");
  }

  /** Cancel pending acquisition or recording without keeping audio or automatically restarting. */
  cancel(reason = "user_cancelled") {
    ++this.generation;
    if (this.session) this.release(this.session);
    this.session = null;
    this.discard();
    this.env.audit(reason);
    this.publish("cancelled");
  }
}
