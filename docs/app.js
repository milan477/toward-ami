"use strict";

const PIAC = ["perceptual", "inferential", "affective", "contextual"];
const ROUTES = ["home", "benchmarks", "models", "evaluation", "results"];
const state = { data: null, filters: { q: "", piac: "" }, benchQ: "", modelQ: "", selected: new Set(), selectMode: false };

const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const pct = (x) => (x == null ? "–" : (x * 100).toFixed(1) + "%");
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

init();

async function loadData() {
  const base = "data/";
  const names = ["meta", "news", "models", "benchmarks", "evaluation", "overview", "prompts", "questions"];
  const parts = await Promise.all(
    names.map((n) => fetch(`${base}${n}.json`, { cache: "no-store" }).then((r) => {
      if (!r.ok) throw new Error(`failed to load ${n}.json`);
      return r.json();
    })),
  );
  const [meta, news, models, benchmarks, evaluation, overview, prompts, questions] = parts;
  return { ...meta, news, models, benchmarks, evaluation, overview, prompts, questions };
}

async function init() {
  const data = await loadData();
  state.data = data;

  const repo = data.repo_url || "https://github.com/milan477/toward-ami";
  $("#repo-btn").href = repo;
  const footRepo = $("#foot-repo");
  if (footRepo) footRepo.href = repo;
  $("#about-btn").addEventListener("click", openAbout);

  renderNews();
  setupBenchSearch();
  setupModelSearch();
  renderBenchmarks();
  renderModels();
  renderEvaluation();
  renderResults();

  window.addEventListener("hashchange", route);
  route();
}

/* ---------- routing ---------- */
function route() {
  let r = (location.hash || "#home").slice(1);
  if (!ROUTES.includes(r)) r = "home";
  $$(".page").forEach((p) => p.classList.toggle("active", p.id === "page-" + r));
  $$("#menu a").forEach((a) => a.classList.toggle("active", a.dataset.route === r));
  closeZoom();
  const bar = $("#bench-actions");
  if (bar) bar.style.display = r === "benchmarks" ? "" : "none";
  window.scrollTo({ top: 0, behavior: "instant" in window ? "instant" : "auto" });
}

/* ---------- home: news ---------- */
function renderNews() {
  const el = $("#news");
  if (!el) return;                       // "Latest" block removed from the home screen
  el.innerHTML = (state.data.news || []).map((n) => `
    <div class="news-item">
      <button class="news-title" type="button">
        <span class="t">${esc(n.title)}</span>
        <span class="date">${esc(n.date)}</span>
      </button>
      <p>${esc(n.text)}</p>
    </div>`).join("");
  $$("#news .news-title").forEach((b) =>
    b.addEventListener("click", () => b.closest(".news-item").classList.toggle("open")));
}

/* ---------- benchmarks ---------- */
function benchByName(name) {
  return (state.data.benchmarks || []).find((b) => b.name === name);
}
// Truncate to `n` words (grid cards); the full text shows in the zoom view.
const truncWords = (s, n) => {
  const w = String(s).trim().split(/\s+/);
  return w.length > n ? w.slice(0, n).join(" ") + "…" : String(s);
};
const formatSize = (s) => {
  const t = String(s).trim();
  if (!t) return t;
  const m = t.match(/^(\d+)(.*)$/);
  if (!m) return t;
  return Number(m[1]).toLocaleString("en-US") + m[2];
};
const field = (k, v, muted, limit) => v
  ? `<div class="field"><div class="k">${k}</div><div class="v${muted ? " muted" : ""}">${esc(limit ? truncWords(v, limit) : v)}</div></div>`
  : "";
const linksHTML = (b) => (b.links || []).map((l) =>
  `<a href="${esc(l.url)}" target="_blank" rel="noopener">${esc(l.label)}</a>`).join("");

