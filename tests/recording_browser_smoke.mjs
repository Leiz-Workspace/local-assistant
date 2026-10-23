/** Exercise the real browser AudioWorklet using its fake microphone and retain finite local-only lifecycle observations. */
import assert from "node:assert/strict";
import {createRequire} from "node:module";

const require = createRequire(import.meta.url);
const {chromium} = require(process.env.PLAYWRIGHT_CORE_PATH);
const origin = process.env.RECORDING_TEST_ORIGIN;
assert.match(origin, /^http:\/\/127\.0\.0\.1:\d+$/);
const browser = await chromium.launch({
  executablePath: process.env.RECORDING_TEST_BROWSER,
  headless: true,
  args: ["--use-fake-device-for-media-stream", "--use-fake-ui-for-media-stream", "--no-sandbox"],
});
const errors = [];
const requests = [];
const logs = [];
try {
  const context = await browser.newContext();
  const page = await context.newPage();
  page.on("pageerror", error => errors.push(error.message));
  page.on("request", request => requests.push({url: request.url(), method: request.method()}));
  page.on("console", message => logs.push(message.text()));
  await page.addInitScript(() => {
    const original = navigator.mediaDevices.getUserMedia.bind(navigator.mediaDevices);
    const originalURL = URL.createObjectURL.bind(URL);
    window.testStreams = [];
    window.testBlobs = [];
    URL.createObjectURL = blob => { window.testBlobs.push(blob); return originalURL(blob); };
    navigator.mediaDevices.getUserMedia = async constraints => {
      const stream = await original(constraints);
      window.testStreams.push(stream);
      if (window.testHoldPermission) await new Promise(resolve => { window.testReleasePermission = resolve; });
      return stream;
    };
  });
  await page.goto(origin);
  assert.equal(await page.evaluate(() => window.testStreams.length), 0);
  await page.getByRole("button", {name: "Bắt đầu ghi"}).click();
  await page.waitForFunction(() => document.getElementById("status").textContent.startsWith("Đang ghi âm"));
  await page.waitForTimeout(700);
  await page.getByRole("button", {name: "Dừng và nghe lại"}).click();
  await page.waitForFunction(() => !document.getElementById("preview").hidden);
  const stopped = await page.evaluate(async () => {
    const blob = await window.testBlobs.at(-1).arrayBuffer();
    const data = new DataView(blob);
    return {rate: data.getUint32(24, true), bytes: data.byteLength, tracks: window.testStreams.flatMap(stream => stream.getTracks().map(track => track.readyState))};
  });
  assert.equal(stopped.rate, 16000);
  assert.ok(stopped.bytes > 44 && stopped.bytes <= 960044);
  assert.deepEqual(stopped.tracks, ["ended"]);
  await page.getByRole("button", {name: "Hủy / xóa audio"}).click();
  assert.equal(await page.locator("#preview").getAttribute("src"), null);
  await page.getByRole("button", {name: "Bắt đầu ghi"}).click();
  await page.waitForFunction(() => document.getElementById("status").textContent.startsWith("Đang ghi âm"));
  await page.keyboard.press("Escape");
  assert.deepEqual(await page.evaluate(() => window.testStreams.flatMap(stream => stream.getTracks().map(track => track.readyState))), ["ended", "ended"]);
  assert.equal(await page.locator("#preview").getAttribute("src"), null);
  await page.getByRole("button", {name: "Bắt đầu ghi"}).click();
  await page.waitForFunction(() => document.getElementById("status").textContent.startsWith("Đang ghi âm"));
  await page.evaluate(() => { Object.defineProperty(document, "hidden", {value: true, configurable: true}); document.dispatchEvent(new Event("visibilitychange")); });
  assert.deepEqual(await page.evaluate(() => window.testStreams.flatMap(stream => stream.getTracks().map(track => track.readyState))), ["ended", "ended", "ended"]);
  assert.equal(await page.locator("#preview").getAttribute("src"), null);
  await page.evaluate(() => { Object.defineProperty(document, "hidden", {value: false, configurable: true}); window.testHoldPermission = true; });
  await page.getByRole("button", {name: "Bắt đầu ghi"}).click();
  await page.waitForFunction(() => typeof window.testReleasePermission === "function");
  await page.getByRole("button", {name: "Hủy / xóa audio"}).click();
  await page.evaluate(() => window.testReleasePermission());
  await page.waitForFunction(() => window.testStreams.every(stream => stream.getTracks().every(track => track.readyState === "ended")));
  assert.equal(await page.locator("#status").textContent(), "Đã hủy và xóa audio");
  assert.equal(await page.evaluate(() => window.testStreams.length), 4);
  assert.equal(requests.some(request => request.method !== "GET" || (!request.url.startsWith(origin + "/") && !request.url.startsWith("blob:"))), false);
  assert.deepEqual(errors, []);
  console.info(JSON.stringify({description: "Actual native browser capture with fake device only; not a physical-microphone or subjective audio-quality test.", browser: browser.version(), stopped, captures: 4, late_permission_cancel_verified: true, all_tracks_ended: true, page_errors: errors, requests, finite_lifecycle_events: logs.filter(line => line.startsWith("explicit_recording_event")), passed: true}));
} finally {
  await browser.close();
}
