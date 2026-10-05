/* Thread-Resilient Learning Engine: single-page client (no build step). */
"use strict";

const $ = (sel, el = document) => el.querySelector(sel);
const view = $("#view");
const modalRoot = $("#modal-root");

const LEVELS = [
  { level: 0, label: "L0", hint: "30s" },
  { level: 1, label: "L1", hint: "3m" },
  { level: 2, label: "L2", hint: "deep" },
];
const LENSES = [
  { lens: "core", label: "Core" },
  { lens: "pattern", label: "Pattern" },
  { lens: "steps", label: "Steps" },
];
const REL_LABELS = {
  REQUIRES: "requires", EXTENDS: "builds on", ANALOGOUS_TO: "is analogous to", CONTRASTS_WITH: "contrasts with",
};

const app = { meta: null, thread: null, unit: null, depth: 0, lens: "core", units: null };

/* ------------------------------------------------------------ utilities */

async function api(path, opts = {}) {
  const init = { method: opts.method || (opts.body ? "POST" : "GET"), headers: {} };
  if (opts.body !== undefined) {
    init.headers["Content-Type"] = "application/json";
    init.body = JSON.stringify(opts.body);
  }
  const res = await fetch(path, init);
  if (res.status === 401) { location.href = "/login"; throw new Error("auth"); }
  if (!res.ok) {
    let msg = res.statusText;
    try { msg = (await res.json()).detail || msg; } catch (_) {}
    throw new Error(typeof msg === "string" ? msg : JSON.stringify(msg));
  }
  return res.status === 204 ? null : res.json();
}

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function h(html) {
  const t = document.createElement("template");
  t.innerHTML = html.trim();
  return t.content.firstElementChild;
}

let toastTimer;
function toast(msg) {
  const t = $("#toast");
  t.textContent = msg;
  t.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => t.classList.remove("show"), 2600);
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

function fmtTime(sec) {
  if (!sec) return "";
  return sec < 60 ? `${sec}s` : `${Math.round(sec / 60)}m`;
}

/* --------------------------------------------------------------- modals */

function openModal(inner, { onClose, cls = "" } = {}) {
  closeModal();
  const bd = h(`<div class="backdrop"><div class="modal ${cls}" role="dialog" aria-modal="true"></div></div>`);
  const m = bd.firstElementChild;
  if (typeof inner === "string") m.innerHTML = inner; else m.appendChild(inner);
  bd.addEventListener("mousedown", (e) => { if (e.target === bd) closeModal(); });
  bd._onClose = onClose;
  modalRoot.appendChild(bd);
  const f = m.querySelector("[autofocus], input, textarea, select, button");
  if (f) setTimeout(() => f.focus(), 20);
  return m;
}

function closeModal() {
  const bd = modalRoot.firstElementChild;
  if (!bd) return;
  modalRoot.innerHTML = "";
  if (bd._onClose) bd._onClose();
}

document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && modalRoot.firstElementChild) { closeModal(); return; }
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
    e.preventDefault();
    if (app.thread && location.hash.startsWith("#/t/")) pinModal();
    else toast("Open a thread to drop a pin into it.");
  }
});

/* --------------------------------------------------------------- router */

async function route() {
  closeModal();
  const hash = location.hash || "#/";
  const [, name, id] = hash.split("/");
  document.querySelectorAll("[data-nav]").forEach((a) =>
    a.classList.toggle("active", a.dataset.nav === (name || "home")));
  document.body.classList.toggle("focus", name === "t");
  $("#pin-fab").hidden = name !== "t";
  window.scrollTo(0, 0);
  try {
    if (name === "t" && id) await showThread(id);
    else if (name === "atlas") await showAtlas();
    else if (name === "resurface") await showResurface();
    else await showHome();
  } catch (err) {
    view.innerHTML = `<div class="empty"><h2>Something went wrong</h2><p>${esc(err.message)}</p><a href="#/">Back to threads</a></div>`;
  }
}
window.addEventListener("hashchange", route);

/* ----------------------------------------------------------------- home */

function threadCard(t, parked) {
  const el = h(`<div class="card ${parked ? "parked" : ""}" tabindex="0" role="button">
    <div style="display:flex;justify-content:space-between;gap:8px;align-items:start">
      <h3>${esc(t.title)}</h3>
      <span class="chip ${parked ? "parked" : t.status}">${parked ? "parked" : t.status.toLowerCase()}</span>
    </div>
    ${t.current_unit_title ? `<div class="sub">at <b>${esc(t.current_unit_title)}</b> · ${t.unit_count} unit${t.unit_count === 1 ? "" : "s"}</div>` : ""}
    ${t.parent_title ? `<div class="sub">↳ branched from ${esc(t.parent_title)}</div>` : ""}
    ${t.last_pin ? `<div class="pin">${esc(t.last_pin)}</div>` : ""}
  </div>`);
  const go = () => openThread(t.id);
  el.addEventListener("click", go);
  el.addEventListener("keydown", (e) => { if (e.key === "Enter") go(); });
  return el;
}