function setupBenchSearch() {
  let t;
  $("#bench-search").addEventListener("input", (e) => {
    clearTimeout(t);
    t = setTimeout(() => { state.benchQ = e.target.value.toLowerCase().trim(); renderBenchmarks(); }, 120);
  });
  // delegated: in select mode a click anywhere on the box toggles selection;
  // otherwise it opens the zoom view. (The round circle is just an indicator.)
  const grid = $("#benchmarks");
  grid.addEventListener("click", (e) => {
    if (e.target.closest("a")) return;
    const card = e.target.closest(".bench");
    if (!card) return;
    const name = card.dataset.name;
    if (state.selectMode) {
      const on = !state.selected.has(name);
      toggleSelect(name, on);
      const box = card.querySelector(".bench-select input");
      if (box) box.checked = on;
    } else {
      openZoom(name, card);
    }
  });
  $("#dl-bib").addEventListener("click", () => exportBib());
  $("#dl-py").addEventListener("click", () => exportPy());
  $("#sel-clear").addEventListener("click", clearSelection);
  $("#sel-toggle").addEventListener("click", toggleSelectMode);
  // delegated so the dynamically-rendered close button works too
  $("#zoom").addEventListener("click", (e) => { if (e.target.closest("[data-close]")) closeZoom(); });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeZoom(); });
}

function renderBenchmarks() {
  const all = state.data.benchmarks || [];
  const q = state.benchQ;
  const rows = !q ? all : all.filter((b) =>
    [b.name, b.paper_title, b.domain, b.format, b.modalities, b.skills, b.sources, b.year]
      .join(" ").toLowerCase().includes(q));
  $("#bench-count").textContent = `${rows.length} of ${all.length}`;
  $("#bench-empty").hidden = rows.length > 0;
  $("#benchmarks").innerHTML = rows.map((b) => {
    const kind = [b.domain, b.format].filter(Boolean).join(" · ");
    const on = state.selected.has(b.name);
    return `
    <article class="bench${on ? " selected" : ""}" data-name="${esc(b.name)}">
      <label class="bench-select" data-name="${esc(b.name)}" title="Select for citation">
        <input type="checkbox" ${on ? "checked" : ""} aria-label="Select ${esc(b.name)}" />
      </label>
      <div class="bench-id">
        <h3>${esc(b.name)}</h3>
        <span class="year">${esc(b.year)}</span>
        ${kind ? `<span class="kind">${esc(kind)}</span>` : ""}
      </div>
      ${b.paper_title ? `<p class="paper">${esc(b.paper_title)}</p>` : ""}
      <div class="bench-fields">
        ${field("Modalities", b.modalities, false, 20)}
        ${field("Size", formatSize(b.size), false, 20)}
        ${field("Skills", b.skills, true, 20)}
        ${field("Sources", b.sources, true, 20)}
        ${b.links && b.links.length ? `<div class="field"><div class="k">Links</div><div class="bench-links">${linksHTML(b)}</div></div>` : ""}
      </div>
    </article>`;
  }).join("");
}

