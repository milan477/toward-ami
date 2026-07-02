"use strict";

const MODEL_COLORS = { "af-next": "#0071e3", "gemini": "#8944ab" };
const PIAC = ["perceptual", "inferential", "affective", "contextual"];
const state = { data: null, model: null, filters: { q: "", piac: "", result: "" } };

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
const pct = (x) => (x == null ? "–" : (x * 100).toFixed(1) + "%");
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

init();

async function init() {
  const res = await fetch("data.json");
  const data = await res.json();
  state.data = data;
  state.model = data.models[0].id;

  $("#ov-n").textContent = data.n_questions;
  $("#gen-date").textContent = (data.generated || "").slice(0, 10);

  setupTabs();
  renderOverview();
  setupBrowseControls();
  renderCards();
  renderPrompts();
}

/* ---------- tabs ---------- */
function setupTabs() {
  $$("#tabs .tab").forEach((btn) => {
    btn.addEventListener("click", () => {
      $$("#tabs .tab").forEach((b) => b.classList.remove("active"));
      $$(".panel").forEach((p) => p.classList.remove("active"));
      btn.classList.add("active");
      $("#tab-" + btn.dataset.tab).classList.add("active");
      window.scrollTo({ top: 0, behavior: "smooth" });
    });
  });
}

/* ---------- overview ---------- */
function renderOverview() {
  const { models, overview } = state.data;
  $("#overview-cards").innerHTML = models.map((m) => {
    const o = overview[m.id];
    const gap = o.mcq_acc - o.oeq_acc;
    const color = MODEL_COLORS[m.id] || "#0071e3";
    return `
    <div class="ov-card">
      <h3><span class="model-dot" style="background:${color}"></span>${esc(m.label)}</h3>
      <div class="metrics">
        <div class="metric">
          <div class="val">${pct(o.mcq_acc)}</div><div class="lab">MCQ accuracy (apparent)</div>
          <div class="bar"><span style="width:${o.mcq_acc * 100}%;background:${color}"></span></div>
        </div>
        <div class="metric">
          <div class="val">${pct(o.oeq_acc)}</div><div class="lab">OEQ accuracy (actual)</div>
          <div class="bar"><span style="width:${o.oeq_acc * 100}%;background:${color}"></span></div>
        </div>
        <div class="metric gap">
          <div class="val">${(gap * 100).toFixed(1)}pt</div><div class="lab">MCQ − OEQ gap</div>
        </div>
        <div class="metric halluc">
          <div class="val">${pct(o.halluc_rate)}</div><div class="lab">OEQ hallucination rate</div>
        </div>
      </div>
      <div class="metric" style="margin-top:14px">
        <div class="lab">OEQ mean judge score (0–1): <b style="color:var(--text)">${o.oeq_mean.toFixed(3)}</b> · n=${o.n}</div>
      </div>
    </div>`;
  }).join("");

  renderPiacTable();
}

function renderPiacTable() {
  const { models, overview } = state.data;
  const head = `<thead><tr>
      <th>PIAC category</th><th>Model</th>
      <th class="num">n</th><th class="num">MCQ</th><th class="num">OEQ</th>
      <th class="num">gap</th><th class="num">OEQ mean</th><th class="num">halluc.</th>
    </tr></thead>`;
  let body = "<tbody>";
  for (const cat of PIAC) {
    const rows = models.map((m) => [m, overview[m.id].by_piac[cat]]).filter(([, r]) => r);
    if (!rows.length) continue;
    rows.forEach(([m, r], i) => {
      const gap = r.mcq_acc - r.oeq_acc;
      body += `<tr>
        ${i === 0 ? `<td class="cat-cell" rowspan="${rows.length}"><span class="pill ${cat}">${cat}</span></td>` : ""}
        <td>${esc(m.label)}</td>
        <td class="num">${r.n}</td>
        <td class="num">${pct(r.mcq_acc)}</td>
        <td class="num">${pct(r.oeq_acc)}</td>
        <td class="num" style="color:var(--warn)">${(gap * 100).toFixed(0)}pt</td>
        <td class="num">${r.oeq_mean.toFixed(2)}</td>
        <td class="num" style="color:var(--bad)">${pct(r.halluc_rate)}</td>
      </tr>`;
    });
  }
  body += "</tbody>";
  $("#piac-table").innerHTML = head + body;
}

/* ---------- browse ---------- */
function setupBrowseControls() {
  const ms = $("#model-select");
  ms.innerHTML = state.data.models.map((m) => `<option value="${m.id}">${esc(m.label)}</option>`).join("");
  ms.value = state.model;
  ms.addEventListener("change", () => { state.model = ms.value; renderCards(); });

  const pf = $("#piac-filter");
  pf.innerHTML = `<option value="">all</option>` + PIAC.map((c) => `<option value="${c}">${c}</option>`).join("");
  pf.addEventListener("change", () => { state.filters.piac = pf.value; renderCards(); });

  $("#result-filter").addEventListener("change", (e) => { state.filters.result = e.target.value; renderCards(); });

  let t;
  $("#search").addEventListener("input", (e) => {
    clearTimeout(t);
    t = setTimeout(() => { state.filters.q = e.target.value.toLowerCase().trim(); renderCards(); }, 140);
  });
}

