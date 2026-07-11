"use strict";

const PIAC = ["perceptual", "inferential", "affective", "contextual"];
const ROUTES = ["home", "models", "benchmarks", "evaluation", "results"];
const CATEGORY_LABELS = {
  modality: "Modality",
  category: "Category",
  genre: "Genre",
  skill: "Skill",
};
const FILTER_LABELS = {
  ...CATEGORY_LABELS,
  piac: "PIAC",
};
const state = {
  data: null,
  benchQ: "",
  benchSort: "name-asc",
  modelQ: "",
  modelSort: "label-asc",
  selected: new Set(),
  selectMode: false,
  inspectName: null,
  benchQFilters: { q: "", categories: {} },
  benchQControlsReady: false,
  questionsPromise: null,
};

const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const pct = (x) => (x == null ? "–" : (x * 100).toFixed(1) + "%");
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const inspectIcon = () => `
  <svg viewBox="0 0 24 24" aria-hidden="true">
    <path d="M4 20h16"></path>
    <path d="M7 17V9"></path>
    <path d="M12 17V5"></path>
    <path d="M17 17v-6"></path>
  </svg>`;
const knownPiac = (value) => {
  const normalized = String(value || "").trim().toLowerCase();
  return PIAC.includes(normalized) ? normalized : "";
};

init();

async function loadData() {
  const base = "data/";
  const names = ["meta", "news", "models", "benchmarks", "evaluation", "overview", "prompts"];
  const parts = await Promise.all(
    names.map((n) => fetch(`${base}${n}.json`, { cache: "no-store" }).then((r) => {
      if (!r.ok) throw new Error(`failed to load ${n}.json`);
      return r.json();
    })),
  );
  const [meta, news, models, benchmarks, evaluation, overview, prompts] = parts;
  return { ...meta, news, models, benchmarks, evaluation, overview, prompts, questions: null };
}

async function loadBenchmarkQuestions() {
  if (state.data?.questions) return state.data.questions;
  if (!state.questionsPromise) {
    state.questionsPromise = fetch("data/benchmark_questions.json", { cache: "no-store" }).then((r) => {
      if (!r.ok) throw new Error("failed to load benchmark_questions.json");
      return r.json();
    }).then((questions) => {
      state.data.questions = questions;
      return questions;
    }).finally(() => {
      state.questionsPromise = null;
    });
  }
  return state.questionsPromise;
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
  setupBenchQuestionControls();
  renderBenchmarks();
  renderModels();
  renderEvaluation();
  renderResults();

  window.addEventListener("hashchange", route);
  route();
}

/* ---------- routing ---------- */
function parseRoute() {
  const raw = (location.hash || "#home").slice(1);
  if (raw.startsWith("benchmark/")) {
    return { page: "benchmark-detail", name: decodeURIComponent(raw.slice("benchmark/".length)) };
  }
  const page = ROUTES.includes(raw) ? raw : "home";
  return { page, name: null };
}

function route() {
  const { page, name } = parseRoute();
  state.inspectName = name;
  $$(".page").forEach((p) => p.classList.toggle("active", p.id === "page-" + page));
  $$(".nav-link[data-route]").forEach((a) =>
    a.classList.toggle("active", a.dataset.route === (page === "benchmark-detail" ? "benchmarks" : page)));
  closeZoom();
  const bar = $("#bench-actions");
  if (bar) bar.style.display = page === "benchmarks" ? "" : "none";
  if (page === "benchmark-detail") renderBenchmarkDetail(name);
  window.scrollTo({ top: 0, behavior: "instant" in window ? "instant" : "auto" });
}

function benchesWithQuestions() {
  return new Set(
    (state.data.benchmarks || []).filter(hasBenchmarkQuestions).map((b) => b.name),
  );
}

function hasBenchmarkQuestions(b) {
  return Boolean(b?.has_questions || Number(b?.question_count || 0) > 0);
}

