/** Bind the isolated voice trial to explicit browser gestures, ephemeral results and nonphysical timing markers. */
import {TrialRecorder, TrialSession} from "./session.mjs";

const elements = Object.fromEntries(["prepare", "start", "stop", "send", "cancel", "status", "capture-status", "preview", "reply", "result", "answer", "transcript", "timing", "pair", "pair-code", "close-session"].map(id => [id, document.getElementById(id)]));
let paired = false;
let server = {state: "idle", remaining: 24, preparations_remaining: 3};
let sending = false;
let output = null;
let source = null;
let answerURL = null;
let expiry = null;
let pollBusy = false;
let feedback = "";
const labels = {idle: "Bấm Chuẩn bị để bắt đầu phiên voice.", preparing: "Đang chuẩn bị, vui lòng chờ…", ready: "Sẵn sàng. Bạn có thể ghi câu hỏi.", busy: "Đang nghe và tạo câu trả lời…", error: "Chưa chuẩn bị được. Kiểm tra tài nguyên máy rồi chủ động thử lại."};
const captureLabels = {idle: "Chưa ghi âm.", requesting: "Đang chờ quyền microphone…", recording: "Đang thu — tối đa 20 giây.", ready: "Đã tắt microphone. Bạn có thể nghe lại rồi bấm Gửi.", cancelled: "Đã tắt thu và xóa câu hỏi.", error: "Không thể ghi âm. Kiểm tra quyền microphone và thử lại."};

/** Route only the existing explicit session protocol to the authenticated same-origin main backend. */
function apiFetch(path, options = {}) {
  if (!path.startsWith("/api/")) return Promise.reject(new Error("invalid_endpoint"));
  return fetch("/ui/voice/" + path.slice(5), {...options, credentials: "same-origin", cache: "no-store"});
}

/** Emit only finite lifecycle events without audio, transcripts, answers or credentials. */
function audit(event) { console.info("main_voice_event", event); }

/** Release scheduled output without silently resuming it when the tab returns. */
function stopAudio() {
  if (source) { try { source.stop(); } catch {} source.disconnect(); source = null; }
  if (output) { void output.close().catch(() => audit("output_close_failed")); output = null; }
}

/** Erase all answer text, native replay references and pending retention callbacks. */
function clearResult() {
  clearTimeout(expiry);
  elements.reply.pause(); elements.reply.removeAttribute("src"); elements.reply.load();
  if (answerURL) URL.revokeObjectURL(answerURL);
  answerURL = null;
  elements.transcript.textContent = elements.answer.textContent = elements.timing.textContent = "";
  elements.result.hidden = true;
}

/** Reflect capture/runtime readiness without automatically recording, submitting or loading a model. */
function render() {
  elements["pair-code"].disabled = paired; elements.pair.disabled = paired; elements.pair.textContent = paired ? "Đã kết nối" : "Kết nối";
  const capturing = ["requesting", "recording"].includes(recorder.state);
  const ready = paired && server.state === "ready" && !sending;
  elements.prepare.disabled = !paired || sending || capturing || ["ready", "busy", "preparing"].includes(server.state) || !server.preparations_remaining || !server.remaining;
  elements.start.disabled = !ready || capturing || !server.remaining;
  elements.stop.disabled = recorder.state !== "recording";
  elements.send.disabled = !ready || recorder.state !== "ready" || !recorder.blob || recorder.blob.size < 32044 || !server.remaining;
  elements["capture-status"].textContent = feedback || captureLabels[recorder.state];
  if (recorder.state === "ready" && recorder.blob?.size < 32044) elements["capture-status"].textContent = "Câu ghi quá ngắn. Hãy ghi ít nhất 1 giây.";
  elements["close-session"].disabled = !paired || server.state === "idle";
  elements.status.textContent = !paired ? "Nhập mã ghép phiên để kết nối." : sending ? labels.busy : (!server.remaining ? "Phiên voice đã hết lượt." : labels[server.state]);
}

/** Decode bounded complete returned WAV bytes without remote URLs or stored browser records. */
function audioBlob(encoded) {
  const raw = Uint8Array.from(atob(encoded), c => c.charCodeAt(0));
  return new Blob([raw], {type: "audio/wav"});
}

/** Unlock only audio output in the Send gesture; this never acquires a microphone. */
async function unlockAudio() {
  stopAudio();
  output = new AudioContext();
  await output.resume();
  if (output.state !== "running") throw new Error("output_unavailable");
}

/** Schedule the complete current answer after decoding, refusing stale output across every asynchronous boundary. */
async function playAudio(encoded, current) {
  const context = output;
  if (!context || context.state !== "running") throw new Error("manual_playback");
  const decoded = await context.decodeAudioData(await audioBlob(encoded).arrayBuffer());
  if (!current() || output !== context || document.hidden) throw new Error("stale_playback");
  source = context.createBufferSource(); source.buffer = decoded; source.connect(context.destination); source.start();
}

/** Render model text as text only and retain replay for at most five minutes, separate from physical acceptance. */
function showResult(value, timing) {
  elements.transcript.textContent = value.transcript;
  elements.answer.textContent = value.answer;
  answerURL = URL.createObjectURL(audioBlob(value.audio_base64)); elements.reply.src = answerURL;
  elements.result.hidden = false;
  elements.timing.textContent = `Nhận audio: ${timing.received.toFixed(3)} giây. ` + (timing.playback === null ? "Chưa tự phát được. Bấm nút phát để nghe." : `Chuẩn bị phát: ${timing.playback.toFixed(3)} giây. Chưa đo tiếng từ loa.`);
  expiry = setTimeout(() => { session.cancel("result_expired"); recorder.cancel("result_expired"); }, 300000);
}

