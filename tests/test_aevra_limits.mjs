import assert from "node:assert/strict";
import test from "node:test";
import {
  MAX_ATTACHMENTS_TOTAL,
  MAX_ATTACHMENT_BYTES,
  MAX_INLINE_PASTE_BYTES,
  PASTE_FILE_NAME,
  classifyOmitted,
  evidenceBytes,
  parsePasteThreshold,
  pastePlacement,
} from "../apps/harness/static/aevra/limits.js";

function file(name, length) {
  return { name, content: "x".repeat(length) };
}

/** A file whose evidence block is exactly `bytes` long. */
function fileOfBytes(name, bytes) {
  return file(name, bytes - evidenceBytes(name, ""));
}

test("attaches a long paste that fits every limit", () => {
  assert.equal(pastePlacement({ attachments: [], text: "a".repeat(5000) }), "attach");
});

test("pastes inline when four files are already attached", () => {
  const attachments = [1, 2, 3, 4].map((index) => file(`f${index}.txt`, 10));
  assert.equal(pastePlacement({ attachments, text: "a".repeat(5000) }), "inline");
});

test("pastes inline when the text is larger than one attachment allows", () => {
  assert.equal(pastePlacement({ attachments: [], text: "a".repeat(MAX_ATTACHMENT_BYTES) }), "inline");
});

test("pastes inline instead of dropping text that would exceed the attachment total", () => {
  const attachments = [1, 2, 3].map((index) => file(`f${index}.txt`, 61440));
  const text = "a".repeat(15000);
  assert.ok(evidenceBytes(PASTE_FILE_NAME, text) <= MAX_ATTACHMENT_BYTES);
  assert.equal(pastePlacement({ attachments, text }), "inline");
});

test("attaches when the total lands exactly on the limit, and not one byte over", () => {
  // Three files leave exactly 1000 bytes, well under the per-file limit, so only the total decides.
  const attachments = [fileOfBytes("a.txt", MAX_ATTACHMENT_BYTES), fileOfBytes("b.txt", MAX_ATTACHMENT_BYTES), fileOfBytes("c.txt", MAX_ATTACHMENTS_TOTAL - 2 * MAX_ATTACHMENT_BYTES - 1000)];
  const text = "a".repeat(1000 - evidenceBytes(PASTE_FILE_NAME, ""));
  assert.equal(evidenceBytes(PASTE_FILE_NAME, text), 1000);
  assert.equal(pastePlacement({ attachments, text }), "attach");
  assert.equal(pastePlacement({ attachments, text: `${text}a` }), "inline");
});

test("measures UTF-8 bytes, not characters", () => {
  const text = "ă".repeat(40000);
  assert.ok(text.length < MAX_ATTACHMENT_BYTES);
  assert.equal(pastePlacement({ attachments: [], text }), "inline");
});

test("refuses a paste that would make the message too large", () => {
  const draft = "d".repeat(MAX_INLINE_PASTE_BYTES - 10);
  assert.equal(pastePlacement({ attachments: [], text: "a".repeat(MAX_ATTACHMENT_BYTES), draft }), "refuse");
  assert.equal(pastePlacement({ attachments: [], text: "a".repeat(MAX_ATTACHMENT_BYTES), draft: "" }), "inline");
});

test("pastes whitespace inline because an empty file would be rejected", () => {
  assert.equal(pastePlacement({ attachments: [], text: " ".repeat(5000) }), "inline");
});

test("pastes text with a NUL character inline because a file with it would be rejected", () => {
  assert.equal(pastePlacement({ attachments: [], text: `${"a".repeat(5000)}\u0000` }), "inline");
});

test("counts a duplicate only when its first copy reached the model", () => {
  const attachments = [{ name: "a.txt", content: "same" }, { name: "a.txt", content: "same" }, { name: "b.txt", content: "big" }];
  const sentOnce = { included_evidence: [0], omitted_evidence: [{ index: 1, reason: "duplicate_evidence" }, { index: 2, reason: "token_budget" }] };
  assert.deepEqual(classifyOmitted(sentOnce, attachments), { omitted: 1, duplicates: 1 });
  const neverSent = { included_evidence: [2], omitted_evidence: [{ index: 0, reason: "token_budget" }, { index: 1, reason: "duplicate_evidence" }] };
  assert.deepEqual(classifyOmitted(neverSent, attachments), { omitted: 2, duplicates: 0 });
  assert.deepEqual(classifyOmitted(null, attachments), { omitted: 0, duplicates: 0 });
  assert.deepEqual(classifyOmitted({ omitted_evidence: [{ index: 9, reason: "duplicate_evidence" }] }, attachments), { omitted: 1, duplicates: 0 });
});

test("keeps the saved threshold for blank or invalid input", () => {
  for (const raw of ["", "   ", "abc", "-5", "12.5", "1e3", undefined, null]) {
    assert.equal(parsePasteThreshold(raw, 2500), 2500, String(raw));
  }
});

test("accepts an explicit zero and clamps large values", () => {
  assert.equal(parsePasteThreshold("0", 2500), 0);
  assert.equal(parsePasteThreshold(" 3000 ", 2500), 3000);
  assert.equal(parsePasteThreshold("150000", 2500), 100000);
});