/* ---------- selection + citation ---------- */
function toggleSelectMode() {
  state.selectMode = !state.selectMode;
  const btn = $("#sel-toggle");
  btn.classList.toggle("on", state.selectMode);
  btn.setAttribute("aria-pressed", String(state.selectMode));
  btn.textContent = state.selectMode ? "Done" : "Select";
  $("#benchmarks").classList.toggle("select-mode", state.selectMode);
  if (!state.selectMode) clearSelection();
}
function toggleSelect(name, on) {
  if (on) state.selected.add(name); else state.selected.delete(name);
  const card = $(`.bench[data-name="${cssq(name)}"]`);
  if (card) card.classList.toggle("selected", on);
  renderActionBar();
}
function clearSelection() {
  state.selected.clear();
  $$("#benchmarks .bench-select input").forEach((c) => (c.checked = false));
  $$("#benchmarks .bench.selected").forEach((c) => c.classList.remove("selected"));
  renderActionBar();
}
function renderActionBar() {
  const n = state.selected.size;
  $("#sel-n").textContent = n;
  $("#bench-actions").hidden = n === 0;
}
function selectedBenchmarks() {
  return (state.data.benchmarks || []).filter((b) => state.selected.has(b.name));
}
const cssq = (s) => s.replace(/["\\]/g, "\\$&");
const slug = (s) => s.toLowerCase().replace(/[^a-z0-9]+/g, "").slice(0, 40);

function bibKey(b) { return slug(b.name) + (b.year || ""); }

function bibFor(b) {
  if (b.bibtex && b.bibtex.trim()) return b.bibtex.trim();
  const url = b.paper_url || (b.links[0] && b.links[0].url) || "";
  return [
    `@misc{${bibKey(b)},`,
    `  title        = {${b.paper_title || b.name}},`,
    `  year         = {${b.year || "n.d."}},`,
    url ? `  howpublished = {\\url{${url}}},` : null,
    `  note         = {${b.name} benchmark},`,
    `}`,
  ].filter(Boolean).join("\n");
}

function exportBib() {
  const list = selectedBenchmarks();
  if (!list.length) return;
  const header = `% Citations for ${list.length} benchmark(s) — toward Artificial Musical Intelligence\n\n`;
  download("benchmarks.bib", header + list.map(bibFor).join("\n\n") + "\n", "application/x-bibtex");
}

function hfId(url) {
  const m = /huggingface\.co\/datasets\/([^?#\s]+)/.exec(url || "");
  return m ? m[1].replace(/\/+$/, "") : "";
}

function exportPy() {
  const list = selectedBenchmarks();
  if (!list.length) return;
  const lines = [
    '"""Download the selected music-understanding benchmarks.',
    "",
    "Generated by toward-ami.com. Datasets on the Hugging Face Hub load directly;",
    "others point to the paper or code repository.",
    "",
    "    pip install datasets",
    '"""',
    "from datasets import load_dataset",
    "",
    "datasets = {}",
    "",
  ];
  for (const b of list) {
    const id = hfId(b.hf_url);
    lines.push(`# ${b.name} (${b.year || "n.d."}) — ${b.paper_title || ""}`.trimEnd());
    if (b.paper_url) lines.push(`# paper: ${b.paper_url}`);
    if (id) {
      lines.push(`datasets[${JSON.stringify(b.name)}] = load_dataset(${JSON.stringify(id)})`);
    } else if (b.code_url) {
      lines.push(`# No Hugging Face dataset — clone the code/data repo:`);
      lines.push(`#   git clone ${b.code_url}`);
    } else {
      lines.push(`# No dataset/code link on record; see the paper above.`);
    }
    lines.push("");
  }
  lines.push('print(f"Loaded {len(datasets)} benchmark(s) from the Hugging Face Hub.")', "");
  download("download_benchmarks.py", lines.join("\n"), "text/x-python");
}

function download(filename, text, mime) {
  const blob = new Blob([text], { type: mime || "text/plain" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url; a.download = filename;
  document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

/* ---------- zoom ---------- */
function zoomHTML(b) {
  const kind = [b.domain, b.format].filter(Boolean).join(" · ");
  return `
    <button class="zoom-close" type="button" data-close aria-label="Close">×</button>
    <div class="bench-id">
      <h3>${esc(b.name)}</h3>
      <span class="year">${esc(b.year)}</span>
      ${kind ? `<span class="kind">${esc(kind)}</span>` : ""}
    </div>
    ${b.paper_title ? `<p class="paper">${esc(b.paper_title)}</p>` : ""}
    <div class="bench-fields">
      ${field("Modalities", b.modalities)}
      ${field("Size", formatSize(b.size))}
      ${field("Skills", b.skills, true)}
      ${field("Sources", b.sources, true)}
      ${field("Models", b.models, true)}
      ${b.links && b.links.length ? `<div class="field"><div class="k">Links</div><div class="bench-links">${linksHTML(b)}</div></div>` : ""}
    </div>
    <div class="zoom-actions">
      <button type="button" class="act" data-zoom-bib>Export .bib</button>
      <button type="button" class="act" data-zoom-py disabled title="Coming soon">Python download (coming soon)</button>
    </div>
    <pre class="cite-preview">${esc(bibFor(b))}</pre>`;
}

function openZoom(name, origin) {
  const b = benchByName(name);
  if (!b) return;
  const overlay = $("#zoom");
  const card = $("#zoom-card");
  card.innerHTML = zoomHTML(b);
  overlay.hidden = false;
  requestAnimationFrame(() => overlay.classList.add("show"));

  // FLIP: grow the centered card from the clicked box's rect.
  card.style.transition = "none";
  card.style.transform = "none";
  const first = origin.getBoundingClientRect();
  const last = card.getBoundingClientRect();
  const dx = first.left - last.left, dy = first.top - last.top;
  const sx = first.width / last.width, sy = first.height / last.height;
  card.style.transformOrigin = "top left";
  card.style.transform = `translate(${dx}px, ${dy}px) scale(${sx}, ${sy})`;
  card.getBoundingClientRect();
  requestAnimationFrame(() => {
    card.style.transition = "transform 320ms cubic-bezier(.2,.7,.2,1)";
    card.style.transform = "none";
  });

  // wire the in-modal controls
  card.querySelector("[data-zoom-bib]").addEventListener("click", () =>
    download(`${slug(b.name)}.bib`, bibFor(b) + "\n", "application/x-bibtex"));
}

/* ---------- home: about / "Learn more" ---------- */
function openAbout() {
  const overlay = $("#zoom");
  const card = $("#zoom-card");
  card.innerHTML = `
    <button class="zoom-close" type="button" data-close aria-label="Close">×</button>
    <div class="about">
      <span class="wip-badge">our mission</span>
      <br /><br />
      <p><em>Towards Artificial Musical Intelligence (AMI)</em> is an open, community-driven platform where researchers can
        collectively define what artificial musical intelligence is about.</p>
      <p>Its goal is to unify evaluation across models
       and benchmarks, enabling consistent and comprehensive assessment of model performance. The Benchmarks section allows users to explore and filter tasks by musical skill, while the Results section provides performance comparisons across models. 
        Designed as a living resource, the platform continuously evolves with contributions from the community, supporting the development and evaluation of the next generation of Audio-Language Models.</p>
      <p class="about-note">Fork the repository on GitHub to contribute to the website, benchmarks or models.</p>
    </div>`;
  overlay.hidden = false;
  requestAnimationFrame(() => overlay.classList.add("show"));
  // No FLIP here — just center the card and let the backdrop fade in.
  card.style.transition = "none";
  card.style.transform = "none";
}

function closeZoom() {
  const overlay = $("#zoom");
  if (overlay.hidden) return;
  const card = $("#zoom-card");
  overlay.classList.remove("show");
  card.style.transition = "transform 140ms ease, opacity 140ms ease";
  card.style.transformOrigin = "center";
  card.style.transform = "scale(0.96)";
  card.style.opacity = "0";
  setTimeout(() => {
    overlay.hidden = true;
    card.style.transition = "";
    card.style.transform = "";
    card.style.opacity = "";
  }, 150);
}

/* ---------- evaluation ---------- */
function motivationHTML(ev) {
  const m = ev.motivation;
  if (!m) return "";
  const paras = (m.body || []).map((p) => `<p>${esc(p)}</p>`).join("");
  const segs = (m.annotated_passage || []).map((seg) => `
    <span class="annot-seg ${esc(seg.category)}">
      <span class="annot-text">${esc(seg.text)}</span>
      <span class="annot-cat">${esc(seg.category)}</span>
    </span>`).join("");
  return `
    <aside class="rule-of-thumb framework-motivation">
      <p class="rule-of-thumb-title">Motivation</p>
      <div class="motivation-body">
        ${paras}
        ${m.example_prompt ? `<p class="motivation-example-q">${esc(m.example_prompt)}</p>` : ""}
        ${segs ? `<div class="annotated-passage">${segs}</div>` : ""}
      </div>
    </aside>`;
}

function ruleOfThumbHTML(ev) {
  const items = ev.rule_of_thumb_items;
  if (items?.length) {
    const rows = items.map((item) => `
      <li class="rule-row">
        <span class="rule-condition">${esc(item.condition)}</span>
        <span class="rule-arrow" aria-hidden="true">→</span>
        <span class="pill ${esc(item.category)}">${esc(item.category)}</span>
      </li>`).join("");
    return `
      <aside class="rule-of-thumb">
        <p class="rule-of-thumb-title">Rule of thumb</p>
        <p class="rule-of-thumb-lede">By degree of ambiguity</p>
        <ul class="rule-of-thumb-list">${rows}</ul>
      </aside>`;
  }
  if (!ev.rule_of_thumb) return "";
  return `<aside class="rule-of-thumb"><p>${esc(ev.rule_of_thumb)}</p></aside>`;
}

function renderEvaluation() {
  const ev = state.data.evaluation || {};
  const cats = ev.categories || [];

  const introEl = $("#framework-intro");
  if (introEl) {
    introEl.textContent = ev.intro || "";
    introEl.hidden = !ev.intro;
  }

  let html = `<div class="framework-list">` + cats.map((c) => `
    <article class="framework-card" data-key="${esc(c.key)}">
      <div class="bench-id"><h3>${esc(c.key)}</h3></div>
      ${c.subtitle ? `<p class="fw-sub">${esc(c.subtitle)}</p>` : ""}
    </article>`).join("") + `</div>`;
  $("#piac").innerHTML = html;
  const rot = ruleOfThumbHTML(ev);
  if (rot) $("#piac").insertAdjacentHTML("beforeend", rot);
  const mot = motivationHTML(ev);
  if (mot) $("#piac").insertAdjacentHTML("beforeend", mot);

  // Click a category to open its full detail in the shared zoom view.
  $("#piac").addEventListener("click", (e) => {
    const card = e.target.closest(".framework-card");
    if (card) openEvalZoom(card.dataset.key, card);
  });

  renderPrompts();
}

function evalByKey(key) {
  return ((state.data.evaluation || {}).categories || []).find((c) => c.key === key);
}

function evalZoomHTML(c) {
  return `
    <button class="zoom-close" type="button" data-close aria-label="Close">×</button>
    <div class="bench-id"><h3 class="cap">${esc(c.key)}</h3></div>
    ${c.subtitle ? `<p class="fw-sub">${esc(c.subtitle)}</p>` : ""}
    <p class="detail"><b>Information.</b> ${esc(c.information)}</p>
    <p class="detail"><b>Ambiguity.</b> ${esc(c.ambiguity)}</p>
    <p class="detail"><b>Coverage.</b> ${esc(c.coverage)}</p>
    <p class="detail"><b>Evaluation.</b> ${esc(c.evaluation)}</p>
    <p class="example"><b>Q.</b> ${esc(c.example_q)} &nbsp; <b>A.</b> ${esc(c.example_a)}</p>`;
}

function openEvalZoom(key, origin) {
  const c = evalByKey(key);
  if (!c) return;
  flipZoom(evalZoomHTML(c), origin);
}

function renderPrompts() {
  $("#prompts").innerHTML = (state.data.prompts || []).map((p, i) => `
    <div class="prompt${i === 0 ? " open" : ""}">
      <div class="prompt-head" data-idx="${i}">
        <div>
          <h4>${esc(p.name)}</h4>
          <p class="purpose">${esc(p.purpose)}</p>
        </div>
        <span class="chev"></span>
      </div>
      <div class="prompt-body"><pre>${esc(p.text)}</pre></div>
    </div>`).join("");
  $$("#prompts .prompt-head").forEach((h) =>
    h.addEventListener("click", () => h.closest(".prompt").classList.toggle("open")));
}

/* ---------- models ---------- */
function modelById(id) {
  return (state.data.models || []).find((m) => m.id === id);
}

function setupModelSearch() {
  let t;
  $("#model-search").addEventListener("input", (e) => {
    clearTimeout(t);
    t = setTimeout(() => { state.modelQ = e.target.value.toLowerCase().trim(); renderModels(); }, 120);
  });
  $("#models").addEventListener("click", (e) => {
    const card = e.target.closest(".framework-card");
    if (card) openModelZoom(card.dataset.id, card);
  });
}

function renderModels() {
  const all = state.data.models || [];
  const q = state.modelQ;
  const rows = !q ? all : all.filter((m) =>
    [m.label, m.developer, m.year, m.paper_title, m.id]
      .join(" ").toLowerCase().includes(q));
  $("#model-count").textContent = `${rows.length} of ${all.length}`;
  $("#models-empty").hidden = rows.length > 0;
  $("#models").innerHTML = rows.map((m) => `
    <article class="framework-card" data-id="${esc(m.id)}">
      <div class="bench-id">
        <h3 class="cap">${esc(m.label)}</h3>
        ${m.year ? `<span class="year">${esc(m.year)}</span>` : ""}
      </div>
      ${m.developer ? `<p class="fw-sub">${esc(m.developer)}</p>` : ""}
    </article>`).join("");
}

function modelZoomHTML(m) {
  const paper = m.paper_url
    ? `<div class="field"><div class="k">Paper</div><div class="bench-links"><a href="${esc(m.paper_url)}" target="_blank" rel="noopener">${esc(m.paper_title || "Paper")}</a></div></div>`
    : "";
  return `
    <button class="zoom-close" type="button" data-close aria-label="Close">×</button>
    <div class="bench-id"><h3 class="cap">${esc(m.label)}</h3></div>
    <div class="bench-fields">
      ${field("Released", m.year)}
      ${field("By", m.developer)}
      ${paper}
    </div>`;
}

function openModelZoom(id, origin) {
  const m = modelById(id);
  if (!m) return;
  flipZoom(modelZoomHTML(m), origin);
}

/* Shared zoom opener: set card HTML, fade the backdrop, and FLIP-grow the
   centered card from the clicked box's rect. */
function flipZoom(html, origin) {
  const overlay = $("#zoom");
  const card = $("#zoom-card");
  card.innerHTML = html;
  overlay.hidden = false;
  requestAnimationFrame(() => overlay.classList.add("show"));
  card.style.transition = "none";
  card.style.transform = "none";
  const first = origin.getBoundingClientRect();
  const last = card.getBoundingClientRect();
  const dx = first.left - last.left, dy = first.top - last.top;
  const sx = first.width / last.width, sy = first.height / last.height;
  card.style.transformOrigin = "top left";
  card.style.transform = `translate(${dx}px, ${dy}px) scale(${sx}, ${sy})`;
  card.getBoundingClientRect();
  requestAnimationFrame(() => {
    card.style.transition = "transform 320ms cubic-bezier(.2,.7,.2,1)";
    card.style.transform = "none";
  });
}

const evalModels = (data = state.data) =>
  (data.models || []).filter((m) => (data.overview || {})[m.id]);

/* ---------- results ---------- */
function renderResults() {
  const { overview } = state.data;
  const models = evalModels();

  $("#results-overview").innerHTML = models.map((m) => {
    const o = overview[m.id];
    const row = (lab, val, head) =>
      `<div class="mrow${head ? " headline" : ""}"><span class="lab">${lab}</span><span class="num">${val}</span></div>`;
    return `
    <div class="model-panel">
      <h3>${esc(m.label)}</h3>
      ${row("MCQ accuracy (apparent)", pct(o.mcq_acc), true)}
      ${row("OEQ accuracy (actual)", pct(o.oeq_acc), true)}
      ${row("MCQ − OEQ gap", ((o.mcq_acc - o.oeq_acc) * 100).toFixed(1) + " pt")}
      ${row("Questions", o.n)}
    </div>`;
  }).join("");

  renderPiacTable();
  setupResultControls();
  renderCards();
}

function renderPiacTable() {
  const { overview } = state.data;
  const models = evalModels();
  let html = `<thead><tr>
      <th>PIAC category</th><th>Model</th>
      <th class="num">n</th><th class="num">MCQ</th><th class="num">OEQ</th><th class="num">gap</th>
    </tr></thead><tbody>`;
  for (const cat of PIAC) {
    const rows = models.map((m) => [m, overview[m.id].by_piac[cat]]).filter(([, r]) => r);
    if (!rows.length) continue;
    rows.forEach(([m, r], i) => {
      html += `<tr>
        ${i === 0 ? `<td class="cat-cell" rowspan="${rows.length}"><span class="pill ${cat}">${cat}</span></td>` : ""}
        <td>${esc(m.label)}</td>
        <td class="num">${r.n}</td>
        <td class="num">${pct(r.mcq_acc)}</td>
        <td class="num">${pct(r.oeq_acc)}</td>
        <td class="num">${((r.mcq_acc - r.oeq_acc) * 100).toFixed(0)} pt</td>
      </tr>`;
    });
  }
  $("#piac-table").innerHTML = html + "</tbody>";
}

function setupResultControls() {
  const pf = $("#piac-filter");
  pf.innerHTML = `<option value="">all</option>` + PIAC.map((c) => `<option value="${c}">${c}</option>`).join("");
  pf.addEventListener("change", () => { state.filters.piac = pf.value; renderCards(); });
  let t;
  $("#search").addEventListener("input", (e) => {
    clearTimeout(t);
    t = setTimeout(() => { state.filters.q = e.target.value.toLowerCase().trim(); renderCards(); }, 140);
  });
  const inspectBtn = $("#inspect-benchmark");
  const panel = $("#questions-panel");
  inspectBtn.addEventListener("click", () => {
    const open = panel.hidden;
    panel.hidden = !open;
    inspectBtn.setAttribute("aria-expanded", String(open));
    inspectBtn.textContent = open ? "Hide questions" : "Inspect benchmark";
  });
}

function renderCards() {
  const { q, piac } = state.filters;
  const models = evalModels();
  const list = state.data.questions.filter((row) => {
    if (piac && row.piac !== piac) return false;
    if (q) {
      const hay = [row.question, row.correct_answer, row.skills,
        ...models.map((m) => row[m.id]?.oeq_response)].join(" ").toLowerCase();
      if (!hay.includes(q)) return false;
    }
    return true;
  });
  $("#count").textContent = `${list.length} of ${state.data.questions.length}`;
  $("#empty").hidden = list.length > 0;
  $("#cards").innerHTML = list.map(cardHTML).join("");
}

function cardHTML(row) {
  const models = evalModels();
  const audio = row.audio
    ? `<audio controls preload="none" src="${esc(row.audio)}"></audio>`
    : `<div class="no-audio">audio unavailable for this clip</div>`;
  const meta = [row.category_2, row.category_3, row.skills ? "skill: " + row.skills : ""]
    .filter(Boolean).map(esc).join(" · ");
  const answers = models.map((m) => modelAnswer(m, row[m.id])).join("");
  return `
  <article class="qcard">
    <div class="qcard-top">
      <p class="q">${esc(row.question)}</p>
      <span class="pill ${row.piac}">${esc(row.piac || "?")}</span>
    </div>
    <div class="qmeta">${meta}</div>
    ${audio}
    <p class="ref"><b>Reference:</b> ${esc(row.correct_answer)}</p>
    <div class="answers">${answers}</div>
  </article>`;
}

function modelAnswer(m, cell) {
  cell = cell || {};
  const oeqRight = (cell.oeq_score ?? 0) >= 0.5;
  const scoreTxt = cell.oeq_score == null ? "–" : cell.oeq_score.toFixed(2);
  const mark = (ok) => `<span class="mark ${ok ? "ok" : "no"}">${ok ? "correct" : "incorrect"}</span>`;
  // The models' own answers (MCQ prediction, OEQ response text) are hidden;
  // only the correctness marks and judge score are shown.
  return `
    <div class="mans">
      <div class="who">${esc(m.label)}</div>
      <div class="line"><span class="k">Multiple choice</span>${mark(cell.mcq_correct)}</div>
      <div class="line"><span class="k">Open-ended</span>${mark(oeqRight)}<span class="score">score ${scoreTxt}</span></div>
    </div>`;
}
