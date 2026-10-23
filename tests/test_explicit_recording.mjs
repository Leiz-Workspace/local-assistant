/** Test consent, pending-permission races, PCM bounds and device cleanup without accessing a real microphone. */
import assert from "node:assert/strict";
import {test} from "node:test";
import vm from "node:vm";
import {readFileSync} from "node:fs";
import {ExplicitRecorder, MAX_SAMPLES, PREVIEW_MILLISECONDS, waveBlob} from "../apps/voice/static/recorder.mjs";

/** Construct finite observable browser doubles with no network, real audio or filesystem writes. */
function fixture() {
  const events = [];
  const timers = new Map();
  const track = {stopped: 0, onended: null, stop() { this.stopped += 1; }};
  const stream = {getTracks() { return [track]; }};
  const port = {onmessage: null};
  const node = {port, connect() {}, disconnect() { events.push("node_disconnected"); }};
  const source = {connect() {}, disconnect() { events.push("source_disconnected"); }};
  const context = {sampleRate: 16000, destination: {}, audioWorklet: {async addModule() {}}, createMediaStreamSource() { return source; }, async resume() {}, async close() { events.push("context_closed"); }};
  const env = {
    async getUserMedia() { events.push("permission_requested"); return stream; },
    createContext() { return context; }, createNode() { return node; },
    setTimer(callback, delay) { timers.set(delay, callback); return delay; },
    clearTimer(timer) { timers.delete(timer); },
    createURL() { events.push("preview_created"); return "blob:test"; },
    revokeURL() { events.push("preview_revoked"); }, audit(event) { events.push(event); },
  };
  const recorder = new ExplicitRecorder(env, state => events.push(`state:${state}`));
  return {recorder, env, track, stream, context, node, timers, events};
}

test("construction does not acquire a microphone; explicit stop releases capture and creates valid WAV", async () => {
  const f = fixture();
  assert.equal(f.recorder.state, "idle");
  assert.deepEqual(f.events, []);
  await f.recorder.start();
  assert.equal(f.recorder.state, "recording");
  f.node.port.onmessage({data: new Float32Array([0, -1, 1, 0.5])});
  f.recorder.stop();
  assert.equal(f.track.stopped, 1);
  assert.equal(f.recorder.state, "ready");
  assert.deepEqual([...f.timers.keys()], [PREVIEW_MILLISECONDS]);
  const raw = new DataView(await f.recorder.blob.arrayBuffer());
  assert.equal(raw.byteLength, 52);
  assert.equal(raw.getUint32(24, true), 16000);
  assert.equal(raw.getInt16(46, true), -32768);
  assert.equal(raw.getInt16(48, true), 32767);
  assert.equal(f.node.port.onmessage, null);
});

test("completed preview expires without recording or retaining a Blob, URL or active timer", async () => {
  const f = fixture();
  await f.recorder.start();
  f.recorder.accept(f.recorder.generation, new Float32Array([0.5]));
  f.recorder.stop();
  assert.equal(PREVIEW_MILLISECONDS, 300000);
  f.timers.get(PREVIEW_MILLISECONDS)();
  assert.equal(f.recorder.state, "cancelled");
  assert.equal(f.recorder.blob, null);
  assert.equal(f.recorder.url, null);
  assert.equal(f.timers.size, 0);
  assert.equal(f.track.stopped, 1);
  assert.equal(f.events.filter(item => item === "permission_requested").length, 1);
  assert.ok(f.events.includes("retention_expired"));
  assert.ok(f.events.includes("preview_revoked"));
});

test("replacing or explicitly deleting a preview cancels its expiry before a new device is requested", async () => {
  const f = fixture();
  await f.recorder.start();
  f.recorder.accept(f.recorder.generation, new Float32Array([0.5]));
  f.recorder.stop();
  assert.equal(f.timers.has(PREVIEW_MILLISECONDS), true);
  const staleExpiry = f.timers.get(PREVIEW_MILLISECONDS);
  await f.recorder.start();
  staleExpiry();
  assert.equal(f.recorder.state, "recording");
  assert.equal(f.timers.has(PREVIEW_MILLISECONDS), false);
  assert.equal(f.recorder.blob, null);
  f.recorder.cancel();
  assert.equal(f.timers.size, 0);
});

test("cancel and duplicate start never keep PCM or acquire a second active device", async () => {
  const f = fixture();
  await f.recorder.start();
  await f.recorder.start();
  f.recorder.accept(f.recorder.generation, new Float32Array([0.1]));
  f.recorder.cancel();
  assert.equal(f.recorder.state, "cancelled");
  assert.equal(f.events.filter(item => item === "permission_requested").length, 1);
  assert.equal(f.track.stopped, 1);
  assert.equal(f.recorder.blob, null);
  assert.equal(f.recorder.session, null);
  assert.equal(f.timers.size, 0);
});

test("cancelling pending permission disposes of a late stream and cannot reactivate recording", async () => {
  const f = fixture();
  let resolve;
  f.env.getUserMedia = () => new Promise(done => { resolve = done; });
  const starting = f.recorder.start();
  assert.equal(f.recorder.state, "requesting");
  f.recorder.cancel();
  resolve(f.stream);
  await starting;
  assert.equal(f.track.stopped, 1);
  assert.equal(f.recorder.state, "cancelled");
  assert.equal(f.events.includes("state:recording"), false);
});