async function showHome() {
  const [threads, m] = await Promise.all([api("/api/threads"), api("/api/metrics")]);
  app.thread = null;
  const groups = { ACTIVE: [], PAUSED: [], PARKED: [], NEW: [], RESOLVED: [] };
  for (const t of threads) {
    if (t.status === "DORMANT" || (t.status === "PAUSED" && t.primer_pending)) groups.PARKED.push(t);
    else groups[t.status].push(t);
  }
  view.innerHTML = "";
  const metrics = h(`<div class="metrics mono"></div>`);
  metrics.innerHTML = m.dormant_counted
    ? `<span>resumption <b>${m.dormant_reactivated}/${m.dormant_counted}</b> parked threads picked back up</span>` +
      (m.median_days_parked_before_return != null ? `<span>median parked <b>${m.median_days_parked_before_return.toFixed(1)}d</b> before return</span>` : "")
    : `<span>no thread has been parked yet</span>`;
  metrics.innerHTML += `<span><b>${m.units}</b> concepts in the atlas</span>` +
    (m.recall_ready ? `<span><a href="#/resurface"><b>${m.recall_ready}</b> ready to resurface</a></span>` : "");
  view.appendChild(metrics);
  if (app.meta && app.meta.persistent === false) {
    view.appendChild(h(`<div class="warn-bar">Storage is ephemeral (<code>${esc(app.meta.db_path)}</code>). Fine for local dev; on a Space, attach a Storage Bucket at <code>/data</code> or threads vanish on restart. <a href="/api/export">Export JSON</a></div>`));
  }

  if (!threads.length) {
    const units = await api("/api/units");
    const empty = h(`<div class="empty"><h2>No threads yet</h2>
      <p>A thread is one line of curiosity. Start anywhere; branch whenever something tugs at you. Nothing here expires and nothing counts streaks.</p>
      <div class="starters"></div></div>`);
    for (const u of units.slice(0, 8)) {
      const b = h(`<button class="ghost">${esc(u.title)}</button>`);
      b.onclick = () => startThread(u.title, u.id);
      $(".starters", empty).appendChild(b);
    }
    view.appendChild(empty);
    return;
  }

  const section = (key, title, hint, parked = false) => {
    if (!groups[key].length) return;
    view.appendChild(h(`<div class="section-h"><h2>${title}</h2><span class="hint">${hint}</span></div>`));
    const grid = h(`<div class="grid"></div>`);
    groups[key].forEach((t) => grid.appendChild(threadCard(t, parked)));
    view.appendChild(grid);
  };
  section("ACTIVE", "Active", `at most ${app.meta?.max_active ?? 2} at a time`);
  section("PAUSED", "Paused", "checkpointed; pick up instantly");
  section("PARKED", "Parked", "safely stored; opening one gives you a 30-second reload first", true);
  section("NEW", "Not started", "");
  if (groups.RESOLVED.length) {
    const d = h(`<details class="resolved"><summary>Resolved (${groups.RESOLVED.length})</summary><div class="grid"></div></details>`);
    groups.RESOLVED.forEach((t) => $(".grid", d).appendChild(threadCard(t, false)));
    view.appendChild(d);
  }
}

async function openThread(id) {
  const r = await api(`/api/threads/${id}/open`, { method: "POST" });
  if (r.needs_primer) showPrimer(r.thread, r.primer);
  else location.hash = `#/t/${id}`;
}

/* --------------------------------------------------------------- primer */

function showPrimer(thread, primer) {
  const m = openModal(`
    <div class="primer">
      <div class="tag">Re-entry · ${esc(thread.title)}</div>
      <div class="anchor"><div class="tag">The problem you were solving</div>${renderMd(primer.anchor_summary)}</div>
      ${primer.consolidated_points.length ? `<div class="tag">What you locked down</div>
        <ul class="locked">${primer.consolidated_points.map((p) => `<li>${renderInline(p)}</li>`).join("")}</ul>` : ""}
      <div class="edge"><div class="tag">Where you froze / open question</div>${renderMd(primer.open_question)}</div>
      <button class="go">Jump back in${primer.recommended_unit_title ? ` at ${esc(primer.recommended_unit_title)}` : ""} →</button>
      <div class="foot"><span>${primer.origin === "synthesised" ? "synthesised by LLM from your trail" : "built directly from your trail (no LLM)"}</span>
        <button class="link refresh">regenerate</button></div>
    </div>`, { cls: "primer-modal" });
  $(".go", m).onclick = async () => {
    await api(`/api/threads/${thread.id}/resume`, { method: "POST" });
    closeModal();
    const target = `#/t/${thread.id}`;
    if (location.hash === target) route(); else location.hash = target;
  };
  $(".refresh", m).onclick = async (e) => {
    e.target.disabled = true; e.target.textContent = "regenerating…";
    const p = await api(`/api/threads/${thread.id}/primer?refresh=true`);
    showPrimer(thread, p);
  };
}

/* --------------------------------------------------------------- reader */

