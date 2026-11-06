/** Exercise actual trial UI/capture/playback lifecycle with a synthetic microphone, muted output and mocked model APIs. */
import assert from "node:assert/strict";
import {createRequire} from "node:module";
import {mkdir, writeFile} from "node:fs/promises";

const require = createRequire(import.meta.url);
const {chromium} = require(process.env.PLAYWRIGHT_CORE_PATH);
const origin = process.env.VOICE_TRIAL_ORIGIN;
const root = process.env.VOICE_TRIAL_BROWSER_ROOT;
assert.match(origin, /^http:\/\/127\.0\.0\.1:\d+$/);
await mkdir(root, {recursive: true});
const wav = Buffer.alloc(32044);
wav.write("RIFF"); wav.writeUInt32LE(32036, 4); wav.write("WAVEfmt ", 8); wav.writeUInt32LE(16, 16);
wav.writeUInt16LE(1, 20); wav.writeUInt16LE(1, 22); wav.writeUInt32LE(16000, 24); wav.writeUInt32LE(32000, 28);
wav.writeUInt16LE(2, 32); wav.writeUInt16LE(16, 34); wav.write("data", 36); wav.writeUInt32LE(32000, 40);
for (let i = 0; i < 16000; i++) wav.writeInt16LE(Math.round(1000 * Math.sin(i * Math.PI / 20)), 44 + 2 * i);
const browser = await chromium.launch({executablePath: process.env.RECORDING_TEST_BROWSER, headless: true,
  args: ["--use-fake-device-for-media-stream", "--use-fake-ui-for-media-stream", "--mute-audio", "--no-sandbox"]});
