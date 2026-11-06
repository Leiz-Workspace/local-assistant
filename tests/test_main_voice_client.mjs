/** Test explicit submission, cancellation races and bounded browser capture using authored audio and no real devices. */
import assert from "node:assert/strict";
import {readFile} from "node:fs/promises";
import {test} from "node:test";

const file = new URL("../apps/web/voice/session.mjs", import.meta.url);
const original = new URL("../apps/web/voice/recorder.mjs", import.meta.url);
const text = (await readFile(file, "utf8")).replace('from "./recorder.mjs"', `from ${JSON.stringify(original.href)}`);
const {TrialSession, TrialRecorder} = await import("data:text/javascript;base64," + Buffer.from(text).toString("base64"));
const blob = new Blob([new Uint8Array(32044)], {type: "audio/wav"});

/** Inject observable browser capabilities without local storage, native playback or microphone access. */
function fixture() {
  const calls = [];
  const env = {uuid: () => "00000000-0000-4000-8000-000000000001", now: () => 100,
    fetch: async (path, options) => { calls.push([path, options]); return {ok: true, json: async () => ({id: env.uuid(), answer: "answer", transcript: "speech", audio_base64: "AAAA"})}; },
    unlockAudio: async () => calls.push("unlock"), playAudio: async () => calls.push("play"),
    stopAudio: () => calls.push("stop"), clearResult: () => calls.push("clear"),
    result: (value, timing) => calls.push(["result", value, timing]), audit: event => calls.push(["audit", event])};
  return {calls, env, session: new TrialSession(env)};
}

test("page construction does not record, fetch, infer or play", () => {
  const {calls} = fixture(); assert.deepEqual(calls, []);
});

test("one explicit Send unlocks output before uploading and plays only matching complete output", async () => {
  const {session, calls} = fixture(); await session.submit(blob);
  const request = calls.find(x => Array.isArray(x) && x[0] === "/api/turn");
  assert.equal(request[1].body, blob); assert.equal(request[1].headers["X-Voice-Submit"], "1");
  assert.ok(calls.indexOf("unlock") < calls.indexOf(request)); assert.ok(calls.includes("play"));
  assert.equal(calls.filter(x => Array.isArray(x) && x[0] === "result").length, 1);
});

test("cancelled late network result cannot play or render and notifies exact operation", async () => {
  const {session, env, calls} = fixture(); let release;
  env.fetch = async (path, options) => {
    calls.push([path, options]);
    if (path === "/api/cancel") return {ok: true};
    await new Promise(resolve => { release = resolve; });
    return {ok: true, json: async () => ({id: env.uuid(), answer: "late", transcript: "speech", audio_base64: "AAAA"})};
  };
  const active = session.submit(blob); while (!release) await new Promise(resolve => setImmediate(resolve));
  session.cancel("page_hidden"); release(); await active;
  assert.ok(!calls.includes("play")); assert.ok(!calls.some(x => Array.isArray(x) && x[0] === "result"));
  const cancelled = calls.find(x => Array.isArray(x) && x[0] === "/api/cancel");
  assert.equal(JSON.parse(cancelled[1].body).id, env.uuid()); assert.equal(cancelled[1].keepalive, true);
});

test("cancellation during audio decode refuses stale publication", async () => {
  const {session, env, calls} = fixture(); let release;
  env.playAudio = async (value, current) => { await new Promise(resolve => { release = resolve; }); if (current()) calls.push("play"); };
  const actor = session.submit(blob); while (!release) await new Promise(resolve => setImmediate(resolve));
  session.cancel(); release(); await actor;
  assert.ok(!calls.includes("play")); assert.ok(!calls.some(x => Array.isArray(x) && x[0] === "result"));
});

test("output failure permits explicit replay and never invents a playback time", async () => {
  const {session, env, calls} = fixture(); env.playAudio = async () => { throw new Error("autoplay blocked"); };
  await session.submit(blob);
  assert.equal(calls.find(x => Array.isArray(x) && x[0] === "result")[2].playback, null);
});

test("short or non WAV input is refused before any browser capability", async () => {
  const {session, calls} = fixture(); await assert.rejects(session.submit(new Blob(["short"])));
  assert.deepEqual(calls, []);
});

test("twenty second capture stops exactly at the sample boundary and does not acquire a device", () => {
  const recorder = new TrialRecorder({}, () => {}); recorder.generation = 1; recorder.state = "recording";
  recorder.session = {count: 319900, chunks: []}; let stopped = false;
  recorder.stop = () => { stopped = true; };
  recorder.accept(1, new Float32Array(200));
  assert.equal(recorder.session.count, 320000); assert.equal(recorder.session.chunks[0].length, 100); assert.equal(stopped, true);
});
