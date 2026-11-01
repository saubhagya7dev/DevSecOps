const {test} = require('node:test');
const assert = require('node:assert/strict');
const {render} = require('../web/markdown.js');

test('report headings, formatting, evidence quotes, and lists become readable HTML', () => {
  const html = render('# Review\n\n## Evidence\n\n**Action:** check `config.py`\n\n- One\n- Two\n\n> cited passage\n> continued');
  assert.match(html, /<h1>Review<\/h1>/);
  assert.match(html, /<h2>Evidence<\/h2>/);
  assert.match(html, /<strong>Action:<\/strong> check <code>config.py<\/code>/);
  assert.match(html, /<ul><li>One<\/li><li>Two<\/li><\/ul>/);
  assert.match(html, /<blockquote><p>cited passage\ncontinued<\/p><\/blockquote>/);
});
test('backend escaped prose is displayed literally without becoming formatting or HTML', () => {
  const html = render('Config &amp; Loader \\(safe\\) &lt;script&gt; \\*literal\\*');
  assert.match(html, /Config &amp; Loader \(safe\) &lt;script&gt; \*literal\*/);
  assert.doesNotMatch(html, /<script|<em>/);
});
test('raw HTML, event handlers, and executable or credential-bearing links stay inert', () => {
  const html = render('<img src=x onerror=alert(1)>\n\n[x](javascript:alert) [data](data:text/html,test) [key](https://user:secret@example.com)\n\n[valid](https://example.com/?a=1&b=2)');
  assert.doesNotMatch(html, /<img|href="(?:javascript|data)|user:secret/);
  assert.match(html, /&lt;img/);
  assert.match(html, /href="https:\/\/example.com\/\?a=1&amp;b=2"/);
  assert.match(html, /rel="noopener noreferrer"/);
});
test('code fences preserve literal Markdown and HTML and ordered lists retain structure', () => {
  const html = render('```html\n<script>**literal**</script>\n```\n\n1. First\n2. Second');
  assert.match(html, /<pre><code>&lt;script&gt;\*\*literal\*\*&lt;\/script&gt;<\/code><\/pre>/);
  assert.match(html, /<ol><li>First<\/li><li>Second<\/li><\/ol>/);
});