const errors = [];
const observed = [];
let state = "idle";
let sends = 0;
let releaseLate;
try {
  const context = await browser.newContext({viewport: {width: 1100, height: 1050}});
  const page = await context.newPage();
  page.on("pageerror", error => errors.push(error.message));
  page.on("request", request => observed.push({method: request.method(), path: request.url().replace(origin, "").split("?")[0]}));
  await page.addInitScript(() => {
    const acquire = navigator.mediaDevices.getUserMedia.bind(navigator.mediaDevices);
    const source = AudioContext.prototype.createBufferSource;
    const timer = window.setTimeout.bind(window);
    const createURL = URL.createObjectURL.bind(URL);
    window.trialStreams = []; window.trialPlayed = 0;
    window.trialBlobs = [];
    URL.createObjectURL = blob => { window.trialBlobs.push(blob); return createURL(blob); };
    window.setTimeout = (callback, delay, ...args) => {
      if (delay === 300000) window.trialExpiry = callback;
      return timer(callback, delay, ...args);
    };
    AudioContext.prototype.createBufferSource = function (...args) {
      const node = source.apply(this, args); const start = node.start.bind(node);
      node.start = (...values) => { window.trialPlayed++; return start(...values); }; return node;
    };
    navigator.mediaDevices.getUserMedia = async options => {
      if (window.trialDeny) throw new DOMException("denied", "NotAllowedError");
      const stream = await acquire(options); window.trialStreams.push(stream); return stream;
    };
  });
  await page.route(origin + "/api/**", async route => {
    const path = new URL(route.request().url()).pathname;
    if (path === "/api/prepare") state = "ready";
    if (path === "/api/turn") {
      sends++;
      const headers = await route.request().allHeaders();
      assert.equal(headers["content-type"], "audio/wav"); assert.equal(headers["x-voice-submit"], "1");
      const body = route.request().postDataBuffer(); assert.ok(body.length >= 32044 && body.length <= 640044);
      if (sends === 2) await new Promise(resolve => { releaseLate = resolve; });
      await route.fulfill({status: 200, contentType: "application/json", body: JSON.stringify({id: headers["x-voice-id"], transcript: "Câu hỏi mẫu công khai.", answer: "Đây là câu trả lời thử nghiệm.", audio_base64: wav.toString("base64"), buffered_seconds: 0.1, stages: {}})}).catch(() => {});
      return;
    }
    await route.fulfill({status: path === "/api/prepare" ? 202 : 200, contentType: "application/json", body: JSON.stringify({state, remaining: 24 - sends, preparations_remaining: 3, code: "cancelled"})});
  });
  await page.goto(origin);
  await page.waitForFunction(() => !document.getElementById("prepare").disabled);
  assert.equal(await page.evaluate(() => window.trialStreams.length), 0);
  assert.equal(observed.some(x => x.method === "POST"), false);
  await page.getByRole("button", {name: "Chuẩn bị", exact: true}).click();
  await page.waitForFunction(() => !document.getElementById("start").disabled);
  await page.getByRole("button", {name: "Ghi câu hỏi", exact: true}).click();
  await page.waitForFunction(() => document.getElementById("capture-status").textContent.includes("Đang thu"));
  await page.waitForTimeout(1250);
  await page.getByRole("button", {name: "Dừng và nghe lại"}).click();
  await page.waitForFunction(() => !document.getElementById("send").disabled);
  assert.deepEqual(await page.evaluate(() => window.trialStreams.flatMap(s => s.getTracks().map(t => t.readyState))), ["ended"]);
  assert.equal(sends, 0);
  await page.getByRole("button", {name: "Gửi câu hỏi", exact: true}).click();
  await page.waitForFunction(() => !document.getElementById("result").hidden);
  assert.equal(await page.locator("#answer").textContent(), "Đây là câu trả lời thử nghiệm.");
  assert.equal(await page.evaluate(() => window.trialPlayed), 1);
  assert.match(await page.locator("#timing").textContent(), /Chưa đo tiếng từ loa/);
  await page.screenshot({path: root + "/desktop.png", fullPage: true});
  await page.setViewportSize({width: 320, height: 900}); await page.emulateMedia({colorScheme: "dark"});
  assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
  await page.screenshot({path: root + "/mobile-dark.png", fullPage: true});
  await page.evaluate(() => window.trialExpiry());
  assert.equal(await page.locator("#reply").getAttribute("src"), null);
  assert.equal(await page.locator("#answer").textContent(), "");
  await page.setViewportSize({width: 1100, height: 1050});
  await page.getByRole("button", {name: "Ghi câu hỏi", exact: true}).click();
  await page.waitForFunction(() => document.getElementById("capture-status").textContent.includes("Đang thu"));
  await page.waitForTimeout(1250); await page.getByRole("button", {name: "Dừng và nghe lại"}).click();
  await page.waitForFunction(() => !document.getElementById("send").disabled);
  await page.getByRole("button", {name: "Gửi câu hỏi", exact: true}).click();
  while (!releaseLate) await page.waitForTimeout(20);
  await page.getByRole("button", {name: "Hủy / xóa", exact: true}).click();
  releaseLate(); await page.waitForTimeout(300);
  assert.equal(await page.evaluate(() => window.trialPlayed), 1);
  assert.equal(await page.locator("#result").isVisible(), false);
  await page.evaluate(() => { window.trialDeny = true; });
  await page.getByRole("button", {name: "Ghi câu hỏi", exact: true}).click();
  await page.waitForFunction(() => document.getElementById("capture-status").textContent.includes("Không thể ghi"));
  assert.equal(await page.evaluate(() => window.trialStreams.length), 2);
  await page.evaluate(() => { window.trialDeny = false; });
  await page.getByRole("button", {name: "Ghi câu hỏi", exact: true}).click();
  await page.waitForFunction(() => document.getElementById("capture-status").textContent.includes("Đang thu"));
  await page.waitForFunction(() => !document.getElementById("send").disabled, null, {timeout: 26000});
  const previewSamples = await page.evaluate(async () => {
    const bytes = await window.trialBlobs.at(-1).arrayBuffer(); return new DataView(bytes).getUint32(40, true) / 2;
  });
  assert.equal(previewSamples, 320000);
  await page.keyboard.press("Escape");
  assert.equal(await page.locator("#preview").getAttribute("src"), null);
  assert.equal(await page.evaluate(() => window.trialStreams.every(s => s.getTracks().every(t => t.readyState === "ended"))), true);
  const storage = await page.evaluate(async () => ({local: localStorage.length, session: sessionStorage.length, databases: (await indexedDB.databases()).length}));
  assert.deepEqual(storage, {local: 0, session: 0, databases: 0});
  assert.deepEqual(errors, []);
  assert.equal(observed.some(x => !x.path.startsWith("/") && !x.path.startsWith("blob:")), false);
  await writeFile(root + "/receipt.json", JSON.stringify({description: "Actual headless Chromium/Brave UI lifecycle with synthetic microphone, muted output and mocked model API; not physical or native performance acceptance.", status: "PASS", real_microphone: false, hardware_audio_output: false, model_requests: 0, fake_submissions: sends, maximum_capture_samples: previewSamples, page_errors: errors, storage, browser: browser.version()}, null, 2) + "\n");
  console.log("voice_trial_browser_controls_PASS fake_microphone/muted/mocked_models");
} finally { await browser.close(); }
