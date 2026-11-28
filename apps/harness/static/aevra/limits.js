/** Attachment and paste limits shared by the composer and settings; no DOM access, so Node tests can import it. */
export const MAX_ATTACHMENTS = 4;
// Byte limits mirror the server: each file's evidence ("Attached file: name" header plus text) and the total.
export const MAX_ATTACHMENT_BYTES = 65536;
export const MAX_ATTACHMENTS_TOTAL = 196608;
export const MAX_INLINE_PASTE_BYTES = 200000;
export const MAX_PASTE_THRESHOLD = 100000;
export const PASTE_FILE_NAME = "van-ban-dan.txt";

const encoder = new TextEncoder();

export function evidenceBytes(name, text) {
  return encoder.encode(`Attached file: ${name}\n\n${text}`).length;
}

export function attachedBytes(attachments) {
  return attachments.reduce((sum, attachment) => sum + evidenceBytes(attachment.name, attachment.content), 0);
}

/**
 * Decide where a long paste goes: "attach" when it fits every attachment limit, otherwise "inline"
 * when the message stays within MAX_INLINE_PASTE_BYTES, otherwise "refuse".
 */
export function pastePlacement({ attachments, text, draft = "" }) {
  const bytes = evidenceBytes(PASTE_FILE_NAME, text);
  const attachable = text.trim().length > 0
    && !text.includes("\u0000")
    && attachments.length < MAX_ATTACHMENTS
    && bytes <= MAX_ATTACHMENT_BYTES
    && attachedBytes(attachments) + bytes <= MAX_ATTACHMENTS_TOTAL;
  if (attachable) return "attach";
  return encoder.encode(draft + text).length <= MAX_INLINE_PASTE_BYTES ? "inline" : "refuse";
}

/** Read the paste-to-file threshold field: blank or invalid input keeps the current value; only an explicit 0 turns it off. */
export function parsePasteThreshold(raw, current) {
  const text = String(raw ?? "").trim();
  if (!/^\d+$/.test(text)) return current;
  return Math.min(MAX_PASTE_THRESHOLD, Number(text));
}

/**
 * Split the server's omitted attachments into ones the model never saw and duplicates whose identical
 * earlier copy was included. Evidence indices follow the order of the request's attachments.
 */
export function classifyOmitted(context, attachments) {
  const omittedEvidence = Array.isArray(context?.omitted_evidence) ? context.omitted_evidence : [];
  const included = new Set(Array.isArray(context?.included_evidence) ? context.included_evidence : []);
  let duplicates = 0;
  for (const entry of omittedEvidence) {
    const current = attachments[entry?.index];
    const first = entry?.reason === "duplicate_evidence" && current
      ? attachments.findIndex((item) => item.name === current.name && item.content === current.content)
      : -1;
    if (first !== -1 && first < entry.index && included.has(first)) duplicates += 1;
  }
  return { omitted: omittedEvidence.length - duplicates, duplicates };
}
