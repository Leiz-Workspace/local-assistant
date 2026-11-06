/** Capture bounded native mono PCM frames without persistence, network or microphone authority. */
class CaptureProcessor extends AudioWorkletProcessor {
  /** Initialize a per-recording sample budget at the browser context rate. */
  constructor() {
    super();
    this.count = 0;
    this.limit = 30 * sampleRate;
  }

  /** Transfer complete admitted input frames and stop at the declared sample budget. */
  process(inputs) {
    const channels = inputs[0];
    if (!channels?.length || !channels[0].length) return true;
    const length = Math.min(channels[0].length, this.limit - this.count);
    const pcm = new Float32Array(length);
    for (let i = 0; i < length; i += 1) {
      for (const channel of channels) pcm[i] += channel[i] / channels.length;
    }
    this.count += length;
    this.port.postMessage(pcm, [pcm.buffer]);
    if (this.count >= this.limit) {
      this.port.postMessage("limit");
      return false;
    }
    return true;
  }
}
registerProcessor("explicit-capture", CaptureProcessor);
