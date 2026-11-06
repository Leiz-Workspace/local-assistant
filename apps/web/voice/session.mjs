/** Own explicit voice submission, bounded capture and stale playback disposal without persistent browser storage. */
import {ExplicitRecorder, RATE} from "./recorder.mjs";

/** Reuse the passed recorder with a visible twenty-second research admission limit. */
export class TrialRecorder extends ExplicitRecorder {
  /** Admit only the first bounded captured frames and stop at the declared sample limit. */
  accept(id, data) {
    if (id !== this.generation || this.state !== "recording") return;
    if (data instanceof Float32Array && data.length && data.length <= 2048 && !data.some(x => !Number.isFinite(x))) {
      const left = 20 * RATE - this.session.count;
      if (left <= 0) { this.stop(); return; }
      super.accept(id, data.length > left ? data.slice(0, left) : data);
      if (this.session?.count === 20 * RATE) this.stop();
    } else super.accept(id, data);
  }
}

/** Coordinate one explicit request and play only a complete current answer, never a delayed cancelled response. */
export class TrialSession {
  /** Inject browser capabilities so privacy and cancellation can be tested without a microphone or models. */
  constructor(env) {
    this.env = env;
    this.active = null;
    this.generation = 0;
  }

  /** Send finite local API commands with same-origin credentials and an explicit submission header. */
  async command(path, body) {
    return this.env.fetch(path, {method: "POST", credentials: "same-origin", keepalive: true,
      headers: {"X-Voice-Submit": "1", ...(body ? {"Content-Type": "application/json"} : {})},
      body: body ? JSON.stringify(body) : undefined});
  }

  /** Explicitly prepare the research runtime without acquiring a microphone or submitting recorded audio. */
  async prepare() {
    this.env.audit("prepare_requested");
    const response = await this.command("/api/prepare");
    if (!response.ok) throw new Error("prepare_failed");
    return response.json();
  }

  /** Timestamp the Send gesture and keep all server/playback measurements separate from physical audibility. */
  async submit(blob) {
    if (this.active || !(blob instanceof Blob) || blob.size < 32044 || blob.size > 640044 || blob.type !== "audio/wav") throw new Error("invalid_input");
    const operation = {id: this.env.uuid(), abort: new AbortController(), generation: ++this.generation};
    this.active = operation;
    const started = this.env.now();
    this.env.clearResult();
    this.env.audit("voice_send");
    try {
      try { await this.env.unlockAudio(); } catch { this.env.audit("output_unlock_pending"); }
      if (operation.generation !== this.generation) return;
      const response = await this.env.fetch("/api/turn", {method: "POST", credentials: "same-origin", signal: operation.abort.signal,
        headers: {"Content-Type": "audio/wav", "X-Voice-Submit": "1", "X-Voice-ID": operation.id}, body: blob});
      const value = await response.json();
      if (operation.generation !== this.generation) return;
      if (!response.ok) throw new Error(["no_speech", "invalid_input", "busy", "closed", "timeout"].includes(value.code) ? value.code : "dependency_failed");
      if (value.id !== operation.id || typeof value.answer !== "string" || value.answer.length > 8192 || typeof value.transcript !== "string" || value.transcript.length > 8192 || typeof value.audio_base64 !== "string" || value.audio_base64.length > 1300000) throw new Error("invalid_result");
      const received = (this.env.now() - started) / 1000;
      let playback = null;
      try {
        await this.env.playAudio(value.audio_base64, () => operation.generation === this.generation);
        if (operation.generation !== this.generation) return;
        playback = (this.env.now() - started) / 1000;
      } catch { this.env.audit("manual_replay_required"); }
      if (operation.generation !== this.generation) return;
      this.env.result(value, {received, playback});
      this.env.audit("voice_answer_complete");
    } finally {
      if (this.active === operation) this.active = null;
    }
  }

  /** Abort matching work, clear stale media and notify the server even if the original fetch has not arrived. */
  cancel(reason = "user_cancelled") {
    ++this.generation;
    const operation = this.active;
    this.active = null;
    operation?.abort.abort();
    this.env.stopAudio();
    this.env.clearResult();
    this.env.audit(reason);
    if (operation) void this.command("/api/cancel", {id: operation.id}).catch(() => this.env.audit("cancel_delivery_failed"));
  }
}