const session = new TrialSession({fetch: apiFetch, uuid: () => crypto.randomUUID(), now: () => performance.now(), unlockAudio, playAudio, stopAudio, clearResult, result: showResult, audit});
const recorder = new TrialRecorder({
  getUserMedia: options => navigator.mediaDevices.getUserMedia(options), createContext: options => new AudioContext(options),
  createNode: context => new AudioWorkletNode(context, "explicit-capture"), setTimer: (callback, delay) => setTimeout(callback, delay),
  clearTimer: timer => clearTimeout(timer), createURL: blob => URL.createObjectURL(blob), revokeURL: url => URL.revokeObjectURL(url), audit,
}, () => {
  elements.preview.pause(); elements.preview.removeAttribute("src");
  if (recorder.url) elements.preview.src = recorder.url;
  elements.preview.hidden = !recorder.url; elements.preview.load(); render();
});

/** Poll only noncontent status; opening or reloading the page cannot start model inference or recording. */
async function refresh() {
  if (pollBusy) return;
  pollBusy = true;
  try {
    const response = await apiFetch("/api/status", {credentials: "same-origin", cache: "no-store"});
    if (response.status === 401) { const wasPaired = paired; paired = false; if (wasPaired) cancel("session_unavailable"); else render(); elements.status.textContent = "Nhập mã ghép phiên để kết nối."; return; }
    if (!response.ok) throw new Error("status_failed");
    paired = true;
    server = await response.json(); render();
  } catch { elements.status.textContent = "Mất kết nối trang trợ lý. Hãy tải lại trang."; elements.prepare.disabled = elements.start.disabled = elements.send.disabled = true; }
  finally { pollBusy = false; }
}

/** End capture and current playback/work with no automatic resubmission or microphone restart. */
function cancel(reason = "user_cancelled") {
  elements["pair-code"].value = "";
  const stopping = Boolean(session.active) || server.state === "preparing";
  if (server.state === "preparing") void session.command("/api/release").catch(() => audit("release_delivery_failed"));
  session.cancel(reason); recorder.cancel(reason); feedback = ""; sending = false;
  if (stopping) server.state = "busy";
  render();
}

elements.prepare.addEventListener("click", async () => { elements.prepare.disabled = true; try { server = await session.prepare(); } catch { server.state = "error"; } render(); });
elements.start.addEventListener("click", () => { feedback = ""; session.cancel("new_capture"); void recorder.start(); });
elements.stop.addEventListener("click", () => recorder.stop());
elements.send.addEventListener("click", async () => {
  if (elements.send.disabled) return;
  const blob = recorder.blob; feedback = ""; sending = true; render();
  const submitted = session.submit(blob); recorder.cancel("explicitly_submitted"); feedback = "Đã gửi câu hỏi và tắt microphone."; render();
  try { await submitted; }
  catch (error) {
    if (error.name !== "AbortError") feedback = ({no_speech: "Không nhận thấy lời nói. Hãy ghi câu hỏi rõ hơn.", invalid_input: "Bản ghi cần dài từ 1 đến 20 giây.", busy: "Máy đang bận. Đợi sẵn sàng rồi tự gửi lại.", closed: "Phiên đã dừng. Bấm Chuẩn bị để tiếp tục.", timeout: "Lượt xử lý quá lâu và đã dừng."})[error.message] ?? "Không xử lý được câu hỏi. Hãy chuẩn bị lại phiên voice.";
  } finally { sending = false; await refresh(); }
});
elements.cancel.addEventListener("click", () => cancel());
elements.reply.addEventListener("play", () => stopAudio());
document.addEventListener("keydown", event => { if (event.key === "Escape") cancel(); });
document.addEventListener("visibilitychange", () => { if (document.hidden) cancel("page_hidden"); });
window.addEventListener("pagehide", () => cancel("page_exit"));
setInterval(() => { if (!document.hidden) void refresh(); }, 1500);
elements.pair.addEventListener("click", async () => {
  const code = elements["pair-code"].value; elements["pair-code"].value = "";
  elements.pair.disabled = true;
  try {
    const response = await fetch("/ui/voice/pair", {method: "POST", credentials: "same-origin", cache: "no-store",
      headers: {"Content-Type": "application/json", "X-Voice-Submit": "1"}, body: JSON.stringify({code})});
    if (!response.ok) throw new Error("pair_failed");
    paired = true; await refresh();
  } catch { paired = false; render(); elements.status.textContent = "Mã không hợp lệ hoặc đã hết hạn. Hãy lấy mã mới."; }
  finally { elements.pair.disabled = paired; }
});
elements["close-session"].addEventListener("click", async () => {
  cancel("close_voice_session");
  elements["close-session"].disabled = true;
  try { const response = await session.command("/api/release"); if (!response.ok) throw new Error("close_failed"); await refresh(); }
  catch { elements.status.textContent = "Chưa xác nhận đóng phiên. Các yêu cầu mới có thể vẫn đang bị khóa."; }
  finally { elements["close-session"].disabled = false; }
});
render(); void refresh();