async function showThread(id) {
  const opened = await api(`/api/threads/${id}/open`, { method: "POST" });
  if (opened.needs_primer) {
    location.hash = "#/";
    setTimeout(() => showPrimer(opened.thread, opened.primer), 50);
    return;
  }
  app.thread = opened.thread;
  if (!app.thread.current_unit_id) {
    renderNoUnit();
    return;
  }
  await loadUnit(app.thread.current_unit_id, app.thread.current_depth || 0, app.thread.current_lens || "core");
}

function renderNoUnit() {
  view.innerHTML = "";
  const box = h(`<div class="reader"><div class="empty"><h2>${esc(app.thread.title)}</h2>
    <p>This thread has no concept yet. Name one to start from.</p>
    <input id="concept" placeholder="e.g. Jacobian, Lagrange multipliers, Hopfield networks">
    <div class="btn-row"><button id="go">Start</button></div></div></div>`);
  $("#go", box).onclick = async () => {
    const c = $("#concept", box).value.trim();
    if (!c) return;
    const units = await api(`/api/units?q=${encodeURIComponent(c)}`);
    const match = units.find((u) => u.title.toLowerCase() === c.toLowerCase());
    const unit = match || (await api("/api/units", { body: { title: c, domain: "Unsorted" } }));
    await exploreHere(unit.id);
  };
  view.appendChild(box);
}

async function loadUnit(unitId, depth, lens) {
  app.depth = depth;
  app.lens = lens;
  app.unit = await api(`/api/units/${unitId}`);
  if (app.thread.status !== "RESOLVED") await saveProgress({}); // visiting counts
  app.thread = await api(`/api/threads/${app.thread.id}`);
  renderReader();
}

function layerFor(level, lens) {
  return app.unit.layers.find((l) => l.depth_level === level && l.lens === lens);
}

async function saveProgress(extra) {
  if (!app.thread || app.thread.status === "RESOLVED") return null;
  return api(`/api/threads/${app.thread.id}/progress`, {
    body: { unit_id: app.unit.id, depth: app.depth, lens: app.lens, ...extra },
  });
}

function renderReader() {
  const t = app.thread, u = app.unit;
  const prog = t.progress.find((p) => p.unit_id === u.id);
  const resolved = t.status === "RESOLVED";
  view.innerHTML = "";
  const r = h(`<div class="reader">
    <div class="crumbs">
      <a href="#/">← threads</a>
      <span>${esc(t.title)}</span>
      <span class="chip ${t.status}">${t.status.toLowerCase()}</span>
      ${t.parent ? `<span>↳ from <a href="#" data-open="${t.parent.id}">${esc(t.parent.title)}</a></span>` : ""}
      <span class="spacer"></span>
      ${resolved
        ? `<button class="ghost" id="reopen">Reopen</button>`
        : `<button class="ghost" id="branch" title="Spawn a child thread from here">⑂ Branch</button>
           <button class="ghost" id="pause">Pause</button>
           <button class="ghost" id="resolve" title="Mark the curiosity satisfied">Resolve</button>`}
    </div>
    <div class="trail"></div>
    <div class="unit-head">
      <div class="meta">${esc(u.domain)}</div>
      <h1>${esc(u.title)}</h1>
    </div>
    <div class="switches">
      <div class="seg" id="depth" role="tablist" aria-label="Depth"></div>
      <div class="seg" id="lens" role="tablist" aria-label="Lens"></div>
    </div>
    <div class="provenance" id="prov"></div>
    <div class="content" id="content"></div>
    <div class="mark-row">
      ${resolved ? "" : `
      <button class="ghost ${prog?.user_status === "CONSOLIDATED" ? "on-CONSOLIDATED" : ""}" id="mark-ok" title="You could explain this to someone">✓ Locked in</button>
      <button class="ghost ${prog?.user_status === "STUCK" ? "on-STUCK" : ""}" id="mark-stuck" title="Flag friction; primers will bring you back here">⚑ Stuck here</button>
      <button class="ghost" id="pin-inline">📌 Pin a thought <span class="kbd">Ctrl K</span></button>`}
    </div>
    <div class="panel" id="probe-panel"></div>
    <div class="panel"><h4>Connections</h4><div class="rel-grid" id="rels"></div></div>
    <div class="panel" id="sources-panel"></div>
    <div class="panel" id="family-panel"></div>
  </div>`);
  view.appendChild(r);

  // trail of units visited in this thread
  const trail = $(".trail", r);
  t.progress.forEach((p) => {
    const st = p.user_status === "CONSOLIDATED" ? "✓" : p.user_status === "STUCK" ? "⚑" : "";
    const b = h(`<button class="${p.unit_id === u.id ? "here" : ""}">${esc(p.unit_title)}${st ? `<span class="st">${st}</span>` : ""}</button>`);
    b.onclick = () => loadUnit(p.unit_id, 0, "core");
    trail.appendChild(b);
  });
  if (t.progress.length < 2) trail.remove();

  // switches
  const depthSeg = $("#depth", r);
  LEVELS.forEach(({ level, label, hint }) => {
    const any = app.unit.layers.find((l) => l.depth_level === level);
    const core = layerFor(level, "core");
    const b = h(`<button role="tab" class="${app.depth === level ? "on" : ""}"><span class="${any ? "" : "missing"}">${label} · ${core ? fmtTime(core.read_time_seconds) || hint : hint}</span></button>`);
    b.onclick = () => switchLayer(level, app.lens);
    depthSeg.appendChild(b);
  });
  const lensSeg = $("#lens", r);
  LENSES.forEach(({ lens, label }) => {
    const has = layerFor(app.depth, lens);
    const b = h(`<button role="tab" class="${app.lens === lens ? "on" : ""}" title="${lens === "pattern" ? "Shape, invariants, cross-domain parallels" : lens === "steps" ? "Built from definitions, step by step" : "Balanced exposition"}"><span class="${has ? "" : "missing"}">${label}</span></button>`);
    b.onclick = () => switchLayer(app.depth, lens);
    lensSeg.appendChild(b);
  });

  renderContent();
  renderProbe($("#probe-panel", r));
  renderRelations($("#rels", r));
  renderSources($("#sources-panel", r));
  renderFamily($("#family-panel", r));

  r.querySelectorAll("[data-open]").forEach((a) => (a.onclick = (e) => { e.preventDefault(); openThread(a.dataset.open); }));
  if (resolved) {
    $("#reopen", r).onclick = async () => { await api(`/api/threads/${t.id}/reopen`, { method: "POST" }); route(); };
  } else {
    $("#branch", r).onclick = () => branchModal({});
    $("#pause", r).onclick = async () => { await api(`/api/threads/${t.id}/pause`, { method: "POST" }); toast("Paused. Checkpoint saved."); location.hash = "#/"; };
    $("#resolve", r).onclick = async () => {
      if (!confirm("Mark this thread resolved? Its connections stay in the graph.")) return;
      await api(`/api/threads/${t.id}/resolve`, { method: "POST" }); location.hash = "#/";
    };
    $("#mark-ok", r).onclick = () => mark("CONSOLIDATED");
    $("#mark-stuck", r).onclick = () => mark("STUCK");
    $("#pin-inline", r).onclick = () => pinModal();
  }
}