function questionsForBench(name) {
  return (state.data.questions || []).filter((q) => q.benchmark === name);
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
const authorDisplay = (b) => authorNamesFromBibtex(b.bibtex).join(", ");
const collator = new Intl.Collator(undefined, { numeric: true, sensitivity: "base" });
const textCompare = (a, b) => collator.compare(String(a || ""), String(b || ""));
const numericFrom = (s) => {
  const m = String(s || "").replace(/,/g, "").match(/\d+(?:\.\d+)?/);
  return m ? Number(m[0]) : null;
};
const yearFrom = (s) => {
  const years = String(s || "").match(/\b(?:19|20)\d{2}\b/g);
  return years ? Math.max(...years.map(Number)) : null;
};
const compareMaybeNumber = (a, b, dir) => {
  const av = a == null ? (dir === "asc" ? Infinity : -Infinity) : a;
  const bv = b == null ? (dir === "asc" ? Infinity : -Infinity) : b;
  return dir === "asc" ? av - bv : bv - av;
};

function setupBenchSearch() {
  let t;
  $("#bench-search").addEventListener("input", (e) => {
    clearTimeout(t);
    t = setTimeout(() => { state.benchQ = e.target.value.toLowerCase().trim(); renderBenchmarks(); }, 120);
  });
  $("#bench-sort").addEventListener("change", (e) => {
    state.benchSort = e.target.value;
    renderBenchmarks();
  });
  // delegated: in select mode a click anywhere on the box toggles selection;
  // otherwise it opens the zoom view. (The round circle is just an indicator.)
  const grid = $("#benchmarks");
  grid.addEventListener("click", (e) => {
    if (e.target.closest("a")) return;
    const inspect = e.target.closest("[data-inspect-benchmark]");
    if (inspect) {
      e.stopPropagation();
      location.hash = `benchmark/${encodeURIComponent(inspect.dataset.inspectBenchmark)}`;
      return;
    }
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
  const filtered = !q ? all : all.filter((b) =>
    [b.name, b.paper_title, b.domain, b.format, b.modalities, b.skills, b.sources, b.year]
      .join(" ").toLowerCase().includes(q));
  const rows = sortBenchmarks(filtered);
  $("#bench-count").textContent = `${rows.length} of ${all.length}`;
  $("#bench-empty").hidden = rows.length > 0;
  $("#benchmarks").innerHTML = rows.map((b) => {
    const kind = [b.domain, b.format].filter(Boolean).join(" · ");
    const on = state.selected.has(b.name);
    const hasQ = benchesWithQuestions().has(b.name);
    return `
    <article class="bench${on ? " selected" : ""}${hasQ ? " has-questions" : ""}" data-name="${esc(b.name)}">
      <label class="bench-select" data-name="${esc(b.name)}" title="Select for citation">
        <input type="checkbox" ${on ? "checked" : ""} aria-label="Select ${esc(b.name)}" />
      </label>
      <div class="bench-id">
        <h3>${esc(b.name)}</h3>
        <span class="year">${esc(b.year)}</span>
        ${kind ? `<span class="kind">${esc(kind)}</span>` : ""}
      </div>
      ${hasQ ? `<button class="inspect-icon bench-inspect" type="button" data-inspect-benchmark="${esc(b.name)}" aria-label="Inspect ${esc(b.name)} questions">${inspectIcon()}<span>inspect</span></button>` : ""}
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

function sortBenchmarks(rows) {
  const sorted = [...rows];
  sorted.sort((a, b) => {
    let cmp = 0;
    if (state.benchSort === "year-desc") cmp = compareMaybeNumber(yearFrom(a.year), yearFrom(b.year), "desc");
    else if (state.benchSort === "year-asc") cmp = compareMaybeNumber(yearFrom(a.year), yearFrom(b.year), "asc");
    else if (state.benchSort === "size-desc") cmp = compareMaybeNumber(numericFrom(a.size), numericFrom(b.size), "desc");
    else if (state.benchSort === "size-asc") cmp = compareMaybeNumber(numericFrom(a.size), numericFrom(b.size), "asc");
    if (!cmp) cmp = textCompare(a.name, b.name);
    return cmp;
  });
  return sorted;
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

function bibFieldValue(bibtex, fieldName) {
  const re = new RegExp(`\\b${fieldName}\\s*=\\s*`, "i");
  const match = re.exec(bibtex || "");
  if (!match) return "";
  let i = match.index + match[0].length;
  while (/\s/.test(bibtex[i] || "")) i += 1;
  const open = bibtex[i];
  if (open !== "{" && open !== '"') {
    const end = bibtex.indexOf(",", i);
    return (end === -1 ? bibtex.slice(i) : bibtex.slice(i, end)).trim();
  }
  const close = open === "{" ? "}" : '"';
  let depth = 0;
  let out = "";
  for (i += 1; i < bibtex.length; i += 1) {
    const ch = bibtex[i];
    if (open === "{" && ch === "{") {
      depth += 1;
      out += ch;
    } else if (ch === close) {
      if (depth === 0) break;
      depth -= 1;
      out += ch;
    } else {
      out += ch;
    }
  }
  return out.trim();
}

function splitBibtexAuthors(authors) {
  const parts = [];
  let depth = 0;
  let buf = "";
  for (let i = 0; i < authors.length; i += 1) {
    const rest = authors.slice(i);
    const ch = authors[i];
    if (ch === "{") depth += 1;
    if (ch === "}") depth = Math.max(0, depth - 1);
    if (depth === 0 && /^\s+and\s+/i.test(rest)) {
      if (buf.trim()) parts.push(buf.trim());
      buf = "";
      i += rest.match(/^\s+and\s+/i)[0].length - 1;
    } else {
      buf += ch;
    }
  }
  if (buf.trim()) parts.push(buf.trim());
  return parts;
}

function cleanLatexName(name) {
  return String(name || "")
    .replace(/\{\\[a-zA-Z]+\s+([^{}])\}/g, "$1")
    .replace(/\\[`'"\^~=.uvHkc]\s*\{?([^{}\s])\}?/g, "$1")
    .replace(/\\[a-zA-Z]+/g, "")
    .replace(/[{}]/g, "")
    .replace(/\s+/g, " ")
    .trim();
}

function formatAuthorName(name) {
  const clean = cleanLatexName(name);
  const parts = clean.split(",").map((part) => part.trim()).filter(Boolean);
  if (parts.length >= 2) return `${parts.slice(1).join(" ")} ${parts[0]}`.trim();
  return clean;
}

function authorNamesFromBibtex(bibtex) {
  const authors = bibFieldValue(bibtex, "author");
  if (!authors) return [];
  return splitBibtexAuthors(authors).map(formatAuthorName).filter(Boolean);
}

function exportBib() {
  const list = selectedBenchmarks();
  if (!list.length) return;
  const header = `% Citations for ${list.length} benchmark(s) — toward Artificial Musical Intelligence\n\n`;
  download("benchmarks.bib", header + list.map(bibFor).join("\n\n") + "\n", "application/x-bibtex");
}

async function copyText(text) {
  if (navigator.clipboard?.writeText && window.isSecureContext) {
    try {
      await navigator.clipboard.writeText(text);
      return true;
    } catch {}
  }
  const ta = document.createElement("textarea");
  ta.value = text;
  ta.setAttribute("readonly", "");
  ta.style.position = "fixed";
  ta.style.left = "-9999px";
  document.body.appendChild(ta);
  ta.select();
  const ok = document.execCommand("copy");
  ta.remove();
  return ok;
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
  const hasQ = benchesWithQuestions().has(b.name);
  return `
    <button class="zoom-close" type="button" data-close aria-label="Close">×</button>
    ${hasQ ? `<button class="inspect-icon zoom-inspect" type="button" data-zoom-inspect aria-label="Inspect ${esc(b.name)} questions">${inspectIcon()}<span>inspect</span></button>` : ""}
    <div class="bench-id">
      <h3>${esc(b.name)}</h3>
      <span class="year">${esc(b.year)}</span>
      ${kind ? `<span class="kind">${esc(kind)}</span>` : ""}
    </div>
    ${b.paper_title ? `<p class="paper">${esc(b.paper_title)}</p>` : ""}
    <div class="bench-fields">
      ${field("Modalities", b.modalities)}
      ${field("Size", formatSize(b.size))}
      ${field("Authors", authorDisplay(b), true)}
      ${field("Skills", b.skills, true)}
      ${field("Sources", b.sources, true)}
      ${field("Models", b.models, true)}
      ${b.links && b.links.length ? `<div class="field"><div class="k">Links</div><div class="bench-links">${linksHTML(b)}</div></div>` : ""}
    </div>
    <div class="zoom-actions">
      <button type="button" class="act" data-zoom-bib>Export .bib</button>
      <button type="button" class="act" data-zoom-py disabled title="Coming soon">Python download (coming soon)</button>
    </div>
    <pre class="cite-preview" role="button" tabindex="0" title="Click to copy citation" data-copy-cite>${esc(bibFor(b))}</pre>`;
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
  const citation = card.querySelector("[data-copy-cite]");
  if (citation) {
    const copyCitation = async () => {
      const original = citation.textContent;
      const ok = await copyText(bibFor(b));
      citation.classList.toggle("copied", ok);
      citation.textContent = ok ? `${original}\n\nCopied to clipboard.` : `${original}\n\nCould not copy.`;
      setTimeout(() => {
        citation.classList.remove("copied");
        citation.textContent = original;
      }, 1200);
    };
    citation.addEventListener("click", copyCitation);
    citation.addEventListener("keydown", (event) => {
      if (event.key !== "Enter" && event.key !== " ") return;
      event.preventDefault();
      copyCitation();
    });
  }
  const inspect = card.querySelector("[data-zoom-inspect]");
  if (inspect) {
    inspect.addEventListener("click", () => {
      closeZoom();
      location.hash = `benchmark/${encodeURIComponent(b.name)}`;
    });
  }
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
      <p class="rule-of-thumb-lede">Motivation</p>
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

        <p class="rule-of-thumb-lede">Rule of thumb</p>
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
  $("#prompts").innerHTML = (state.data.prompts || []).map((p) => {
    const variants = (p.variants || []).length
      ? `<div class="oeq-variants">${p.variants.map((v) => `
          <aside class="oeq-variant">
            <p class="rule-of-thumb-title">${esc(v.label)}</p>
            <pre>${esc(v.text)}</pre>
            ${v.example ? `<p class="oeq-example-label">Example built prompt</p><pre class="oeq-example">${esc(v.example)}</pre>` : ""}
          </aside>`).join("")}</div>`
      : "";
    const body = variants
      ? variants
      : (p.text ? `<pre class="prompt-example">${esc(p.text)}</pre>` : "");
    return `
    <div class="prompt">
      <div class="prompt-head">
        <div>
          <h4>${esc(p.name)}</h4>
          <p class="purpose">${esc(p.purpose)}</p>
        </div>
        <span class="chev"></span>
      </div>
      <div class="prompt-body">${body}</div>
    </div>`;
  }).join("");
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
  $("#model-sort").addEventListener("change", (e) => {
    state.modelSort = e.target.value;
    renderModels();
  });
  $("#models").addEventListener("click", (e) => {
    const card = e.target.closest(".framework-card");
    if (card) openModelZoom(card.dataset.id, card);
  });
}

function renderModels() {
  const all = state.data.models || [];
  const q = state.modelQ;
  const filtered = !q ? all : all.filter((m) =>
    [m.label, m.developer, m.year, m.paper_title, m.id]
      .join(" ").toLowerCase().includes(q));
  const rows = sortModels(filtered);
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

function sortModels(rows) {
  const sorted = [...rows];
  sorted.sort((a, b) => {
    let cmp = 0;
    if (state.modelSort === "year-desc") cmp = compareMaybeNumber(yearFrom(a.year), yearFrom(b.year), "desc");
    else if (state.modelSort === "year-asc") cmp = compareMaybeNumber(yearFrom(a.year), yearFrom(b.year), "asc");
    else if (state.modelSort === "developer-asc") cmp = textCompare(a.developer, b.developer);
    if (!cmp) cmp = textCompare(a.label, b.label);
    return cmp;
  });
  return sorted;
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

/* ---------- benchmark detail / inspect questions ---------- */
function setupBenchQuestionControls() {
  if (state.benchQControlsReady) return;
  state.benchQControlsReady = true;
  let t;
  $("#bench-q-search").addEventListener("input", (e) => {
    clearTimeout(t);
    t = setTimeout(() => {
      state.benchQFilters.q = e.target.value.toLowerCase().trim();
      renderBenchQuestions();
    }, 140);
  });
  document.addEventListener("click", (event) => {
    const target = event.target instanceof Element ? event.target : event.target?.parentElement;
    const audioButton = target?.closest("[data-load-audio]");
    if (audioButton) {
      loadQuestionAudio(audioButton);
      return;
    }
    const toggle = target?.closest(".pie-toggle");
    if (!toggle) return;
    const card = toggle.closest(".pie-card");
    if (!card) return;
    const expanded = card.classList.toggle("show-all");
    toggle.setAttribute("aria-expanded", String(expanded));
    toggle.textContent = expanded ? "show less" : "show all";
  });
}

async function renderBenchmarkDetail(name) {
  const b = benchByName(name);
  const head = $("#bench-detail-head");
  const meta = $("#bench-detail-meta");
  if (!b) {
    head.innerHTML = `<h1 class="display sm">Benchmark not found</h1>
      <p class="lede">No catalog entry for “${esc(name)}”.</p>`;
    meta.innerHTML = "";
    $("#bench-q-cards").innerHTML = "";
    $("#bench-q-count").textContent = "";
    $("#bench-q-empty").hidden = false;
    $("#bench-q-empty").textContent = "No questions available.";
    return;
  }
  if (!state.data.questions) {
    renderBenchmarkDetailLoading(b);
    try {
      await loadBenchmarkQuestions();
      if (state.inspectName === name) renderBenchmarkDetail(name);
    } catch (err) {
      $("#bench-q-empty").hidden = false;
      $("#bench-q-empty").textContent = "Could not load questions.";
      console.error(err);
    }
    return;
  }
  const kind = [b.domain, b.format].filter(Boolean).join(" · ");
  const nQ = questionsForBench(b.name).length;
  const benchRows = questionsForBench(b.name);
  head.innerHTML = `
    <h1 class="display sm">${esc(b.name)}</h1>
    <p class="lede">${esc(b.paper_title || b.extended || "")}</p>
    <p class="bench-detail-tags">
      ${b.year ? `<span class="year">${esc(b.year)}</span>` : ""}
      ${kind ? `<span class="kind">${esc(kind)}</span>` : ""}
      <span class="kind">${nQ} question${nQ === 1 ? "" : "s"}</span>
    </p>`;
  meta.innerHTML = `
    <div class="bench-fields">
      ${field("Modalities", b.modalities)}
      ${field("Size", formatSize(b.size))}
      ${field("Authors", authorDisplay(b), true)}
      ${field("Skills", b.skills, true)}
      ${field("Sources", b.sources, true)}
      ${b.links && b.links.length ? `<div class="field"><div class="k">Links</div><div class="bench-links">${linksHTML(b)}</div></div>` : ""}
    </div>
    ${categoryFilterHTML(benchRows)}
    <div id="bench-stat-fields" class="bench-fields stat-fields"></div>
    <div id="bench-chart-wrap"></div>`;
  state.benchQFilters = { q: "", categories: {} };
  setupBenchmarkCategoryFilters();
  $("#bench-q-search").value = "";
  renderBenchQuestions();
}

function renderBenchmarkDetailLoading(b) {
  const kind = [b.domain, b.format].filter(Boolean).join(" · ");
  const nQ = Number(b.question_count || 0);
  $("#bench-detail-head").innerHTML = `
    <h1 class="display sm">${esc(b.name)}</h1>
    <p class="lede">${esc(b.paper_title || b.extended || "")}</p>
    <p class="bench-detail-tags">
      ${b.year ? `<span class="year">${esc(b.year)}</span>` : ""}
      ${kind ? `<span class="kind">${esc(kind)}</span>` : ""}
      <span class="kind">${nQ ? `${nQ.toLocaleString()} question${nQ === 1 ? "" : "s"}` : "questions"}</span>
    </p>`;
  $("#bench-detail-meta").innerHTML = `
    <div class="bench-fields">
      ${field("Modalities", b.modalities)}
      ${field("Size", formatSize(b.size))}
      ${field("Authors", authorDisplay(b), true)}
      ${field("Skills", b.skills, true)}
      ${field("Sources", b.sources, true)}
      ${b.links && b.links.length ? `<div class="field"><div class="k">Links</div><div class="bench-links">${linksHTML(b)}</div></div>` : ""}
    </div>`;
  state.benchQFilters = { q: "", categories: {} };
  $("#bench-q-search").value = "";
  $("#bench-q-count").textContent = "Loading questions…";
  $("#bench-q-empty").hidden = false;
  $("#bench-q-empty").textContent = "Loading inspectable questions.";
  $("#bench-q-cards").innerHTML = "";
}

function categoryFilterHTML(rows) {
  const options = categoryOptions(rows);
  const dims = Object.entries(FILTER_LABELS).filter(([key]) => (options[key] || []).length);
  if (!dims.length) return "";
  return `
    <section class="slice-panel" aria-label="Benchmark filters">
      <div class="slice-groups">
        ${dims.map(([key, label]) => `
          <fieldset class="slice-group">
            <legend>${esc(label)}</legend>
            <div class="slice-options">
              ${options[key].map((value) => `
                <label class="slice-option">
                  <input class="slice-check" type="checkbox" data-dimension="${esc(key)}" value="${esc(value)}" />
                  <span>${esc(value)}</span>
                </label>`).join("")}
            </div>
          </fieldset>`).join("")}
      </div>
    </section>`;
}

function categoryOptions(rows) {
  const out = Object.fromEntries(Object.keys(FILTER_LABELS).map((key) => [key, new Set()]));
  rows.forEach((row) => {
    Object.keys(CATEGORY_LABELS).forEach((key) => {
      (row.categories?.[key] || []).forEach((value) => {
        if (value) out[key].add(value);
      });
    });
    const piac = knownPiac(row.piac);
    if (piac) out.piac.add(piac);
  });
  return Object.fromEntries(
    Object.entries(out).map(([key, values]) => [key, [...values].sort((a, b) => a.localeCompare(b))]),
  );
}

function setupBenchmarkCategoryFilters() {
  $$(".slice-check").forEach((input) => {
    input.addEventListener("change", () => {
      const categories = {};
      $$(".slice-check:checked").forEach((checked) => {
        const dim = checked.dataset.dimension;
        if (!dim) return;
        categories[dim] = categories[dim] || [];
        categories[dim].push(checked.value);
      });
      state.benchQFilters.categories = categories;
      renderBenchQuestions();
    });
  });
}

function computeQuestionStats(rows) {
  let distractorTotal = 0;
  const durations = [];
  rows.forEach((row) => {
    const distractorCount = (row.distractors || []).length;
    distractorTotal += distractorCount;
    (row.audio_duration_seconds || []).forEach((duration) => {
      const value = Number(duration);
      if (Number.isFinite(value)) durations.push(value);
    });
  });
  const sum = durations.reduce((acc, value) => acc + value, 0);
  return {
    n_questions: rows.length,
    average_audio_duration_seconds: durations.length ? sum / durations.length : null,
    average_distractors: rows.length ? distractorTotal / rows.length : 0,
    audio_duration_seconds: durations,
  };
}

function updateBenchmarkStats(rows) {
  const target = $("#bench-stat-fields");
  const charts = $("#bench-chart-wrap");
  const stats = computeQuestionStats(rows);
  if (target) target.innerHTML = `
    ${field("Questions", Number(stats.n_questions || 0).toLocaleString())}
    ${field("Avg audio", stats.average_audio_duration_seconds == null ? "unknown" : `${Number(stats.average_audio_duration_seconds).toFixed(1)}s`)}
    ${field("Avg distractors", Number(stats.average_distractors || 0).toFixed(2))}
  `;
  if (charts) charts.innerHTML = chartPanelHTML(rows, stats);
  setupPieInteractions();
}

function chartPanelHTML(rows, stats) {
  const charts = discreteDistributions(rows);
  const sound = soundDistributionCardHTML(stats);
  if (!charts.length && !sound) return "";
  return `<section class="pie-panel" aria-label="Category distributions">
    ${sound}
    ${charts.map(pieChartHTML).join("")}
  </section>`;
}

function soundDistributionCardHTML(stats) {
  const samples = (stats.audio_duration_seconds || []).map(Number).filter((value) => Number.isFinite(value));
  if (!samples.length) return "";
  return `
    <article class="pie-card sound-card" tabindex="0" data-sound-samples="${esc(JSON.stringify(samples))}">
      <h3>Sound duration</h3>
      ${soundHistogramHTML(samples, 8, 76)}
    </article>`;
}

function histogramBins(values, n) {
  if (!values.length) return [];
  const lo = Math.min(...values);
  const hi = Math.max(...values);
  if (lo === hi) return [{ min: lo, max: hi, count: values.length }];
  const width = (hi - lo) / n;
  const bins = Array.from({ length: n }, (_, i) => ({ min: lo + i * width, max: lo + (i + 1) * width, count: 0 }));
  values.forEach((value) => {
    const idx = Math.min(n - 1, Math.floor((value - lo) / width));
    bins[idx].count += 1;
  });
  return bins;
}

function durationLabel(value) {
  return value >= 60 ? `${(value / 60).toFixed(value >= 600 ? 0 : 1)}m` : `${value.toFixed(0)}s`;
}

function discreteDistributions(rows) {
  const specs = [
    { key: "distractors", label: "Distractors", values: (row) => [`${(row.distractors || []).length}`] },
    ...Object.entries(CATEGORY_LABELS).map(([key, label]) => ({
      key,
      label,
      values: (row) => row.categories?.[key] || [],
    })),
    { key: "piac", label: "PIAC", values: (row) => [knownPiac(row.piac)].filter(Boolean) },
  ];
  return specs.map((spec) => {
    const counts = {};
    rows.forEach((row) => {
      spec.values(row).forEach((value) => {
        if (value) counts[value] = (counts[value] || 0) + 1;
      });
    });
    const entries = Object.entries(counts)
      .sort((a, b) => b[1] - a[1] || textCompare(a[0], b[0]))
      .map(([label, count]) => ({ label, count }));
    return { ...spec, entries };
  }).filter((chart) => chart.entries.length);
}

function pieChartHTML(chart) {
  const total = chart.entries.reduce((sum, entry) => sum + entry.count, 0);
  if (!total) return "";
  const colors = ["#4A1523", "#6E2637", "#8C3B4B", "#A9576A", "#C77A8D", "#D9A2AE", "#5E5A52", "#8A867C"];
  const slices = chart.entries.length === 1
    ? `<circle class="pie-slice pie-full-slice" tabindex="0" cx="50" cy="50" r="42" fill="${colors[0]}" data-label="${esc(pieSliceLabel(chart.entries[0], total))}">
        <title>${esc(chart.entries[0].label)}: ${chart.entries[0].count} (100%)</title>
      </circle>`
    : (() => {
        let start = -90;
        return chart.entries.map((entry, i) => {
          const sweep = (entry.count / total) * 360;
          const path = pieSlicePath(50, 50, 42, start, start + sweep);
          start += sweep;
          return `<path class="pie-slice" tabindex="0" d="${path}" fill="${colors[i % colors.length]}" data-label="${esc(pieSliceLabel(entry, total))}">
            <title>${esc(entry.label)}: ${entry.count} (${Math.round(entry.count / total * 100)}%)</title>
          </path>`;
        }).join("");
      })();
  const hasExtra = chart.entries.length > 4;
  const legend = chart.entries.map((entry, i) => `
    <li${i >= 4 ? ` class="pie-extra"` : ""}>
      <span class="pie-swatch" style="--swatch:${colors[i % colors.length]}"></span>
      <span class="pie-label">${esc(entry.label)}</span>
      <span class="pie-count">${entry.count.toLocaleString()}</span>
    </li>`).join("");
  return `
    <article class="pie-card" data-chart="${esc(chart.key)}" tabindex="0">
      <h3>${esc(chart.label)}</h3>
      <div class="pie-body">
        <svg class="pie-svg" viewBox="0 0 100 100" role="img" aria-label="${esc(chart.label)} distribution">
          ${slices}
          <circle class="pie-hole" cx="50" cy="50" r="22"></circle>
        </svg>
        <div class="pie-legend-wrap">
          <div class="pie-tip" aria-live="polite"></div>
          <ul class="pie-legend">${legend}</ul>
          ${hasExtra ? `<button class="pie-toggle" type="button" data-chart="${esc(chart.key)}" aria-expanded="false">show all</button>` : ""}
        </div>
      </div>
    </article>`;
}

function pieSliceLabel(entry, total) {
  return `${entry.label}: ${entry.count.toLocaleString()} (${Math.round(entry.count / total * 100)}%)`;
}

function setupPieInteractions() {
  $$(".pie-card").forEach((card) => {
    if (card.classList.contains("sound-card")) {
      setupSoundCard(card);
      return;
    }
    card.addEventListener("click", (event) => {
      if (event.target.closest(".pie-toggle")) return;
      openPieZoom(card);
    });
    card.addEventListener("keydown", (event) => {
      if (event.key !== "Enter" && event.key !== " ") return;
      if (event.target.closest(".pie-toggle")) return;
      event.preventDefault();
      openPieZoom(card);
    });
    card.querySelectorAll(".pie-slice").forEach((slice) => {
      const show = () => setPieTip(card, slice.dataset.label || "");
      const hide = () => setPieTip(card, "");
      slice.addEventListener("mouseenter", show);
      slice.addEventListener("focus", show);
      slice.addEventListener("mouseleave", hide);
      slice.addEventListener("blur", hide);
    });
  });
}

function setupSoundCard(card) {
  card.addEventListener("click", () => openSoundZoom(card));
  card.addEventListener("keydown", (event) => {
    if (event.key !== "Enter" && event.key !== " ") return;
    event.preventDefault();
    openSoundZoom(card);
  });
}

function setPieTip(card, text) {
  const tip = card.querySelector(".pie-tip");
  if (tip) tip.textContent = text;
}

function openPieZoom(card) {
  const clone = card.cloneNode(true);
  clone.classList.add("pie-card-zoom", "show-all");
  clone.querySelectorAll(".pie-toggle").forEach((button) => button.remove());
  const html = `
    <button class="zoom-close" type="button" data-close aria-label="Close">×</button>
    ${clone.outerHTML}`;
  flipZoom(html, card);
  const zoomCard = $("#zoom-card .pie-card-zoom");
  if (zoomCard) {
    zoomCard.querySelectorAll(".pie-slice").forEach((slice) => {
      const show = () => setPieTip(zoomCard, slice.dataset.label || "");
      const hide = () => setPieTip(zoomCard, "");
      slice.addEventListener("mouseenter", show);
      slice.addEventListener("focus", show);
      slice.addEventListener("mouseleave", hide);
      slice.addEventListener("blur", hide);
    });
  }
}

function openSoundZoom(card) {
  let samples = [];
  try {
    samples = JSON.parse(card.dataset.soundSamples || "[]");
  } catch {
    samples = [];
  }
  const html = `
    <button class="zoom-close" type="button" data-close aria-label="Close">×</button>
    <article class="pie-card sound-card sound-card-zoom" data-sound-samples="${esc(JSON.stringify(samples))}">
      <h3>Sound duration</h3>
      <label class="bin-control">Bins
        <input id="sound-zoom-bins" type="range" min="4" max="32" step="1" value="18" />
        <span id="sound-zoom-bin-value">18</span>
      </label>
      <div id="sound-zoom-hist">${soundHistogramHTML(samples, 18, 180)}</div>
    </article>`;
  flipZoom(html, card);
  setupSoundZoomControls();
}

function soundHistogramHTML(samples, nBins, maxHeight = 180) {
  const values = samples.map(Number).filter((value) => Number.isFinite(value));
  if (!values.length) return "";
  const bins = histogramBins(values, nBins);
  const maxCount = Math.max(...bins.map((bin) => bin.count), 1);
  const bars = bins.map((bin) => {
    const h = Math.max(2, (bin.count / maxCount) * maxHeight);
    const range = `${durationLabel(bin.min)}-${durationLabel(bin.max)}`;
    const label = `${range}: ${bin.count}`;
    return `<div class="mini-bar" style="--h:${h.toFixed(1)}px" title="${esc(label)}" data-label="${esc(label)}">
      <span>${bin.count}</span>
      <b>${esc(range)}</b>
    </div>`;
  }).join("");
  return `
    <div class="mini-hist" role="img" aria-label="Sound duration distribution">${bars}</div>
    <div class="mini-axis">${bins.map((bin) => `<span>${esc(durationLabel(bin.min))}</span>`).join("")}</div>`;
}

function setupSoundZoomControls() {
  const card = $("#zoom-card .sound-card-zoom");
  const input = $("#sound-zoom-bins");
  const value = $("#sound-zoom-bin-value");
  const target = $("#sound-zoom-hist");
  if (!card || !input || !target) return;
  let samples = [];
  try {
    samples = JSON.parse(card.dataset.soundSamples || "[]");
  } catch {
    samples = [];
  }
  const redraw = () => {
    const bins = Number(input.value || 18);
    if (value) value.textContent = String(bins);
    target.innerHTML = soundHistogramHTML(samples, bins, 180);
  };
  input.addEventListener("input", redraw);
}

function pieSlicePath(cx, cy, r, startDeg, endDeg) {
  const start = polarToCartesian(cx, cy, r, endDeg);
  const end = polarToCartesian(cx, cy, r, startDeg);
  const largeArc = endDeg - startDeg > 180 ? 1 : 0;
  return `M ${cx} ${cy} L ${start.x} ${start.y} A ${r} ${r} 0 ${largeArc} 0 ${end.x} ${end.y} Z`;
}

function polarToCartesian(cx, cy, r, deg) {
  const rad = (deg - 90) * Math.PI / 180;
  return { x: cx + r * Math.cos(rad), y: cy + r * Math.sin(rad) };
}

function renderBenchQuestions() {
  const name = state.inspectName;
  const { q, categories } = state.benchQFilters;
  const all = questionsForBench(name);
  const list = all.filter((row) => {
    for (const [dimension, selected] of Object.entries(categories || {})) {
      if (!selected.length) continue;
      const values = dimension === "piac" ? [knownPiac(row.piac)].filter(Boolean) : (row.categories?.[dimension] || []);
      if (!selected.some((value) => values.includes(value))) return false;
    }
    if (q) {
      const hay = [row.question, row.correct_answer, row.skills, row.answer_format,
        ...(row.distractors || [])].join(" ").toLowerCase();
      if (!hay.includes(q)) return false;
    }
    return true;
  });
  updateBenchmarkStats(list);
  $("#bench-q-count").textContent = `${list.length} of ${all.length}`;
  $("#bench-q-empty").hidden = list.length > 0;
  $("#bench-q-empty").textContent = all.length
    ? "No questions match."
    : "Questions for this benchmark are not loaded on the site yet.";
  $("#bench-q-cards").innerHTML = list.map(benchQuestionHTML).join("");
}

function benchQuestionHTML(row) {
  const audio = row.audio
    ? `<div class="audio-lazy"><button class="audio-load" type="button" data-load-audio="${esc(row.audio)}">Play audio</button></div>`
    : `<div class="no-audio">audio unavailable for this clip</div>`;
  const meta = questionCategoryMeta(row);
  const piac = knownPiac(row.piac);
  const distractors = (row.distractors || []).length
    ? `<p class="ref muted"><b>Distractors:</b> ${row.distractors.map(esc).join(" · ")}</p>`
    : "";
  const fmt = row.answer_format
    ? `<p class="ref muted"><b>Answer format:</b> ${esc(row.answer_format)}</p>`
    : "";
  return `
  <article class="qcard">
    <div class="qcard-top">
      <p class="q">${esc(row.question)}</p>
      ${piac ? `<span class="pill ${piac}">${esc(piac)}</span>` : ""}
    </div>
    <div class="qmeta">${meta}</div>
    ${audio}
    <p class="ref"><b>Reference:</b> ${esc(row.correct_answer)}</p>
    ${fmt}
    ${distractors}
  </article>`;
}

function loadQuestionAudio(button) {
  const src = button.dataset.loadAudio;
  if (!src) return;
  const audio = document.createElement("audio");
  audio.controls = true;
  audio.preload = "none";
  audio.src = src;
  button.replaceWith(audio);
  audio.play().catch(() => {});
}

function questionCategoryMeta(row) {
  const parts = Object.entries(CATEGORY_LABELS).map(([key, label]) => {
    const values = row.categories?.[key] || [];
    return values.length ? `${label}: ${values.map(esc).join(", ")}` : "";
  }).filter(Boolean);
  if (!parts.length) {
    return [row.category_2, row.category_3, row.skills ? "Skill: " + row.skills : ""]
      .filter(Boolean).map(esc).join(" · ");
  }
  return parts.join(" · ");
}
