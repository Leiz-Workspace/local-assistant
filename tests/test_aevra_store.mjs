import assert from "node:assert/strict";
import test from "node:test";

// Force the in-memory fallback; Node has no IndexedDB.
globalThis.indexedDB = { open() { throw new Error("indexeddb_unavailable"); } };
const store = await import("../apps/harness/static/aevra/store.js");

const CONVERSATION = "c1";
const UUID = "123e4567-e89b-12d3-a456-426614174000";
const START = Date.UTC(2026, 0, 1);

function user(over = {}) {
  return { id: "m1", convId: CONVERSATION, role: "user", content: "hi", parent: null, children: ["m2"], createdAt: START, ...over };
}

function assistant(over = {}) {
  return { id: "m2", convId: CONVERSATION, role: "assistant", content: "ok", parent: "m1", children: [], createdAt: START + 1, status: "done", ...over };
}

function wrap(messages, extra = {}) {
  return { format: "aevra-conversations", version: 1, conversations: [{ id: CONVERSATION, title: "t", messages, ...extra }] };
}

async function rejects(messages, extra) {
  await assert.rejects(store.importConversations(wrap(messages, extra)), /invalid_import/);
}

test("rejects an empty user message", () => rejects([user({ content: "   " }), assistant()]));

test("rejects a skill reference that is not a UUID pair", () => rejects([user({ skill: { installation_id: "x", workspace_id: UUID } }), assistant()]));

test("rejects timestamps outside the supported range", async () => {
  await rejects([user({ createdAt: 1 }), assistant()]);
  await rejects([user(), assistant()], { updatedAt: Date.now() + 10 * 86400000 });
});

test("rejects parent cycles and duplicate message ids", async () => {
  await rejects([user({ parent: "m2" }), assistant()]);
  await rejects([user(), assistant({ id: "m1" })]);
});

test("rejects an error field that is not an error code", () => rejects([user(), assistant({ error: "<img src=x>" })]));

test("rejects a duplicate count outside 0..4", () => rejects([user(), assistant({ duplicates: 9 })]));

test("carries known metadata and drops unknown fields", async () => {
  const before = (await store.listConversations()).length;
  const count = await store.importConversations(wrap([
    user({ skill: { installation_id: UUID, workspace_id: UUID, label: "Review" }, extra: "dropped" }),
    assistant({ usage: { prompt_tokens: 3, completion_tokens: 2 }, timing: { totalMs: 12.5, firstTokenMs: null }, context: { input_tokens: 10, preset_selected: "fast" }, omitted: 1, duplicates: 2, edited: true, error: "stream_timeout" }),
  ]));
  assert.equal(count, 1);
  const list = await store.listConversations();
  assert.equal(list.length, before + 1);
  const loaded = await store.loadConversation(list.find((item) => item.title === "t").id);
  const answer = loaded.messages.find((message) => message.role === "assistant");
  const question = loaded.messages.find((message) => message.role === "user");
  assert.deepEqual(answer.usage, { prompt_tokens: 3, completion_tokens: 2 });
  assert.deepEqual(answer.timing, { totalMs: 12.5 });
  assert.deepEqual(answer.context, { input_tokens: 10 });
  assert.equal(answer.omitted, 1);
  assert.equal(answer.duplicates, 2);
  assert.equal(answer.edited, true);
  assert.equal(answer.error, "stream_timeout");
  assert.equal(question.skill.label, "Review");
  assert.equal("extra" in question, false);
  assert.notEqual(question.id, "m1");
  assert.equal(answer.parent, question.id);
});

test("validates a long linear chain quickly", async () => {
  const chain = Array.from({ length: 10000 }, (_, index) => ({
    id: `n${index}`,
    convId: CONVERSATION,
    role: index % 2 ? "assistant" : "user",
    content: "x",
    parent: index ? `n${index - 1}` : null,
    children: index < 9999 ? [`n${index + 1}`] : [],
    createdAt: START + index,
    status: index % 2 ? "done" : undefined,
  }));
  const started = performance.now();
  assert.equal(await store.importConversations(wrap(chain)), 1);
  assert.ok(performance.now() - started < 5000);
});