async function mark(status) {
  const prog = app.thread.progress.find((p) => p.unit_id === app.unit.id);
  const next = prog?.user_status === status ? "VIEWED" : status;
  await saveProgress({ status: next });
  app.thread = await api(`/api/threads/${app.thread.id}`);
  if (next === "STUCK") {
    pinModal("What exactly is the snag? (the primer will bring you back to this)");
  }
  renderReader();
}

async function switchLayer(level, lens) {
  const y = window.scrollY;
  app.depth = level;
  app.lens = lens;
  renderReaderSwitchesOnly();
  renderContent();
  window.scrollTo(0, y);
  saveProgress({});
}

function renderReaderSwitchesOnly() {
  document.querySelectorAll("#depth button").forEach((b, i) => b.classList.toggle("on", i === app.depth));
  const lensSeg = $("#lens");
  lensSeg.querySelectorAll("button").forEach((b, i) => {
    const lens = LENSES[i].lens;
    b.classList.toggle("on", lens === app.lens);
    b.firstElementChild.classList.toggle("missing", !layerFor(app.depth, lens));
  });
}

function renderContent() {
  const box = $("#content");
  const prov = $("#prov");
  const layer = layerFor(app.depth, app.lens);
  box.className = `content l${app.depth}`;
  prov.innerHTML = "";
  if (layer) {
    box.innerHTML = renderMd(layer.content_markdown);
    prov.innerHTML = `<span class="chip ${layer.origin}">${layer.origin}</span>` +
      (layer.model ? `<span class="mono">${esc(layer.model)}</span>` : "") +
      (layer.origin === "synthesised" ? `<span>LLM-written: verify before trusting</span>` : "") +
      `<button class="link" id="edit-layer">edit</button>`;
    $("#edit-layer").onclick = () => editLayer(layer);
    return;
  }
  const lvl = LEVELS[app.depth];
  box.innerHTML = "";
  const miss = h(`<div class="missing-layer">
    <p>No <b>${lvl.label}</b> (${lvl.hint}) layer in the <b>${app.lens}</b> lens yet.</p>
    <div class="btn-row">
      <button id="synth" ${app.meta?.llm_enabled ? "" : "disabled"}>Synthesize ${lvl.label} · ${app.lens}</button>
      <button class="ghost" id="write">Write it yourself</button>
    </div>
    ${app.meta?.llm_enabled ? "" : `<p class="err" style="margin-top:12px">LLM is off: add an <code>HF_TOKEN</code> secret to the Space to enable synthesis.</p>`}
  </div>`);
  box.appendChild(miss);
  $("#write", miss).onclick = () => editLayer({ depth_level: app.depth, lens: app.lens, content_markdown: "" });
  if (app.meta?.llm_enabled) $("#synth", miss).onclick = () => synthesize(app.depth, app.lens);
}