test("permission deadline cancels an unanswered prompt and its eventual device", async () => {
  const f = fixture();
  let resolve;
  f.env.getUserMedia = () => new Promise(done => { resolve = done; });
  const starting = f.recorder.start();
  f.timers.get(10000)();
  resolve(f.stream);
  await starting;
  assert.equal(f.track.stopped, 1);
  assert.equal(f.recorder.state, "cancelled");
  assert.ok(f.events.includes("permission_timeout"));
});

test("permission rejection and unsupported audio rate release all acquired resources", async () => {
  for (const mode of ["denied", "rate"]) {
    const f = fixture();
    if (mode === "denied") f.env.getUserMedia = async () => { throw new Error("private device secret"); };
    else f.context.sampleRate = 48000;
    await f.recorder.start();
    assert.equal(f.recorder.state, "error");
    assert.equal(f.recorder.session, null);
    assert.equal(f.timers.size, 0);
    assert.equal(f.track.stopped, mode === "rate" ? 1 : 0);
    assert.equal(f.events.some(item => item.includes("private")), false);
  }
});

test("late worklet initialization after cancellation cannot create a capture graph", async () => {
  const f = fixture();
  let resolve;
  f.context.audioWorklet.addModule = () => new Promise(done => { resolve = done; });
  const starting = f.recorder.start();
  await Promise.resolve();
  f.recorder.cancel();
  resolve();
  await starting;
  assert.equal(f.recorder.state, "cancelled");
  assert.ok(f.track.stopped >= 1);
  assert.equal(f.events.includes("state:recording"), false);
});

test("device loss, invalid frames and deadline stop capture without automatic retry", async () => {
  for (const mode of ["lost", "nan", "oversized", "deadline", "processor"]) {
    const f = fixture();
    await f.recorder.start();
    if (mode === "lost") f.track.onended();
    if (mode === "nan") f.recorder.accept(f.recorder.generation, new Float32Array([NaN]));
    if (mode === "oversized") f.recorder.accept(f.recorder.generation, new Float32Array(2049));
    if (mode === "deadline") f.timers.get(30000)();
    if (mode === "processor") f.node.onprocessorerror();
    assert.equal(f.track.stopped, 1);
    assert.equal(f.events.filter(item => item === "permission_requested").length, 1);
    assert.equal(f.recorder.blob, null);
  }
});

test("preview creation failure still releases the microphone before encoding or URL operations", async () => {
  const f = fixture();
  await f.recorder.start();
  f.recorder.accept(f.recorder.generation, new Float32Array([1]));
  f.env.createURL = () => { assert.equal(f.track.stopped, 1); throw new Error("private failure"); };
  f.recorder.stop();
  assert.equal(f.recorder.state, "error");
  assert.equal(f.recorder.blob, null);
  assert.equal(f.recorder.session, null);
});

test("stale frames cannot modify an old or a replacement recording; cancel revokes preview", async () => {
  const f = fixture();
  await f.recorder.start();
  const old = f.recorder.generation;
  f.recorder.accept(old, new Float32Array([1]));
  f.recorder.stop();
  f.recorder.accept(old, new Float32Array([1]));
  assert.equal(f.recorder.blob.size, 46);
  f.recorder.cancel();
  assert.ok(f.events.includes("preview_revoked"));
  await f.recorder.start();
  f.recorder.accept(old, new Float32Array([1]));
  assert.equal(f.recorder.session.count, 0);
  f.recorder.cancel();
});

test("sample limit finishes one bounded complete WAV; malformed counts fail", async () => {
  const f = fixture();
  await f.recorder.start();
  for (let i = 0; i < MAX_SAMPLES; i += 128) f.recorder.accept(f.recorder.generation, new Float32Array(128));
  f.recorder.accept(f.recorder.generation, "limit");
  assert.equal(f.recorder.state, "ready");
  assert.equal(f.recorder.blob.size, 44 + MAX_SAMPLES * 2);
  assert.throws(() => waveBlob([new Float32Array([NaN])], 1));
  assert.throws(() => waveBlob([new Float32Array(2)], 1));
  assert.throws(() => waveBlob([], 1));
  assert.throws(() => waveBlob([], MAX_SAMPLES + 1));
  assert.throws(() => waveBlob([], true));
});

test("native worklet downmixes, never feeds microphone to speakers, and emits an exact final sample bound", () => {
  let Processor;
  const messages = [];
  class Base {
    /** Expose only a test message port to the isolated worklet source. */
    constructor() { this.port = {postMessage: value => messages.push(value)}; }
  }
  vm.runInNewContext(readFileSync(new URL("../apps/voice/static/capture-worklet.js", import.meta.url), "utf8"), {
    AudioWorkletProcessor: Base, sampleRate: 16000,
    registerProcessor(name, value) { assert.equal(name, "explicit-capture"); Processor = value; },
  });
  const processor = new Processor();
  assert.equal(processor.process([]), true);
  assert.equal(processor.process([[new Float32Array([1, -1]), new Float32Array([-1, 1])]]), true);
  assert.deepEqual(Array.from(messages[0]), [0, 0]);
  processor.count = MAX_SAMPLES - 1;
  assert.equal(processor.process([[new Float32Array([0.5, 0.5])]]), false);
  assert.equal(messages.at(-2).length, 1);
  assert.equal(messages.at(-1), "limit");
});
