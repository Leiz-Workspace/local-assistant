/** Device-local conversation store in IndexedDB, with an in-memory fallback. */
const DB_NAME = "aevra";
const VERSION = 1;
const memory = { conversations: new Map(), messages: new Map() };
let dbPromise = null;
export const storage = { persistent: true };

function open() {
  if (dbPromise) return dbPromise;
  dbPromise = new Promise((resolve) => {
    let requestDb;
    try {
      requestDb = indexedDB.open(DB_NAME, VERSION);
    } catch {
      storage.persistent = false;
      resolve(null);
      return;
    }
    requestDb.onupgradeneeded = () => {
      const db = requestDb.result;
      if (!db.objectStoreNames.contains("conversations")) db.createObjectStore("conversations", { keyPath: "id" });
      if (!db.objectStoreNames.contains("messages")) db.createObjectStore("messages", { keyPath: "id" }).createIndex("conversation", "convId");
    };
    requestDb.onsuccess = () => resolve(requestDb.result);
    requestDb.onerror = () => {
      storage.persistent = false;
      resolve(null);
    };
  });
  return dbPromise;
}

function done(transaction) {
  return new Promise((resolve, reject) => {
    transaction.oncomplete = () => resolve();
    transaction.onerror = () => reject(transaction.error);
    transaction.onabort = () => reject(transaction.error);
  });
}

function result(requestDb) {
  return new Promise((resolve, reject) => {
    requestDb.onsuccess = () => resolve(requestDb.result);
    requestDb.onerror = () => reject(requestDb.error);
  });
}

export function newId() {
  return crypto.randomUUID();
}

export async function listConversations() {
  const db = await open();
  const rows = db ? await result(db.transaction("conversations").objectStore("conversations").getAll()) : [...memory.conversations.values()];
  return rows.sort((a, b) => b.updatedAt - a.updatedAt);
}

export async function loadConversation(id) {
  const db = await open();
  if (!db) {
    const conversation = memory.conversations.get(id);
    return conversation ? { conversation, messages: [...memory.messages.values()].filter((message) => message.convId === id) } : null;
  }
  const transaction = db.transaction(["conversations", "messages"]);
  const conversation = await result(transaction.objectStore("conversations").get(id));
  if (!conversation) return null;
  const messages = await result(transaction.objectStore("messages").index("conversation").getAll(id));
  return { conversation, messages };
}

export async function saveConversation(conversation) {
  const db = await open();
  if (!db) {
    memory.conversations.set(conversation.id, structuredClone(conversation));
    return;
  }
  const transaction = db.transaction("conversations", "readwrite");
  transaction.objectStore("conversations").put(conversation);
  await done(transaction);
}

export async function saveMessages(messages) {
  const db = await open();
  if (!db) {
    messages.forEach((message) => memory.messages.set(message.id, structuredClone(message)));
    return;
  }
  const transaction = db.transaction("messages", "readwrite");
  messages.forEach((message) => transaction.objectStore("messages").put(message));
  await done(transaction);
}

export async function deleteMessages(ids) {
  const db = await open();
  if (!db) {
    ids.forEach((id) => memory.messages.delete(id));
    return;
  }
  const transaction = db.transaction("messages", "readwrite");
  ids.forEach((id) => transaction.objectStore("messages").delete(id));
  await done(transaction);
}

export async function deleteConversation(id) {
  const loaded = await loadConversation(id);
  if (!loaded) return;
  await deleteMessages(loaded.messages.map((message) => message.id));
  const db = await open();
  if (!db) {
    memory.conversations.delete(id);
    return;
  }
  const transaction = db.transaction("conversations", "readwrite");
  transaction.objectStore("conversations").delete(id);
  await done(transaction);
}

export async function deleteAll() {
  const db = await open();
  if (!db) {
    memory.conversations.clear();
    memory.messages.clear();
    return;
  }
  const transaction = db.transaction(["conversations", "messages"], "readwrite");
  transaction.objectStore("conversations").clear();
  transaction.objectStore("messages").clear();
  await done(transaction);
}

export async function exportConversations(ids) {
  const conversations = [];
  for (const id of ids) {
    const loaded = await loadConversation(id);
    if (loaded) conversations.push({ ...loaded.conversation, messages: loaded.messages });
  }
  return { format: "aevra-conversations", version: 1, exportedAt: new Date().toISOString(), conversations };
}

const ROLES = new Set(["user", "assistant", "system"]);
const STATUSES = new Set(["done", "stopped", "error", "streaming", undefined]);
const PRESETS = new Set(["fast", "balanced", "deep", "auto", "unlimited"]);
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const ERROR_CODE = /^[a-z0-9_]{1,64}$/;
// Timestamps must fall between 2020-01-01 and one day from now.
const MIN_TIME = Date.UTC(2020, 0, 1);
const isText = (value, max) => typeof value === "string" && value.length <= max;
const isTime = (value) => Number.isFinite(value) && value >= MIN_TIME && value <= Date.now() + 86400000;
const isCount = (value) => Number.isInteger(value) && value >= 0 && value <= 1e9;
const isAmount = (value) => Number.isFinite(value) && value >= 0 && value <= 1e12;

function validAttachment(item) {
  return item && isText(item.name, 256) && item.name.length > 0 && isText(item.content, 65536) && item.content.length > 0
    && (item.size === undefined || isCount(item.size));
}

