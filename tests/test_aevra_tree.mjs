import assert from "node:assert/strict";
import test from "node:test";
import { addNode, latestLeaf, pathTo, removeSubtree, siblings } from "../apps/harness/static/aevra/tree.js";

function node(id, parent, createdAt) {
  return { id, parent, children: [], role: parent ? "assistant" : "user", content: id, createdAt };
}

function sample() {
  const nodes = new Map();
  addNode(nodes, node("u1", null, 1));
  addNode(nodes, node("a1", "u1", 2));
  addNode(nodes, node("a1b", "u1", 3));
  addNode(nodes, node("u2", "a1b", 4));
  return nodes;
}

test("paths follow parents from the root", () => {
  const nodes = sample();
  assert.deepEqual(pathTo(nodes, "u2").map((item) => item.id), ["u1", "a1b", "u2"]);
  assert.deepEqual(pathTo(nodes, "missing"), []);
});

test("siblings and latest leaf support version navigation", () => {
  const nodes = sample();
  assert.deepEqual(siblings(nodes, "a1"), ["a1", "a1b"]);
  assert.deepEqual(siblings(nodes, "u1"), ["u1"]);
  assert.equal(latestLeaf(nodes, "u1"), "u2");
  assert.equal(latestLeaf(nodes, "a1"), "a1");
});

test("removing a branch returns the next visible leaf", () => {
  const nodes = sample();
  const { removed, next } = removeSubtree(nodes, "a1b");
  assert.deepEqual(removed.sort(), ["a1b", "u2"]);
  assert.equal(next, "a1");
  assert.deepEqual(nodes.get("u1").children, ["a1"]);
  const last = removeSubtree(nodes, "u1");
  assert.equal(last.next, null);
  assert.equal(nodes.size, 0);
});