async function synthesize(level, lens) {
  const box = $("#content");
  const unitId = app.unit.id;
  box.innerHTML = `<p class="rel-none">Model is thinking before it writes (reasoning models can take 30–60 s)…</p>`;
  box.classList.add("streaming");
  let text = "", last = 0;
  try {
    const res = await fetch(`/api/units/${unitId}/expand`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ level, lens }),
    });
    if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || res.statusText);
    const reader = res.body.getReader();
    const dec = new TextDecoder();
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      text += dec.decode(value, { stream: true });
      if (Date.now() - last > 120) { box.innerHTML = renderMd(text); last = Date.now(); }
    }
    box.innerHTML = renderMd(text);
  } catch (err) {
    box.innerHTML = `<p class="err">Synthesis failed: ${esc(err.message)}</p>`;
  } finally {
    box.classList.remove("streaming");
  }
  if (app.unit?.id === unitId) {
    app.unit = await api(`/api/units/${unitId}`);
    if (app.depth === level && app.lens === lens) { renderReaderSwitchesOnly(); renderContent(); }
  }
}

function editLayer(layer) {
  const m = openModal(`<h2>Edit L${layer.depth_level} · ${esc(layer.lens)}</h2>
    <p class="lede">Markdown with $inline$ and $$display$$ maths. Saving marks the layer as curated.</p>
    <textarea id="txt" style="min-height:320px" class="mono">${esc(layer.content_markdown)}</textarea>
    <div class="actions"><button class="ghost" id="cancel">Cancel</button><button id="save">Save</button></div>`);
  $("#cancel", m).onclick = closeModal;
  $("#save", m).onclick = async () => {
    const content = $("#txt", m).value.trim();
    if (!content) return;
    app.unit = await api(`/api/units/${app.unit.id}/layers`, {
      method: "PUT", body: { level: layer.depth_level, lens: layer.lens, content },
    });
    closeModal();
    renderReaderSwitchesOnly();
    renderContent();
  };
}

function renderProbe(panel, onRated) {
  const p = app.unit.probe;
  panel.innerHTML = `<h4>Test yourself</h4>`;
  if (!p) {
    const b = h(`<div class="rel-none">No recall question yet. ${app.meta?.llm_enabled ? `<button class="link">Generate one</button>` : ""}</div>`);
    const btn = b.querySelector("button");
    if (btn) btn.onclick = async () => {
      btn.disabled = true; btn.textContent = "generating…";
      try { app.unit.probe = await api(`/api/units/${app.unit.id}/probe`, { method: "POST" }); renderProbe(panel); }
      catch (err) { toast(err.message); btn.disabled = false; btn.textContent = "Generate one"; }
    };
    panel.appendChild(b);
    return;
  }
  const card = h(`<div class="probe">
    <div class="q">${renderMd(p.prompt)}</div>
    <textarea placeholder="Explain it in your own words before revealing. Rough is fine."></textarea>
    <div class="btn-row"><button class="ghost" id="reveal">Reveal reference</button></div>
  </div>`);
  $("#reveal", card).onclick = () => {
    $("#reveal", card).remove();
    card.appendChild(h(`<div class="ref">${renderMd(p.reference_answer)}</div>`));
    const row = h(`<div class="btn-row"><span class="sub" style="align-self:center;color:var(--text-dim);font-size:13px">How did that go?</span></div>`);
    [["again", "Didn't have it"], ["shaky", "Partly"], ["solid", "Had it"]].forEach(([rating, label]) => {
      const b = h(`<button class="ghost">${label}</button>`);
      b.onclick = async () => {
        const a = await api(`/api/recall/${p.id}/attempt`, {
          body: { rating, response: $("textarea", card).value || null, thread_id: app.thread?.id },
        });
        toast(`Will resurface in about ${Math.round(a.interval_days)} day${a.interval_days >= 1.5 ? "s" : ""}.`);
        row.remove();
        if (onRated) onRated(rating);
      };
      row.appendChild(b);
    });
    card.appendChild(row);
  };
  panel.appendChild(card);
}

function renderRelations(grid) {
  const rel = app.unit.relations;
  const cols = [
    ["prerequisites", "Prerequisites"],
    ["downstream", "Downstream"],
    ["analogous", "Structural parallels"],
    ["contrasts", "Contrast points"],
  ];
  for (const [key, label] of cols) {
    const col = h(`<div><h5>${label}</h5></div>`);
    if (!rel[key].length) col.appendChild(h(`<div class="rel-none">—</div>`));
    rel[key].forEach((x) => {
      const b = h(`<button class="rel-item">${esc(x.title)}<small>${esc(x.description || x.domain)}</small></button>`);
      b.onclick = () => relationChoice(x);
      col.appendChild(b);
    });
    grid.appendChild(col);
  }
  const add = h(`<div><h5>&nbsp;</h5><button class="link">+ link a concept</button></div>`);
  $("button", add).onclick = linkModal;
  grid.appendChild(add);
}