function validSkill(skill) {
  return skill === undefined || skill === null || (typeof skill === "object" && typeof skill.installation_id === "string" && UUID.test(skill.installation_id)
    && typeof skill.workspace_id === "string" && UUID.test(skill.workspace_id) && (skill.label === undefined || isText(skill.label, 200)));
}

function numbers(value, keys) {
  return value === undefined || value === null || (typeof value === "object" && keys.every((key) => value[key] === undefined || value[key] === null || isAmount(value[key])));
}

function validMessage(message, convId) {
  return message && isText(message.id, 128) && message.convId === convId && ROLES.has(message.role)
    && isText(message.content, 1048576) && (message.role !== "user" || message.content.trim().length > 0)
    && (message.reasoning === undefined || isText(message.reasoning, 1048576))
    && (message.parent === null || isText(message.parent, 128)) && message.parent !== message.id
    && Array.isArray(message.children) && message.children.every((child) => isText(child, 128))
    && isTime(message.createdAt) && STATUSES.has(message.status)
    && (message.attachments === undefined || (Array.isArray(message.attachments) && message.attachments.length <= 4 && message.attachments.every(validAttachment)))
    && validSkill(message.skill)
    && (message.error === undefined || message.error === null || (typeof message.error === "string" && ERROR_CODE.test(message.error)))
    && (message.edited === undefined || typeof message.edited === "boolean")
    && (message.omitted === undefined || (Number.isInteger(message.omitted) && message.omitted >= 0 && message.omitted <= 4))
    && numbers(message.usage, ["prompt_tokens", "completion_tokens", "total_tokens"])
    && numbers(message.timing, ["totalMs", "firstTokenMs", "generationMs"])
    && numbers(message.context, ["input_tokens", "input_limit", "context_size", "max_tokens"]);
}

/** Reject parent chains that loop, so an imported tree can never hang path or leaf walks (linear time). */
function acyclic(messages) {
  const parents = new Map(messages.map((message) => [message.id, message.parent]));
  const state = new Map();
  for (const message of messages) {
    const trail = [];
    let current = message.id;
    while (current && parents.has(current) && !state.has(current)) {
      state.set(current, "visiting");
      trail.push(current);
      current = parents.get(current);
    }
    if (current && state.get(current) === "visiting") return false;
    trail.forEach((id) => state.set(id, "done"));
  }
  return true;
}

function validConversation(source) {
  return source && isText(source.id, 128) && Array.isArray(source.messages) && source.messages.length <= 10000
    && new Set(source.messages.map((message) => message?.id)).size === source.messages.length
    && source.messages.every((message) => validMessage(message, source.id)) && acyclic(source.messages)
    && (source.title === undefined || isText(source.title, 500)) && (source.preset === undefined || PRESETS.has(source.preset))
    && (source.systemPrompt === undefined || isText(source.systemPrompt, 8000))
    && (source.createdAt === undefined || isTime(source.createdAt)) && (source.updatedAt === undefined || isTime(source.updatedAt));
}

const pick = (value, keys) => (value && typeof value === "object" ? Object.fromEntries(keys.filter((key) => Number.isFinite(value[key])).map((key) => [key, value[key]])) : undefined);

export async function importConversations(data) {
  if (data?.format !== "aevra-conversations" || data.version !== 1 || !Array.isArray(data.conversations)) throw new Error("invalid_import");
  if (data.conversations.length > 1000 || !data.conversations.every(validConversation)) throw new Error("invalid_import");
  let count = 0;
  for (const source of data.conversations) {
    const ids = new Map(source.messages.map((message) => [message.id, newId()]));
    const convId = newId();
    const messages = source.messages.map((message) => ({
      id: ids.get(message.id),
      role: message.role,
      content: message.content,
      reasoning: message.reasoning || "",
      status: message.status === "streaming" ? "stopped" : message.status,
      attachments: message.attachments?.map((file) => ({ name: file.name, content: file.content, size: file.size ?? file.content.length })),
      skill: message.skill ? { installation_id: message.skill.installation_id, workspace_id: message.skill.workspace_id, label: message.skill.label || "" } : null,
      ...(message.error ? { error: message.error } : {}),
      ...(message.edited ? { edited: true } : {}),
      ...(message.omitted ? { omitted: message.omitted } : {}),
      ...(message.usage ? { usage: pick(message.usage, ["prompt_tokens", "completion_tokens", "total_tokens"]) } : {}),
      ...(message.timing ? { timing: pick(message.timing, ["totalMs", "firstTokenMs", "generationMs"]) } : {}),
      ...(message.context ? { context: pick(message.context, ["input_tokens", "input_limit", "context_size", "max_tokens"]) } : {}),
      createdAt: message.createdAt,
      convId,
      parent: message.parent ? ids.get(message.parent) ?? null : null,
      children: message.children.map((child) => ids.get(child)).filter(Boolean),
    }));
    await saveMessages(messages);
    // Only known fields are kept; anything else in the file is ignored.
    await saveConversation({ id: convId, title: String(source.title || "Hội thoại nhập").slice(0, 120), createdAt: source.createdAt ?? Date.now(), updatedAt: source.updatedAt ?? Date.now(), currNode: ids.get(source.currNode) ?? messages.at(-1)?.id ?? null, pinned: source.pinned === true, preset: source.preset || "fast", systemPrompt: source.systemPrompt || "" });
    count += 1;
  }
  return count;
}