function matchesResult(cell, mode) {
  if (!mode) return true;
  const oeqRight = (cell.oeq_score ?? 0) >= 0.5;
  switch (mode) {
    case "halluc": return cell.hallucinated;
    case "mcqRight-oeqWrong": return cell.mcq_correct && !oeqRight;
    case "both-right": return cell.mcq_correct && oeqRight;
    case "both-wrong": return !cell.mcq_correct && !oeqRight;
    default: return true;
  }
}

function renderCards() {
  const { q, piac, result } = state.filters;
  const mid = state.model;
  const list = state.data.questions.filter((row) => {
    if (piac && row.piac !== piac) return false;
    if (!matchesResult(row[mid], result)) return false;
    if (q) {
      const hay = [row.question, row.correct_answer, row.skills, row[mid].oeq_response,
        row[mid].mcq_pred, row.qid].join(" ").toLowerCase();
      if (!hay.includes(q)) return false;
    }
    return true;
  });

  $("#browse-count").textContent = `${list.length} of ${state.data.questions.length}`;
  $("#empty").hidden = list.length > 0;
  $("#cards").innerHTML = list.map((row) => cardHTML(row, mid)).join("");
  $$(".model-picker select").forEach((sel) => sel.addEventListener("change", onCardModelChange));
}

function cardHTML(row, mid) {
  const cell = row[mid];
  const audio = row.audio
    ? `<audio controls preload="none" src="${esc(row.audio)}"></audio>`
    : `<div class="no-audio">audio unavailable for this clip</div>`;
  const layers = [row.category_2, row.category_3].filter(Boolean)
    .map((c) => `<span class="tag">${esc(c)}</span>`).join("");
  const opts = state.data.models.map((m) =>
    `<option value="${m.id}"${m.id === mid ? " selected" : ""}>${esc(m.label)}</option>`).join("");

  return `
  <article class="qcard" data-qid="${esc(row.qid)}">
    <div class="qcard-top">
      <p class="qtext">${esc(row.question)}</p>
      <span class="pill ${row.piac}">${row.piac || "?"}</span>
    </div>
    <div class="qmeta">
      ${layers}
      ${row.skills ? `<span class="tag">skill: ${esc(row.skills)}</span>` : ""}
      <span class="qid mono">${esc(row.qid)}</span>
    </div>
    ${audio}
    <div class="answer-block">
      <p class="ref"><b>Reference answer:</b> ${esc(row.correct_answer)}</p>
      <div class="model-picker">
        <label style="color:var(--muted);font-size:12px;font-weight:600">Model answers</label>
        <select data-role="card-model">${opts}</select>
      </div>
      <div class="answer-body">${answerHTML(cell)}</div>
    </div>
  </article>`;
}

function answerHTML(cell) {
  const oeqRight = (cell.oeq_score ?? 0) >= 0.5;
  const scoreColor = cell.oeq_score == null ? "var(--muted)"
    : cell.oeq_score >= 0.5 ? "rgba(63,185,80,.18)" : "rgba(248,81,73,.16)";
  const scoreTxt = cell.oeq_score == null ? "–" : cell.oeq_score.toFixed(2);
  return `
    <div class="ans-grid">
      <div class="k">MCQ</div>
      <div class="v">
        <span class="verdict ${cell.mcq_correct ? "ok" : "no"}">${cell.mcq_correct ? "✓" : "✗"} ${esc(cell.mcq_pred || "—")}</span>
      </div>
      <div class="k">Open-ended</div>
      <div class="v">
        <span class="verdict ${oeqRight ? "ok" : "no"}">${oeqRight ? "✓" : "✗"}</span>
        <span class="score-chip" style="background:${scoreColor}">score ${scoreTxt}</span>
        ${cell.hallucinated ? `<span class="halluc-flag">⚠ hallucinated${cell.hallucination_level && cell.hallucination_level !== "none" ? " · " + esc(cell.hallucination_level) : ""}</span>` : ""}
        <p class="v" style="margin-top:6px">${esc(cell.oeq_response || "(no answer)")}</p>
        ${cell.rationale ? `<p class="rationale">judge: ${esc(cell.rationale)}</p>` : ""}
      </div>
    </div>`;
}

function onCardModelChange(e) {
  const card = e.target.closest(".qcard");
  const row = state.data.questions.find((r) => r.qid === card.dataset.qid);
  $(".answer-body", card).innerHTML = answerHTML(row[e.target.value]);
}

/* ---------- prompts ---------- */
function renderPrompts() {
  $("#prompts-list").innerHTML = state.data.prompts.map((p, i) => `
    <div class="prompt-card${i === 0 ? " open" : ""}">
      <div class="prompt-head" data-idx="${i}">
        <div>
          <h3>${esc(p.name)}</h3>
          <p class="purpose">${esc(p.purpose)}</p>
        </div>
        <span class="chev">▶</span>
      </div>
      <div class="prompt-body"><pre>${esc(p.text)}</pre></div>
    </div>`).join("");
  $$("#prompts-list .prompt-head").forEach((h) =>
    h.addEventListener("click", () => h.closest(".prompt-card").classList.toggle("open")));
}
