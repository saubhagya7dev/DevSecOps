/* Read-only renderer for the Markdown constructs emitted by our report writer.
 * Raw HTML and images are text, and links are restricted to public HTTPS URLs. */
(function (root) {
  'use strict';
  const escape = value => String(value).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const plain = text => escape(text.replace(/&(?:amp|lt|gt);/g, e => ({'&amp;':'&','&lt;':'<','&gt;':'>'}[e])));
  function safeLink(value) {
    try {
      const url = new URL(value);
      return url.protocol === 'https:' && !url.username && !url.password ? url.href : null;
    } catch { return null; }
  }
  function inline(text, depth = 0) {
    if (depth > 8) return plain(text);
    let result = '', i = 0;
    while (i < text.length) {
      const rest = text.slice(i);
      let match;
      if ((match = /^\\([\\`*_{}\[\]()#+!|>.-])/.exec(rest))) {
        result += plain(match[1]); i += match[0].length;
      } else if ((match = /^`([^`\n]+)`/.exec(rest))) {
        result += `<code>${plain(match[1])}</code>`; i += match[0].length;
      } else if ((match = /^\[([^\]\n]+)\]\(([^\s)]*)\)/.exec(rest))) {
        const url = safeLink(match[2]);
        result += url ? `<a href="${escape(url)}" target="_blank" rel="noopener noreferrer">${inline(match[1], depth + 1)}</a>` : inline(match[1], depth + 1);
        i += match[0].length;
      } else if ((match = /^(\*\*|__)([^\n]+?)\1/.exec(rest))) {
        result += `<strong>${inline(match[2], depth + 1)}</strong>`; i += match[0].length;
      } else if ((match = /^(\*|_)([^\n]+?)\1/.exec(rest))) {
        result += `<em>${inline(match[2], depth + 1)}</em>`; i += match[0].length;
      } else {
        const end = rest.search(/[\\`\[*_&<]/);
        const length = end > 0 ? end : 1;
        // Keep pre-escaped prose entities together; decode exactly once before escaping.
        const entity = /^&(?:amp|lt|gt);/.exec(rest);
        result += plain(entity ? entity[0] : rest.slice(0, length));
        i += entity ? entity[0].length : length;
      }
    }
    return result;
  }
  function render(markdown) {
    const lines = String(markdown).replace(/\r\n?/g, '\n').split('\n');
    let html = '', i = 0;
    const special = line => /^(?:#{1,6} |>|[-*+] |\d+\. |```|~~~|\s*$|---+$)/.test(line);
    while (i < lines.length) {
      const line = lines[i];
      let match;
      if (!line.trim()) { i++; continue; }
      if ((match = /^(#{1,6}) (.*)$/.exec(line))) {
        const level = match[1].length;
        html += `<h${level}>${inline(match[2])}</h${level}>`; i++; continue;
      }
      if ((match = /^(```|~~~)/.exec(line))) {
        const fence = match[1], body = []; i++;
        while (i < lines.length && !lines[i].startsWith(fence)) body.push(lines[i++]);
        if (i < lines.length) i++;
        html += `<pre><code>${escape(body.join('\n'))}</code></pre>`; continue;
      }
      if (/^---+$/.test(line)) { html += '<hr>'; i++; continue; }
      if (/^>/.test(line)) {
        const body = [];
        while (i < lines.length && /^>/.test(lines[i])) body.push(lines[i++].replace(/^> ?/, ''));
        html += `<blockquote><p>${inline(body.join('\n'))}</p></blockquote>`; continue;
      }
      if (/^(?:[-*+] |\d+\. )/.test(line)) {
        const ordered = /^\d+\./.test(line), tag = ordered ? 'ol' : 'ul';
        html += `<${tag}>`;
        while (i < lines.length && (ordered ? /^\d+\. / : /^[-*+] /).test(lines[i])) {
          let body = lines[i++].replace(/^(?:[-*+] |\d+\. )/, '');
          while (i < lines.length && /^ {2,}\S/.test(lines[i])) body += '\n' + lines[i++].trim();
          html += `<li>${inline(body)}</li>`;
        }
        html += `</${tag}>`; continue;
      }
      const body = [line]; i++;
      while (i < lines.length && !special(lines[i])) body.push(lines[i++]);
      html += `<p>${inline(body.join('\n'))}</p>`;
    }
    return html;
  }
  const api = {render};
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.ReportMarkdown = api;
})(typeof window !== 'undefined' ? window : globalThis);
