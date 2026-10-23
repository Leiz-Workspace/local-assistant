/** Verify native keyboard capture, named landmarks/playback, responsive dark layout and local-only requests with a fake microphone. */
import assert from "node:assert/strict";
import {createRequire} from "node:module";

const require = createRequire(import.meta.url);
const {chromium} = require(process.env.PLAYWRIGHT_CORE_PATH);
const origin = process.env.RECORDING_TEST_ORIGIN;
assert.match(origin, /^http:\/\/127\.0\.0\.1:\d+$/);
const browser = await chromium.launch({executablePath:process.env.RECORDING_TEST_BROWSER, headless:true,
  args:["--use-fake-device-for-media-stream","--use-fake-ui-for-media-stream","--no-sandbox"]});
const requests = [];
const errors = [];
try {
  const context = await browser.newContext({viewport:{width:1280,height:900}});
  const page = await context.newPage();
  /** Retain only finite static request metadata to reject uploads or outside requests. */
  page.on("request", request => requests.push({url:request.url(),method:request.method()}));
  /** Retain test-page JavaScript errors without private media data. */
  page.on("pageerror", error => errors.push(error.message));
  await page.goto(origin);
  assert.equal(await page.getByRole("main",{name:"Ghi âm chủ động"}).count(),1);
  assert.equal(await page.getByRole("group",{name:"Điều khiển ghi âm"}).count(),1);
  await page.keyboard.press("Tab");
  assert.equal(await page.locator(":focus").getAttribute("id"),"start");
  await page.keyboard.press("Space");
  /** Wait only for the recorder's finite visible lifecycle transition. */
  await page.waitForFunction(() => document.getElementById("status").textContent.startsWith("Đang ghi âm"));
  await page.waitForTimeout(300);
  await page.keyboard.press("Tab");
  assert.equal(await page.locator(":focus").getAttribute("id"),"stop");
  await page.keyboard.press("Enter");
  await page.getByLabel("Bản ghi âm vừa tạo",{exact:true}).waitFor({state:"visible"});
  await page.screenshot({path:"data/backups/d86-recorder-desktop.png",fullPage:true});
  await page.keyboard.press("Escape");
  assert.equal(await page.locator("#preview").getAttribute("src"),null);
  await page.setViewportSize({width:320,height:740});
  await page.emulateMedia({colorScheme:"dark",reducedMotion:"reduce"});
  /** Read layout and accessibility attributes without inspecting or serializing captured audio. */
  const layout = await page.evaluate(() => ({width:innerWidth,scroll:document.documentElement.scrollWidth,
    live:document.getElementById("status").getAttribute("aria-live"),atomic:document.getElementById("status").getAttribute("aria-atomic"),
    previewLabel:document.getElementById("preview").getAttribute("aria-label"),background:getComputedStyle(document.body).backgroundColor,
    buttons:[...document.querySelectorAll("button")].map(button => button.getBoundingClientRect().height)}));
  assert.ok(layout.scroll <= layout.width);
  assert.ok(layout.buttons.every(height => height >= 44));
  assert.equal(layout.background,"rgb(16, 21, 29)");
  assert.equal(layout.live,"polite");
  assert.equal(layout.atomic,"true");
  await page.screenshot({path:"data/backups/d86-recorder-mobile-dark.png",fullPage:true});
  assert.deepEqual(errors,[]);
  assert.equal(requests.some(request => request.method !== "GET" || (!request.url.startsWith(origin+"/") && !request.url.startsWith("blob:"))),false);
  console.info(JSON.stringify({description:"Actual fake-device browser keyboard/layout smoke; not physical mic, subjective listening or formal screen-reader/WCAG certification.",passed:true,browser:browser.version(),layout,keyboard_start_stop_escape:true,external_requests_or_uploads:false,page_errors:errors}));
} finally {
  await browser.close();
}
