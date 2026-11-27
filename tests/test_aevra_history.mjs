import assert from "node:assert/strict";
import test from "node:test";
import { boundedHistory, byteSize } from "../apps/harness/static/aevra/history.js";

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
