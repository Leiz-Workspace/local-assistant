/** Bind trusted explicit recording controls to browser capabilities without persistent state or audio transmission. */
import {ExplicitRecorder} from "/recorder.mjs";

const start = document.getElementById("start");
const stop = document.getElementById("stop");
const cancel = document.getElementById("cancel");
const preview = document.getElementById("preview");
const labels = {idle: "Chưa ghi âm", requesting: "Đang chờ quyền microphone; có thể bấm Hủy", recording: "Đang ghi âm — tối đa 30 giây", ready: "Đã dừng microphone; có thể nghe lại", cancelled: "Đã hủy và xóa audio", error: "Không thể ghi âm. Kiểm tra quyền hoặc thiết bị rồi chủ động thử lại."};

/** Reflect lifecycle state without rendering audio content or implementation details. */
function render(state) {
  document.getElementById("status").textContent = labels[state];
  start.disabled = ["requesting", "recording"].includes(state);
  stop.disabled = state !== "recording";
  cancel.disabled = state === "idle" || state === "cancelled";
  preview.pause();
  preview.removeAttribute("src");
  if (recorder.url) preview.src = recorder.url;
  preview.hidden = !recorder.url;
  preview.load();
}

const recorder = new ExplicitRecorder({
  getUserMedia: constraints => navigator.mediaDevices.getUserMedia(constraints),
  createContext: options => new AudioContext(options),
  createNode: context => new AudioWorkletNode(context, "explicit-capture"),
  setTimer: (callback, delay) => setTimeout(callback, delay),
  clearTimer: timer => clearTimeout(timer),
  createURL: blob => URL.createObjectURL(blob),
  revokeURL: url => URL.revokeObjectURL(url),
  audit: event => console.info("explicit_recording_event", event),
}, render);

start.addEventListener("click", () => { void recorder.start(); });
stop.addEventListener("click", () => recorder.stop());
cancel.addEventListener("click", () => recorder.cancel());
document.addEventListener("keydown", event => { if (event.key === "Escape") recorder.cancel(); });
document.addEventListener("visibilitychange", () => { if (document.hidden) recorder.cancel("page_hidden"); });
window.addEventListener("pagehide", () => recorder.cancel("page_exit"));
