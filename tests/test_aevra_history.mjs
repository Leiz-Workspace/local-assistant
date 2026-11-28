import assert from "node:assert/strict";
import test from "node:test";
import { MAX_MESSAGES, boundedHistory, buildRequest, byteSize } from "../apps/harness/static/aevra/history.js";

function conversation(turns) {
  const messages = [];
  for (let index = 0; index < turns; index += 1) {
    messages.push({ role: "user", content: `u${index}` }, { role: "assistant", content: `a${index}` });
  }
  messages.push({ role: "user", content: "current" });
  return messages;
}

test("keeps a short conversation unchanged", () => {
  const messages = conversation(3);
  assert.deepEqual(boundedHistory(messages), messages);
});

test("trims by message count to whole pairs ending with the current turn", () => {
  const kept = boundedHistory(conversation(128));
  assert.equal(kept.length, 255);
  assert.equal(kept[0].role, "user");
  assert.equal(kept.at(-1).content, "current");
  kept.forEach((message, index) => assert.equal(message.role, index % 2 ? "assistant" : "user"));
});

test("trims by bytes without starting on an assistant turn", () => {
  const messages = conversation(10);
  const kept = boundedHistory(messages, { maxBytes: byteSize(messages.at(-1)) + byteSize(messages.at(-2)) + 1 });
  assert.deepEqual(kept, [messages.at(-1)]);
  assert.deepEqual(boundedHistory([]), []);
});

function path(pairs, current = "current") {
  const messages = [];
  for (let index = 0; index < pairs; index += 1) {
    messages.push({ role: "user", content: `u${index}` }, { role: "assistant", content: `a${index}`, status: "done" });
  }
  messages.push({ role: "user", content: current });
  return messages;
}

test("buildRequest counts dropped question/answer pairs, not messages", () => {
  const full = path(3);
  const keep = byteSize({ role: "user", content: "u2" }) + byteSize({ role: "assistant", content: "a2" }) + byteSize({ role: "user", content: "current" });
  const request = buildRequest(full, "", keep);
  assert.deepEqual(request.messages.map((message) => message.content), ["u2", "a2", "current"]);
  assert.equal(request.droppedPairs, 2);
  assert.equal(buildRequest(full, "", 1e9).droppedPairs, 0);
});

test("buildRequest returns null when the current turn alone does not fit", () => {
  assert.equal(buildRequest(path(1, "x".repeat(500)), "", 100), null);
});

test("buildRequest skips answers that failed or are empty", () => {
  const messages = [
    { role: "user", content: "u0" }, { role: "assistant", content: "partial", status: "error" },
    { role: "user", content: "u1" }, { role: "assistant", content: "  ", status: "done" },
    { role: "user", content: "u2" }, { role: "assistant", content: "kept", status: "stopped" },
    { role: "user", content: "current" },
  ];
  const request = buildRequest(messages, "", 1e9);
  assert.deepEqual(request.messages.map((message) => message.content), ["u2", "kept", "current"]);
  assert.equal(request.droppedPairs, 0);
});

test("buildRequest puts the system message first and leaves room for it in the count", () => {
  const request = buildRequest(path(200), "rules", 1e9);
  assert.equal(request.messages[0].role, "system");
  assert.equal(request.messages.length, MAX_MESSAGES);
  assert.equal(request.messages.at(-1).content, "current");
  assert.equal(request.messages[1].role, "user");
});