function relationChoice(x) {
  const resolved = app.thread.status === "RESOLVED";
  const m = openModal(`<h2>${esc(x.title)}</h2>
    <p class="lede">${esc(x.description || "")}</p>
    <div class="choice">
      <button id="here" ${resolved ? "disabled" : ""}>Explore in this thread<small>Keeps one line of thought; it joins this thread's trail.</small></button>
      <button class="ghost" id="fork" ${resolved ? "disabled" : ""}>⑂ Branch to a new thread<small>Checkpoints this thread and opens a child thread there.</small></button>
    </div>`);
  $("#here", m).onclick = async () => { closeModal(); await exploreHere(x.id); };
  $("#fork", m).onclick = () => branchModal({ unit: x });
}

async function exploreHere(unitId) {
  await loadUnit(unitId, 0, "core");
  window.scrollTo(0, 0);
}

function renderSources(panel) {
  const s = app.unit.sources;
  if (!s.length) { panel.remove(); return; }
  panel.innerHTML = `<h4>Sources</h4><ul class="sources">${s.map((x) =>
    `<li>${x.url ? `<a href="${esc(x.url)}" target="_blank" rel="noopener">${esc(x.title)}</a>` : esc(x.title)} <span class="chip">${esc(x.kind)}</span></li>`).join("")}</ul>`;
}

function renderFamily(panel) {
  const t = app.thread;
  if (!t.children.length) { panel.remove(); return; }
  panel.innerHTML = `<h4>Branches from this thread</h4>`;
  t.children.forEach((c) => {
    const b = h(`<button class="rel-item">${esc(c.title)} <span class="chip ${c.status}">${c.status.toLowerCase()}</span><small>${esc(c.branch_trigger_concept || "")}</small></button>`);
    b.onclick = () => openThread(c.id);
    panel.appendChild(b);
  });
}

/* ------------------------------------------------------------ dialogs */

async function unitOptions() {
  app.units = await api("/api/units");
  return app.units.map((u) => `<option value="${esc(u.title)}"></option>`).join("");
}

async function branchModal({ unit }) {
  const opts = await unitOptions();
  const cur = app.unit?.title || "this concept";
  const m = openModal(`<h2>⑂ Branch</h2>
    <p class="lede">This thread is checkpointed at <b>${esc(cur)}</b>. Nothing is lost.</p>
    <label>Branch to</label>
    <input id="target" list="unit-list" value="${esc(unit?.title || "")}" placeholder="An existing concept, or name a new one">
    <datalist id="unit-list">${opts}</datalist>
    <label>Reason for pivot (optional, the primer uses it)</label>
    <input id="reason" placeholder="e.g. need Raft before distributed state makes sense">
    <label>Link it? <span class="mono" style="color:var(--text-faint)">${esc(cur)} … target</span></label>
    <select id="rel"><option value="">no link</option>${Object.entries(REL_LABELS).map(([k, v]) => `<option value="${k}">${esc(cur)} ${v} target</option>`).join("")}</select>
    <div class="actions"><button class="ghost" id="cancel">Cancel</button><button id="go">Branch</button></div>`);
  $("#cancel", m).onclick = closeModal;
  $("#go", m).onclick = async () => {
    const name = $("#target", m).value.trim();
    if (!name) return;
    const match = app.units.find((u) => u.title.toLowerCase() === name.toLowerCase());
    const body = {
      reason: $("#reason", m).value.trim() || null,
      relationship_type: $("#rel", m).value || null,
      ...(match ? { unit_id: match.id } : { concept: name }),
    };
    const child = await api(`/api/threads/${app.thread.id}/branch`, { body });
    closeModal();
    toast(`Branched. “${app.thread.title}” is paused.`);
    location.hash = `#/t/${child.id}`;
  };
}

async function linkModal() {
  const opts = await unitOptions();
  const cur = app.unit.title;
  const m = openModal(`<h2>Link a concept</h2>
    <label>${esc(cur)} …</label>
    <select id="rel">${Object.entries(REL_LABELS).map(([k, v]) => `<option value="${k}">${v}</option>`).join("")}</select>
    <label>… this concept</label>
    <input id="target" list="unit-list2" placeholder="Existing concept or a new name"><datalist id="unit-list2">${opts}</datalist>
    <label>Why (optional)</label><input id="desc">
    <div class="actions"><button class="ghost" id="cancel">Cancel</button><button id="go">Link</button></div>`);
  $("#cancel", m).onclick = closeModal;
  $("#go", m).onclick = async () => {
    const name = $("#target", m).value.trim();
    if (!name) return;
    let target = app.units.find((u) => u.title.toLowerCase() === name.toLowerCase());
    if (!target) target = await api("/api/units", { body: { title: name, domain: app.unit.domain } });
    await api(`/api/units/${app.unit.id}/relations`, {
      body: { target_unit_id: target.id, relationship_type: $("#rel", m).value, description: $("#desc", m).value.trim() || null },
    });
    closeModal();
    app.unit = await api(`/api/units/${app.unit.id}`);
    renderReader();
  };
}

