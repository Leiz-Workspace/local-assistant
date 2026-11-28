import assert from "node:assert/strict";
import test from "node:test";

/*
 * A small IndexedDB stand-in with transaction semantics: writes are buffered and applied only when the
 * transaction completes, and a failed write aborts the whole transaction.
 */
const committed = { conversations: new Map(), messages: new Map() };
const created = new Set();
const transactions = [];
const failure = { afterPuts: Infinity, puts: 0 };

function request(value) {
  const req = { result: undefined, error: null, onsuccess: null, onerror: null };
  setTimeout(() => {
    req.result = value;
    req.onsuccess?.();
  }, 0);
  return req;
}

function database() {
  return {
    objectStoreNames: { contains: (name) => created.has(name) },
    createObjectStore(name) {
      created.add(name);
      return { createIndex() {} };
    },
    transaction(names, mode = "readonly") {
      const stores = Array.isArray(names) ? names : [names];
      const pending = [];
      let error = null;
      let finished = false;
      const tx = {
        mode,
        stores,
        error: null,
        oncomplete: null,
        onerror: null,
        onabort: null,
        abort() {
          if (finished) throw new Error("InvalidStateError");
          finished = true;
          tx.error = new Error("AbortError");
          setTimeout(() => tx.onabort?.(), 0);
        },
        objectStore(name) {
          if (!stores.includes(name)) throw new Error("NotFoundError");
          const data = committed[name];
          return {
            put(value) {
              if (mode !== "readwrite") throw new Error("ReadOnlyError");
              failure.puts += 1;
              if (failure.puts > failure.afterPuts && !error) error = Object.assign(new Error("QuotaExceededError"), { name: "QuotaExceededError" });
              const copy = structuredClone(value);
              pending.push(() => data.set(copy.id, copy));
              return request(copy.id);
            },
            delete(id) {
              pending.push(() => data.delete(id));
              return request(undefined);
            },
            clear() {
              pending.push(() => data.clear());
              return request(undefined);
            },
            get: (id) => request(structuredClone(data.get(id))),
            getAll: () => request([...data.values()].map((value) => structuredClone(value))),
            index: () => ({ getAll: (key) => request([...data.values()].filter((value) => value.convId === key).map((value) => structuredClone(value))) }),
          };
        },
      };
      transactions.push(tx);
      setTimeout(() => {
        if (finished) return;
        finished = true;
        if (error) {
          tx.error = error;
          tx.onerror?.();
          tx.onabort?.();
          return;
        }
        pending.forEach((apply) => apply());
        tx.oncomplete?.();
      }, 5);
      return tx;
    },
  };
}

globalThis.indexedDB = {
  open() {
    const req = { result: null, onupgradeneeded: null, onsuccess: null, onerror: null };
    setTimeout(() => {
      req.result = database();
      req.onupgradeneeded?.();
      req.onsuccess?.();
    }, 0);
    return req;
  },
};

const store = await import("../apps/harness/static/aevra/store.js");
const START = Date.UTC(2026, 0, 1);

function conversation(id) {
  return {
    id,
    title: `t-${id}`,
    messages: [
      { id: "m1", convId: id, role: "user", content: "hi", parent: null, children: ["m2"], createdAt: START },
      { id: "m2", convId: id, role: "assistant", content: "ok", parent: "m1", children: [], createdAt: START + 1, status: "done" },
    ],
  };
}

function file(...ids) {
  return { format: "aevra-conversations", version: 1, conversations: ids.map(conversation) };
}

function snapshot() {
  return { conversations: committed.conversations.size, messages: committed.messages.size, writes: transactions.filter((tx) => tx.mode === "readwrite").length };
}

test("imports every conversation in one transaction over both stores", async () => {
  const before = snapshot();
  assert.equal(await store.importConversations(file("a", "b")), 2);
  const after = snapshot();
  assert.equal(after.writes - before.writes, 1);
  const tx = transactions.filter((item) => item.mode === "readwrite").at(-1);
  assert.deepEqual([...tx.stores].sort(), ["conversations", "messages"]);
  assert.equal(after.conversations - before.conversations, 2);
  assert.equal(after.messages - before.messages, 4);
  assert.equal((await store.listConversations()).length, after.conversations);
});

test("a storage failure part-way leaves nothing behind", async () => {
  const before = snapshot();
  // Fail on the fourth of six writes (four messages, then two conversations).
  failure.afterPuts = failure.puts + 3;
  try {
    await assert.rejects(store.importConversations(file("c", "d")), /import_storage_failed/);
  } finally {
    failure.afterPuts = Infinity;
  }
  const after = snapshot();
  assert.equal(after.conversations, before.conversations);
  assert.equal(after.messages, before.messages);
});

test("an invalid file is rejected before anything is written", async () => {
  const before = snapshot();
  const bad = file("e");
  bad.conversations[0].messages[1].parent = "m2";
  await assert.rejects(store.importConversations(bad), /invalid_import/);
  assert.deepEqual(snapshot(), before);
});
