import assert from "node:assert/strict";
import test from "node:test";
import { esc, renderMarkdown } from "../apps/harness/static/aevra/markdown.js";

test("renders the supported Markdown subset", () => {
  const html = renderMarkdown("**Xin chào!** `code`\n\n- một\n- *hai*\n\n1. đầu\n\n## Tiêu đề\n\n```python\nprint('aevra')\n```");
  assert.match(html, /<strong>Xin chào!<\/strong> <code>code<\/code>/);
  assert.match(html, /<ul><li>một<\/li><li><em>hai<\/em><\/li><\/ul>/);
  assert.match(html, /<ol><li>đầu<\/li><\/ol>/);
  assert.match(html, /<h4>Tiêu đề<\/h4>/);
  assert.match(html, /<pre><span class="code-lang">python<\/span><code>print\(&#39;aevra&#39;\)<\/code><\/pre>/);
});

test("escapes every model-controlled value", () => {
  const html = renderMarkdown("<img src=x onerror=alert(1)> **<script>x</script>** `<b>`\n```\n\"><svg onload=1>\n</pre><script>\n```\n[x](javascript:alert(1)) [y](https://e.com/\"onmouseover=1)");
  assert.doesNotMatch(html, /<img|<script|<svg|<b>|<\/pre><script|href="javascript|" onmouseover/i);
  assert.match(html, /href="https:\/\/e\.com\/&quot;onmouseover=1"/);
  assert.equal(esc(`<a href="x">'&`), "&lt;a href=&quot;x&quot;&gt;&#39;&amp;");
});

test("leaves arithmetic and identifiers alone", () => {
  assert.equal(renderMarkdown("2 * 3 * 4"), "<p>2 * 3 * 4</p>");
  assert.equal(renderMarkdown("snake_case and a*b*c"), "<p>snake_case and a*b*c</p>");
  assert.equal(renderMarkdown(""), "");
});

test("keeps emphasis out of inline code and links", () => {
  assert.equal(renderMarkdown("Chạy `*.py` và `**/*.js` rồi *xong*"), "<p>Chạy <code>*.py</code> và <code>**/*.js</code> rồi <em>xong</em></p>");
  assert.equal(renderMarkdown("[tài liệu](https://example.com/_x_/a*b*)"), '<p><a href="https://example.com/_x_/a*b*" target="_blank" rel="noopener noreferrer">tài liệu</a></p>');
});

test("keeps ordered list numbering and continuation lines", () => {
  const html = renderMarkdown("1. Cài đặt\n   chạy lệnh\n\n2. Kiểm tra");
  assert.match(html, /<ol><li>Cài đặt<br>chạy lệnh<\/li><\/ol><ol start="2"><li>Kiểm tra<\/li><\/ol>/);
});

test("renders tables, quotes, nested lists, rules and strikethrough", () => {
  const html = renderMarkdown("| A | B |\n|:--|--:|\n| 1 | **2** |\n\n> trích dẫn\n> > lồng\n\n- a\n  - b\n    - c\n\n---\n\n~~bỏ~~ __đậm__ _nghiêng_");
  assert.match(html, /<table><thead><tr><th style="text-align:left">A<\/th><th style="text-align:right">B<\/th><\/tr><\/thead><tbody><tr><td style="text-align:left">1<\/td><td style="text-align:right"><strong>2<\/strong><\/td><\/tr><\/tbody><\/table>/);
  assert.match(html, /<blockquote><p>trích dẫn<\/p><blockquote><p>lồng<\/p><\/blockquote><\/blockquote>/);
  assert.match(html, /<ul><li>a<ul><li>b<ul><li>c<\/li><\/ul><\/li><\/ul><\/li><\/ul>/);
  assert.match(html, /<hr>/);
  assert.match(html, /<del>bỏ<\/del> <strong>đậm<\/strong> <em>nghiêng<\/em>/);
});

test("fences open only on their own line and stay open while streaming", () => {
  assert.equal(renderMarkdown("Dùng ``` để mở khối code, rồi viết tiếp.\n\nĐoạn sau **đậm**."), "<p>Dùng ``` để mở khối code, rồi viết tiếp.</p><p>Đoạn sau <strong>đậm</strong>.</p>");
  assert.equal(renderMarkdown("~~~js\nlet a = 1;\n~~~"), '<pre><span class="code-lang">js</span><code>let a = 1;</code></pre>');
  assert.equal(renderMarkdown("```\npartial"), "<pre><code>partial</code></pre>");
});

test("handles task lists, code inside emphasis and lists, and links with parentheses", () => {
  assert.match(renderMarkdown("- [ ] việc\n- [x] xong"), /<li class="task"><input type="checkbox" disabled aria-label="Chưa xong"> việc<\/li><li class="task"><input type="checkbox" disabled checked aria-label="Đã xong"> xong<\/li>/);
  assert.equal(renderMarkdown("**`code` đậm**"), "<p><strong><code>code</code> đậm</strong></p>");
  assert.match(renderMarkdown("[wiki](https://vi.wikipedia.org/wiki/A_(b))"), /href="https:\/\/vi\.wikipedia\.org\/wiki\/A_\(b\)"/);
  const list = renderMarkdown("1. Cài:\n   ```bash\n   uv sync\n   ```\n2. Chạy");
  assert.match(list, /<li>Cài:<pre><span class="code-lang">bash<\/span><code>uv sync<\/code><\/pre><\/li><li>Chạy<\/li>/);
});
