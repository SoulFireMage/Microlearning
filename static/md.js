/* Shared by the app and the guide page: escaping and Markdown + KaTeX rendering. */
"use strict";

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

/* Markdown + KaTeX. Math is lifted out before Markdown parsing so that
   underscores and asterisks inside formulas survive, then rendered back in. */
function renderMd(src) {
  const math = [];
  const stash = (tex, display) => { math.push({ tex, display }); return `@@MATH${math.length - 1}@@`; };
  const parts = String(src || "").split(/(```[\s\S]*?```|`[^`\n]*`)/g);
  const prepped = parts.map((p, i) => {
    if (i % 2 === 1) return p; // code: untouched
    return p
      .replace(/\$\$([\s\S]+?)\$\$/g, (_, t) => stash(t, true))
      .replace(/\\\[([\s\S]+?)\\\]/g, (_, t) => stash(t, true))
      .replace(/\\\(([\s\S]+?)\\\)/g, (_, t) => stash(t, false))
      .replace(/(^|[^\\$])\$([^$\n]+?)\$(?!\d)/g, (_, pre, t) => pre + stash(t, false));
  }).join("");
  let html = DOMPurify.sanitize(marked.parse(prepped, { gfm: true, breaks: false }));
  html = html.replace(/@@MATH(\d+)@@/g, (_, i) => {
    const m = math[+i];
    try { return katex.renderToString(m.tex, { displayMode: m.display, throwOnError: false, strict: "ignore" }); }
    catch (_) { return esc(m.tex); }
  });
  return html;
}

function renderInline(src) {
  return renderMd(src).replace(/^\s*<p>([\s\S]*)<\/p>\s*$/, "$1");
}

