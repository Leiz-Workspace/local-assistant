/** Pure helpers for the branching message tree of one conversation. */

export function addNode(nodes, node) {
  nodes.set(node.id, { ...node, children: [...(node.children || [])] });
  if (node.parent) {
    const parent = nodes.get(node.parent);
    if (parent && !parent.children.includes(node.id)) parent.children = [...parent.children, node.id];
  }
  return nodes;
}

export function roots(nodes) {
  return [...nodes.values()].filter((node) => !node.parent).sort((a, b) => a.createdAt - b.createdAt).map((node) => node.id);
}

export function siblings(nodes, id) {
  const node = nodes.get(id);
  if (!node) return [];
  return node.parent ? [...(nodes.get(node.parent)?.children || [])] : roots(nodes);
}

export function latestLeaf(nodes, id) {
  const seen = new Set();
  let current = nodes.get(id);
  while (current && current.children.length && !seen.has(current.id)) {
    seen.add(current.id);
    current = nodes.get(current.children[current.children.length - 1]) || current;
    if (seen.has(current.id)) break;
  }
  return current ? current.id : null;
}

export function pathTo(nodes, leafId) {
  const path = [];
  const seen = new Set();
  let current = leafId ? nodes.get(leafId) : null;
  while (current && !seen.has(current.id)) {
    seen.add(current.id);
    path.unshift(current);
    current = current.parent ? nodes.get(current.parent) : null;
  }
  return path;
}

export function subtree(nodes, id) {
  const ids = [];
  const stack = [id];
  const seen = new Set();
  while (stack.length) {
    const current = nodes.get(stack.pop());
    if (!current || seen.has(current.id)) continue;
    seen.add(current.id);
    ids.push(current.id);
    stack.push(...current.children);
  }
  return ids;
}

/** Remove a node and its descendants; return the removed ids and the node to show next. */
export function removeSubtree(nodes, id) {
  const node = nodes.get(id);
  if (!node) return { removed: [], next: null };
  const removed = subtree(nodes, id);
  const parentId = node.parent;
  removed.forEach((key) => nodes.delete(key));
  if (parentId && nodes.has(parentId)) {
    const parent = nodes.get(parentId);
    parent.children = parent.children.filter((key) => key !== id);
    const next = parent.children.length ? latestLeaf(nodes, parent.children[parent.children.length - 1]) : parentId;
    return { removed, next };
  }
  const remaining = roots(nodes);
  return { removed, next: remaining.length ? latestLeaf(nodes, remaining[remaining.length - 1]) : null };
}
