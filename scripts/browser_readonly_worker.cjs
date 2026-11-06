/** Run only the pinned browser's inherited CDP pipes inside network-none confinement and emit metadata-only lifecycle diagnostics. */
"use strict";

const { spawn } = require("node:child_process");
const { createHash } = require("node:crypto");
const METHODS = new Set([
  "Browser.getVersion", "Browser.setDownloadBehavior", "Browser.setPermission", "Browser.close",
  "Target.createBrowserContext", "Target.createTarget", "Target.setAutoAttach", "Target.setDiscoverTargets",
  "Target.closeTarget", "Target.attachToTarget", "Target.disposeBrowserContext", "Page.enable", "Page.setLifecycleEventsEnabled",
  "Page.navigate", "Page.getFrameTree", "Page.handleJavaScriptDialog", "DOMSnapshot.captureSnapshot", "Runtime.runIfWaitingForDebugger",
  "Fetch.enable", "Fetch.failRequest", "Fetch.fulfillRequest", "Network.enable", "Network.setCacheDisabled",
  "Network.setBypassServiceWorker"
]);
const MAX_FRAME = 2097152;
const MAX_DIRECTION = 16777216;
const argumentsList = [
  "--headless=new", "--no-startup-window", "--no-sandbox", "--disable-gpu", "--disable-extensions",
  "--disable-background-networking", "--disable-component-update", "--no-first-run", "--no-default-browser-check",
  "--disable-breakpad", "--disable-crash-reporter", "--disable-sync", "--deny-permission-prompts",
  "--disk-cache-size=16777216", "--media-cache-size=0", "--user-data-dir=/tmp/browser-profile",
  "--remote-debugging-pipe", "--window-size=1200,800"
];
let browser;
let incoming = Buffer.alloc(0), outgoing = Buffer.alloc(0);
let stderrBytes = 0, commands = 0, frames = 0;
let inputBytes = 0, outputBytes = 0;
let stopping = false, finished = false, failure = null, killTimer = null;
const stderrHash = createHash("sha256");

/** Emit only fixed lifecycle identifiers and finite native metadata, never a page or raw browser diagnostic. */
function audit(event, details = {}) {
  process.stderr.write(JSON.stringify({ event, ...details }) + "\n");
}

/** Stop only the owned browser and cap graceful retirement before its container supervisor joins it. */
function stop(code) {
  if (stopping || finished) return;
  stopping = true;
  failure = code || null;
  process.stdin.pause();
  if (browser) browser.kill("SIGTERM");
  killTimer = setTimeout(forceKill, 2000);
  audit("browser_worker_stop_requested", { failed: !!failure });
}

/** Finish an unresponsive owned browser without signaling any host process or external container. */
function forceKill() {
  if (browser) browser.kill("SIGKILL");
}

/** Validate one finite host command before forwarding the complete frame over child FD3. */
function command(frame) {
  let value;
  try { value = JSON.parse(frame.toString("utf8")); } catch { stop("command_invalid"); return; }
  if (!value || !Number.isInteger(value.id) || value.id < 1 || !METHODS.has(value.method) || commands >= 4096) {
    stop("command_denied"); return;
  }
  commands += 1;
  if (!browser.stdio[3].write(Buffer.concat([frame, Buffer.from([0])]))) process.stdin.pause();
}

/** Parse bounded NUL-delimited host input without accepting arbitrary executable or JavaScript commands. */
function input(chunk) {
  inputBytes += chunk.length;
  if (inputBytes > MAX_DIRECTION) { stop("command_total_limit"); return; }
  incoming = Buffer.concat([incoming, chunk]);
  let boundary;
  while ((boundary = incoming.indexOf(0)) >= 0) {
    if (boundary > MAX_FRAME) { stop("command_frame_limit"); return; }
    const frame = incoming.subarray(0, boundary);
    incoming = incoming.subarray(boundary + 1);
    command(frame);
    if (stopping) return;
  }
  if (incoming.length > MAX_FRAME) stop("command_frame_limit");
}

/** Resume host input only after actual browser command-pipe backpressure has drained. */
function drained() {
  if (!stopping) process.stdin.resume();
}

/** Forward only complete bounded native CDP frames, without printing their private contents into audit logs. */
function output(chunk) {
  outputBytes += chunk.length;
  if (outputBytes > MAX_DIRECTION) { stop("response_total_limit"); return; }
  outgoing = Buffer.concat([outgoing, chunk]);
  let boundary;
  while ((boundary = outgoing.indexOf(0)) >= 0) {
    if (boundary > MAX_FRAME || frames >= 8192) { stop("response_frame_limit"); return; }
    const frame = outgoing.subarray(0, boundary + 1);
    outgoing = outgoing.subarray(boundary + 1);
    frames += 1;
    if (!process.stdout.write(frame)) browser.stdio[4].pause();
  }
  if (outgoing.length > MAX_FRAME) stop("response_frame_limit");
}

/** Resume native CDP output only after the host has consumed its bounded pipe backlog. */
function outputDrained() {
  if (browser && !finished) browser.stdio[4].resume();
}

/** Retain only size/hash of untrusted native diagnostics and stop on overflow. */
function diagnostic(chunk) {
  stderrBytes += chunk.length;
  if (stderrBytes > 65536) { stop("stderr_limit"); return; }
  stderrHash.update(chunk);
}

/** Retire on command/output pipe loss without echoing native error messages or private URLs. */
function pipeLost() {
  stop("pipe_lost");
}

/** Treat host EOF as the end of the operation, never as permission to keep browsing. */
function hostEnded() {
  stop("host_eof");
}

/** Join the actual browser exit and emit only a finite final record before the worker itself closes. */
function closed(code, signal) {
  if (finished) return;
  finished = true;
  clearTimeout(killTimer);
  audit("browser_worker_closed", { code, signal, commands, frames, input_bytes: inputBytes, output_bytes: outputBytes, stderr_bytes: stderrBytes, stderr_sha256: stderrHash.digest("hex"), failure });
  process.stdin.destroy();
  process.exitCode = failure && failure !== "host_eof" ? 1 : (code === 0 ? 0 : 1);
}

/** Report a sanitized startup failure when the pinned executable cannot be spawned. */
function startFailed() {
  failure = "spawn_failed";
  audit("browser_worker_spawn_failed");
}

browser = spawn("/opt/brave.com/brave-origin/brave-origin", argumentsList, {
  env: { HOME: "/tmp", PATH: "/usr/bin:/bin", LANG: "C.UTF-8" },
  stdio: ["ignore", "ignore", "pipe", "pipe", "pipe"]
});
browser.stdio[3].on("error", pipeLost);
browser.stdio[3].on("drain", drained);
browser.stdio[4].on("data", output);
browser.stderr.on("data", diagnostic);
browser.on("error", startFailed);
browser.on("close", closed);
process.stdin.on("data", input);
process.stdin.on("end", hostEnded);
process.stdin.on("error", pipeLost);
process.stdout.on("drain", outputDrained);
process.stdout.on("error", pipeLost);
process.on("SIGTERM", hostEnded);
process.on("SIGINT", hostEnded);
audit("browser_worker_started");
