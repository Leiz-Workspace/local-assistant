/** Render an escaped Markdown subset (GFM-like) for assistant replies; no raw HTML ever passes through. */
export function esc(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "\"": "&quot;", "'": "&#39;" }[char]));
}

const FENCE_OPEN = /^ {0,3}(`{3,}|~{3,})[ \t]*([\w+#.-]{0,24})[ \t]*$/;
const LIST_ITEM = /^( *)([-*+]|\d{1,9}[.)])[ \t]+(.*)$/;
const TABLE_DELIMITER = /^ *\|? *:?-+:? *(\| *:?-+:? *)*\|? *$/;
const RULE = /^ {0,3}([-*_])( *\1){2,} *$/;
const MAX_DEPTH = 6;

const LINK = /\[([^\]\n]+)\]\(((?:https?:\/\/|mailto:)(?:[^\s()]|\([^\s()]*\))+)\)/g;

function emphasis(escaped) {
  // Links are lifted out first so emphasis can never rewrite inside an href.
  const links = [];
  const text = escaped.replace(//g, "").replace(LINK, (_, label, url) => {
    links.push([label, url]);
    return `${links.length - 1}`;
  });
  return styles(text).replace(/(\d+)/g, (_, index) => `<a href="${links[index][1]}" target="_blank" rel="noopener noreferrer">${styles(links[index][0])}</a>`);
}

function styles(escaped) {
  return escaped
    .replace(/\*\*([^*\n]+)\*\*/g, "<strong>$1</strong>")
    .replace(/(^|[^\w])__([^_\n]+)__(?!\w)/g, "$1<strong>$2</strong>")
    .replace(/~~([^~\n]+)~~/g, "<del>$1</del>")
    .replace(/(^|[^*\w])\*(\S(?:[^*\n]*\S)?)\*(?!\w)/g, "$1<em>$2</em>")
    .replace(/(^|[^\w])_(\S(?:[^_\n]*\S)?)_(?!\w)/g, "$1<em>$2</em>");
}

function inline(text) {
  // Code spans become placeholders first, so emphasis may wrap them but never applies inside them.
  const spans = [];
  const masked = esc(text).replace(/\uE001/g, "").replace(/`([^`\n]+)`/g, (_, code) => {
    spans.push(code);
    return `\uE001${spans.length - 1}\uE001`;
  });
  return emphasis(masked).replace(/\uE001(\d+)\uE001/g, (_, index) => `<code>${spans[index]}</code>`);
}

function itemText(lines) {
  const task = lines[0].match(/^\[( |x|X)\][ \t]+(.*)$/);
  if (!task) return lines.map(inline).join("<br>");
  const box = `<input type="checkbox" disabled${task[1] === " " ? "" : " checked"} aria-label="${task[1] === " " ? "Chưa xong" : "Đã xong"}">`;
  return `${box} ${[task[2], ...lines.slice(1)].map(inline).join("<br>")}`;
}

function splitRow(line) {
  let row = line.trim();
  if (row.startsWith("|")) row = row.slice(1);
  if (row.endsWith("|") && !row.endsWith("\\|")) row = row.slice(0, -1);
  return row.split(/(?<!\\)\|/).map((cell) => cell.trim().replace(/\\\|/g, "|"));
}

function table(header, delimiter, rows) {
  const align = splitRow(delimiter).map((cell) => (cell.startsWith(":") && cell.endsWith(":") ? "center" : cell.endsWith(":") ? "right" : cell.startsWith(":") ? "left" : ""));
  const cell = (tag, value, index) => `<${tag}${align[index] ? ` style="text-align:${align[index]}"` : ""}>${inline(value)}</${tag}>`;
  const head = splitRow(header);
  const body = rows.map((row) => {
    const cells = splitRow(row);
    return `<tr>${head.map((_, index) => cell("td", cells[index] ?? "", index)).join("")}</tr>`;
  }).join("");
  return `<div class="table-wrap"><table><thead><tr>${head.map((value, index) => cell("th", value, index)).join("")}</tr></thead>${body ? `<tbody>${body}</tbody>` : ""}</table></div>`;
}

function listHtml(items, depth) {
  // items: [{indent, ordered, start, text: [lines]}] at one nesting level, children nested by indent.
  let html = "";
  let index = 0;
  while (index < items.length) {
    const first = items[index];
    const tag = first.ordered ? "ol" : "ul";
    const start = first.ordered && first.start !== 1 ? ` start="${first.start}"` : "";
    let body = "";
    while (index < items.length && items[index].indent === first.indent && items[index].ordered === first.ordered) {
      const item = items[index];
      index += 1;
      const children = [];
      while (index < items.length && items[index].indent > first.indent) children.push(items[index++]);
      const nested = children.length && depth < MAX_DEPTH ? listHtml(children, depth + 1) : "";
      body += `<li${/^\[( |x|X)\][ \t]/.test(item.text[0]) ? ' class="task"' : ""}>${itemText(item.text)}${item.blocks || ""}${nested}</li>`;
    }
    html += `<${tag}${start}>${body}</${tag}>`;
  }
  return html;
}

function blocks(lines, depth) {
  let html = "";
  let paragraph = [];
  let list = [];
  const flushParagraph = () => {
    if (paragraph.length) html += `<p>${paragraph.map(inline).join("<br>")}</p>`;
    paragraph = [];
  };
  const flushList = () => {
    if (list.length) html += listHtml(list, depth);
    list = [];
  };
  const flush = () => {
    flushParagraph();
    flushList();
  };
  let index = 0;
  while (index < lines.length) {
    const line = lines[index];
    const indent = line.match(/^ */)[0].length;
    const current = list[list.length - 1];
    if (current && indent > current.indent && FENCE_OPEN.test(line.trimStart())) {
      // A fence indented under a list item belongs to that item; its body loses the item's indent.
      const [, marker, language] = line.trimStart().match(FENCE_OPEN);
      const closing = new RegExp(`^${marker[0] === "`" ? "`" : "~"}{${marker.length},}[ \\t]*$`);
      const code = [];
      index += 1;
      while (index < lines.length && !closing.test(lines[index].trimStart())) code.push(lines[index++].replace(new RegExp(`^ {0,${indent}}`), ""));
      index += 1;
      current.blocks = (current.blocks || "") + `<pre>${language ? `<span class="code-lang">${esc(language)}</span>` : ""}<code>${esc(code.join("\n"))}</code></pre>`;
      continue;
    }
    const fence = line.match(FENCE_OPEN);
    if (fence) {
      flush();
      const [, marker, language] = fence;
      const closing = new RegExp(`^ {0,3}${marker[0] === "`" ? "`" : "~"}{${marker.length},}[ \\t]*$`);
      const code = [];
      index += 1;
      while (index < lines.length && !closing.test(lines[index])) code.push(lines[index++]);
      index += 1;
      const label = language ? `<span class="code-lang">${esc(language)}</span>` : "";
      html += `<pre>${label}<code>${esc(code.join("\n"))}</code></pre>`;
      continue;
    }
    if (!line.trim()) {
      flush();
      index += 1;
      continue;
    }
    if (line.includes("|") && index + 1 < lines.length && lines[index + 1].includes("|") && TABLE_DELIMITER.test(lines[index + 1])) {
      flush();
      const header = line;
      const delimiter = lines[index + 1];
      const rows = [];
      index += 2;
      while (index < lines.length && lines[index].trim() && lines[index].includes("|")) rows.push(lines[index++]);
      html += table(header, delimiter, rows);
      continue;
    }
    if (RULE.test(line)) {
      flush();
      html += "<hr>";
      index += 1;
      continue;
    }
    const heading = line.match(/^ {0,3}(#{1,6})[ \t]+(.*?)[ \t#]*$/);
    if (heading) {
      flush();
      const level = Math.min(heading[1].length + 2, 6);
      html += `<h${level}>${inline(heading[2])}</h${level}>`;
      index += 1;
      continue;
    }
    if (/^ {0,3}>/.test(line)) {
      flush();
      const quoted = [];
      while (index < lines.length && /^ {0,3}>/.test(lines[index])) quoted.push(lines[index++].replace(/^ {0,3}> ?/, ""));
      html += `<blockquote>${depth < MAX_DEPTH ? blocks(quoted, depth + 1) : `<p>${quoted.map(inline).join("<br>")}</p>`}</blockquote>`;
      continue;
    }
    const item = line.match(LIST_ITEM);
    if (item) {
      flushParagraph();
      const ordered = /\d/.test(item[2]);
      list.push({ indent: item[1].length, ordered, start: ordered ? Number.parseInt(item[2], 10) : 1, text: [item[3]] });
      index += 1;
      continue;
    }
    if (list.length && /^ {2,}\S/.test(line)) {
      list[list.length - 1].text.push(line.trim());
      index += 1;
      continue;
    }
    flushList();
    paragraph.push(line);
    index += 1;
  }
  flush();
  return html;
}

export function renderMarkdown(text) {
  return blocks(String(text ?? "").replace(/\r\n?/g, "\n").split("\n"), 0);
}