function pinModal(prompt) {
  if (!app.thread) return;
  const m = openModal(`<h2>📌 Drop a pin</h2>
    <p class="lede">${esc(prompt || "One sentence: a thought, a question, a snag. It goes into this thread's trail without leaving the page.")}</p>
    <input id="pin" maxlength="1000" autofocus placeholder="e.g. why does the Jacobian have a null direction?">
    <div class="actions"><button class="ghost" id="cancel">Cancel</button><button id="go">Pin</button></div>`);
  const submit = async () => {
    const text = $("#pin", m).value.trim();
    if (!text) return;
    await api(`/api/threads/${app.thread.id}/pins`, { body: { text, unit_id: app.unit?.id || null } });
    closeModal();
    toast("Pinned.");
  };
  $("#pin", m).addEventListener("keydown", (e) => { if (e.key === "Enter") submit(); });
  $("#cancel", m).onclick = closeModal;
  $("#go", m).onclick = submit;
}
$("#pin-fab").onclick = () => pinModal();

async function startThread(title, unitId, concept) {
  const t = await api("/api/threads", { body: { title, seed_unit_id: unitId || null, concept: concept || null } });
  closeModal();
  location.hash = `#/t/${t.id}`;
}

async function newThreadModal(prefill) {
  const opts = await unitOptions();
  const m = openModal(`<h2>New thread</h2>
    <p class="lede">A question or curiosity, and a concept to start from.</p>
    <label>What are you trying to understand?</label>
    <input id="title" autofocus placeholder="e.g. Why does attention use softmax and not something else?" value="${esc(prefill?.title || "")}">
    <label>Start at</label>
    <input id="start" list="unit-list3" placeholder="Pick a concept or name a new one" value="${esc(prefill?.start || "")}">
    <datalist id="unit-list3">${opts}</datalist>
    <div class="actions"><button class="ghost" id="cancel">Cancel</button><button id="go">Start</button></div>`);
  $("#cancel", m).onclick = closeModal;
  $("#go", m).onclick = async () => {
    const start = $("#start", m).value.trim();
    const title = $("#title", m).value.trim() || start;
    if (!title) return;
    const match = app.units.find((u) => u.title.toLowerCase() === start.toLowerCase());
    await startThread(title, match?.id, match ? null : start || null);
  };
}
$("#btn-new-thread").onclick = () => newThreadModal();

function ingestModal() {
  let kind = "wikipedia";
  const hints = {
    wikipedia: ["Article title or URL", "e.g. Lagrange multiplier"],
    arxiv: ["arXiv id or URL", "e.g. 1706.03762"],
    url: ["Any public web page", "https://…"],
    text: ["Paste text (notes, an excerpt you are allowed to use)", "First line becomes the title if the LLM is off"],
  };
  const m = openModal(`<h2>Add a concept from a source</h2>
    <p class="lede">The source text is stored with the concept so deeper layers are grounded in it. ${app.meta?.llm_enabled ? "The LLM drafts L0/L1, a recall question and links to your existing concepts." : "LLM is off: the first paragraph becomes L0."}</p>
    <div class="tabs">${Object.keys(hints).map((k) => `<button data-k="${k}" class="${k === kind ? "on" : ""}">${k}</button>`).join("")}</div>
    <label id="ref-label">${hints[kind][0]}</label>
    <div id="ref-box"><input id="ref" placeholder="${hints[kind][1]}"></div>
    <label>Domain (optional)</label><input id="domain" placeholder="e.g. Optimisation">
    <label><input type="checkbox" id="add-thread" style="width:auto"> also add it to the thread I'm in</label>
    <div class="err" id="err"></div>
    <div class="actions"><button class="ghost" id="cancel">Cancel</button><button id="go">Fetch & build</button></div>`);
  const cb = $("#add-thread", m);
  if (!app.thread || !location.hash.startsWith("#/t/")) cb.parentElement.remove();
  m.querySelectorAll(".tabs button").forEach((b) => (b.onclick = () => {
    kind = b.dataset.k;
    m.querySelectorAll(".tabs button").forEach((x) => x.classList.toggle("on", x === b));
    $("#ref-label", m).textContent = hints[kind][0];
    $("#ref-box", m).innerHTML = kind === "text"
      ? `<textarea id="ref" style="min-height:160px" placeholder="${hints[kind][1]}"></textarea>`
      : `<input id="ref" placeholder="${hints[kind][1]}">`;
  }));
  $("#cancel", m).onclick = closeModal;
  $("#go", m).onclick = async (e) => {
    const ref = $("#ref", m).value.trim();
    if (!ref) return;
    e.target.disabled = true; e.target.textContent = "Working…"; $("#err", m).textContent = "";
    try {
      const inThread = $("#add-thread", m)?.checked && app.thread;
      const unit = await api("/api/ingest", {
        body: { kind, ref, domain: $("#domain", m).value.trim(), thread_id: inThread ? app.thread.id : null },
      });
      closeModal();
      toast(unit.notice ? `Added “${unit.title}”. ${unit.notice}` : `Added “${unit.title}”.`);
      if (inThread) await loadUnit(unit.id, 0, "core");
      else unitPreview(unit);
    } catch (err) {
      $("#err", m).textContent = err.message;
      e.target.disabled = false; e.target.textContent = "Fetch & build";
    }
  };
}
$("#btn-ingest").onclick = ingestModal;

/* ---------------------------------------------------------------- atlas */

