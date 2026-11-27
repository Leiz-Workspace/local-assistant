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
