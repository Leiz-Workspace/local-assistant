/** Bound chat history to the server's request limits without breaking user/assistant pairs. */
export const MAX_MESSAGES = 256;
export const MAX_BYTES = 240000;

export function byteSize(value) {
  return new TextEncoder().encode(JSON.stringify(value)).length + 1;
}

export function boundedHistory(messages, { maxMessages = MAX_MESSAGES, maxBytes = MAX_BYTES } = {}) {
  const kept = [];
  let total = 0;
  for (let index = messages.length - 1; index >= 0 && kept.length < maxMessages; index -= 1) {
    const size = byteSize(messages[index]);
    if (total + size > maxBytes) break;
    kept.unshift(messages[index]);
    total += size;
  }
  // History policies require complete pairs, so the window must start with a user turn.
  while (kept.length > 1 && kept[0].role !== "user") kept.shift();
  return kept;
}

/**
 * Build the chat request from the active path: complete question/answer pairs, always ending with the
 * current user turn. Returns null when that turn cannot fit; droppedPairs counts the pairs left out.
 */
export function buildRequest(path, system, maxBytes) {
  const turns = [];
  path.forEach((message, index) => {
    if (message.role !== "user") return;
    if (index === path.length - 1) {
      turns.push({ role: "user", content: message.content });
      return;
    }
    const answer = path[index + 1];
    if (answer?.role === "assistant" && answer.content?.trim() && (answer.status === "done" || answer.status === "stopped")) {
      turns.push({ role: "user", content: message.content }, { role: "assistant", content: answer.content });
    }
  });
  const bounded = boundedHistory(turns, { maxMessages: system ? MAX_MESSAGES - 1 : MAX_MESSAGES, maxBytes });
  if (!bounded.length || bounded[bounded.length - 1] !== turns[turns.length - 1]) return null;
  return {
    messages: system ? [{ role: "system", content: system }, ...bounded] : bounded,
    droppedPairs: Math.ceil((turns.length - bounded.length) / 2),
  };
}