async function showAtlas() {
  app.thread = null;
  const units = await api("/api/units");
  view.innerHTML = "";
  const top = h(`<div class="atlas-top"><input id="q" placeholder="Filter concepts…" autofocus><span class="meta mono" style="color:var(--text-faint);font-size:12px">${units.length} concepts</span></div>`);
  view.appendChild(top);
  const list = h(`<div></div>`);
  view.appendChild(list);
  const draw = (filter) => {
    list.innerHTML = "";
    const f = filter.toLowerCase();
    const shown = units.filter((u) => !f || u.title.toLowerCase().includes(f) || u.domain.toLowerCase().includes(f));
    const byDomain = {};
    shown.forEach((u) => (byDomain[u.domain] ||= []).push(u));
    for (const [domain, us] of Object.entries(byDomain)) {
      list.appendChild(h(`<div class="domain-h mono">${esc(domain)}</div>`));
      const grid = h(`<div class="grid"></div>`);
      us.forEach((u) => {
        const c = h(`<div class="card" tabindex="0" role="button"><h3>${esc(u.title)}</h3>
          <div class="hook">${u.hook ? renderMd(u.hook) : `<i>stub: no layers yet</i>`}</div></div>`);
        c.onclick = () => unitPreview(u);
        grid.appendChild(c);
      });
      list.appendChild(grid);
    }
    if (!shown.length) list.appendChild(h(`<p class="rel-none">Nothing matches. Add it with <b>+ Source</b>, or start a thread on it.</p>`));
  };
  $("#q", top).addEventListener("input", (e) => draw(e.target.value));
  draw("");
}

async function unitPreview(u) {
  const full = await api(`/api/units/${u.id}`);
  const active = await api("/api/threads?status=ACTIVE,PAUSED,NEW");
  const l0 = full.layers.find((l) => l.depth_level === 0 && l.lens === "core");
  const m = openModal(`<div class="meta mono" style="font-size:12px;color:var(--text-faint);text-transform:uppercase">${esc(full.domain)}</div>
    <h2>${esc(full.title)}</h2>
    <div class="content l0" style="font-size:16px;margin-top:10px">${l0 ? renderMd(l0.content_markdown) : "<i>No hook yet.</i>"}</div>
    <div class="choice">
      <button id="start">Start a new thread here</button>
      ${active.length ? `<div style="display:flex;gap:8px"><select id="into">${active.map((t) => `<option value="${t.id}">${esc(t.title)}</option>`).join("")}</select><button class="ghost" id="add" style="white-space:nowrap">Add to thread</button></div>` : ""}
    </div>`);
  $("#start", m).onclick = () => newThreadModal({ start: full.title, title: "" });
  const add = $("#add", m);
  if (add) add.onclick = async () => {
    const tid = $("#into", m).value;
    await api(`/api/threads/${tid}/progress`, { body: { unit_id: full.id, depth: 0 } });
    closeModal();
    openThread(tid);
  };
}

/* ------------------------------------------------------------ resurface */

async function showResurface() {
  app.thread = null;
  const queue = await api("/api/recall/queue");
  view.innerHTML = `<div class="reader"><div class="section-h"><h2>Resurface</h2>
    <span class="hint">concepts you have engaged with, ready for a recall check. No backlog, no penalty: do one or none.</span></div><div id="q"></div></div>`;
  const box = $("#q");
  if (!queue.length) {
    box.innerHTML = `<div class="empty">Nothing is ready right now. Concepts appear here once you have read them at L1+ or locked them in, and come back on an expanding schedule after each check.</div>`;
    return;
  }
  let i = 0;
  const show = () => {
    if (i >= queue.length) { box.innerHTML = `<div class="empty">That's all that's ready. ✓</div>`; return; }
    const p = queue[i];
    app.unit = { id: p.unit_id, probe: { id: p.probe_id, prompt: p.prompt, reference_answer: p.reference_answer } };
    box.innerHTML = `<div class="meta mono" style="font-size:12px;color:var(--text-faint);margin-bottom:6px">${i + 1} / ${queue.length} · ${esc(p.domain)} · ${esc(p.title)}</div><div id="probe-slot"></div>
      <div class="btn-row"><button class="ghost" id="skip">Skip</button></div>`;
    const slot = $("#probe-slot");
    renderProbe(slot, () => setTimeout(() => { i++; show(); }, 500));
    $("h4", slot)?.remove();
    $("#skip").onclick = () => { i++; show(); };
  };
  show();
}

/* ---------------------------------------------------------------- theme */

function applyTheme(t) {
  document.documentElement.dataset.theme = t;
  try { localStorage.setItem("theme", t); } catch (_) {}
}
$("#btn-theme").onclick = () => applyTheme(document.documentElement.dataset.theme === "dark" ? "light" : "dark");
try { const t = localStorage.getItem("theme"); if (t) document.documentElement.dataset.theme = t; } catch (_) {}

/* ----------------------------------------------------------------- boot */

(async function boot() {
  try { app.meta = await api("/api/meta"); } catch (_) { app.meta = {}; }
  route();
})();
