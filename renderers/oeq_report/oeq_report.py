"""Generate a self-contained HTML viewer for exp-0 MCQ + OEQ results.

Reads ``summary.csv`` from an ``exp_7_mcq_oeq/.../<date>/oeq`` run directory
(and merges its sibling MCQ summary). Legacy ``*_summary.csv`` runs remain
supported. Open with ``--serve`` to play local audio from ``data/audio/``.

Usage:
    python renderers/oeq_report/oeq_report.py --serve
    python renderers/oeq_report/oeq_report.py results/exp_7_mcq_oeq/mmar/gemini-3-flash-preview/2026-07-18_17-37-06/oeq/summary.csv --serve
    python renderers/oeq_report/oeq_report.py path/to/summary.csv -o view.html
"""

import argparse
import contextlib
import csv
import glob
import json
import re
import socket
import sys
from functools import lru_cache
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

ROOT = Path(__file__).resolve().parents[2]
AUDIO_ROOT = ROOT / "data" / "audio"
# Prefer dated experiment runs, then fall back to the older variant layout.
DEFAULT_GLOBS = [
    str(ROOT / "results" / "exp_7_mcq_oeq" / "*" / "*" / "*" / "oeq" / "summary.csv"),
    str(ROOT / "results" / "mcq-oeq" / "*" / "*" / "*-oeq" / "*_summary.csv"),
    str(ROOT / "results" / "mcq-oeq" / "*" / "*" / "*-oeq-piac" / "*_summary.csv"),
    str(ROOT / "results" / "*" / "*" / "*-oeq-piac" / "*_summary.csv"),
]
AUDIO_EXTS = {".wav", ".mp3", ".flac", ".ogg", ".m4a", ".opus"}
MIME = {".wav": "audio/wav", ".mp3": "audio/mpeg", ".flac": "audio/flac",
        ".ogg": "audio/ogg", ".m4a": "audio/mp4", ".opus": "audio/opus"}


@lru_cache(maxsize=None)
def _audio_index() -> dict[str, Path]:
    """Map audio basename and stem → file path, recursively under data/audio."""
    idx: dict[str, Path] = {}
    if AUDIO_ROOT.exists():
        for p in AUDIO_ROOT.rglob("*"):
            if p.is_file() and p.suffix.lower() in AUDIO_EXTS:
                idx.setdefault(p.name, p)
                idx.setdefault(p.stem, p)
    return idx


def _resolve_audio(name: str) -> Path | None:
    idx = _audio_index()
    return idx.get(name) or idx.get(name.rsplit(".", 1)[0])

COLUMNS = ["qid", "category", "category_1", "category_2", "category_3", "category_4", "question",
           "answer_format", "example_answer", "prompt", "reference_answer",
           "response", "judge_score", "judge_score_norm", "judge_confidence",
           "judge_rationale",
           "skipped", "error"]


def _result_date(path: str) -> str:
    result = Path(path)
    if result.name == "summary.csv" and result.parent.name == "oeq":
        return result.parent.parent.name
    return result.name.split("_summary.csv")[0]


def available_summary_files() -> list[Path]:
    """Return every OEQ summary understood by this renderer."""
    matches: set[str] = set()
    for pattern in DEFAULT_GLOBS:
        matches.update(glob.glob(pattern))
    return [Path(path) for path in sorted(matches, key=lambda path: (_result_date(path), path))]


def load_rows(csv_path: Path) -> list[dict]:
    with csv_path.open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    mcq_by_qid = _load_sibling_mcq(csv_path)
    if not mcq_by_qid:
        return rows
    for row in rows:
        mcq = mcq_by_qid.get(row.get("qid", ""), {})
        if not mcq:
            continue
        row.setdefault("mcq_pred_letter", mcq.get("pred_letter", ""))
        row.setdefault("mcq_pred", mcq.get("pred_answer", ""))
        row.setdefault("mcq_correct", mcq.get("correct", ""))
        row.setdefault("mcq_response", mcq.get("response", ""))
        row.setdefault("mcq_prompt", mcq.get("prompt", ""))
        if not row.get("audio") and mcq.get("audio"):
            row["audio"] = mcq["audio"]
    return rows


def _load_sibling_mcq(oeq_csv: Path) -> dict[str, dict]:
    """Pull the matching MCQ summary from the same logical run."""
    parent = oeq_csv.parent
    name = parent.name
    if name == "oeq" and oeq_csv.name == "summary.csv":
        mcq_dir = parent.parent / "mcq"
        candidates = [mcq_dir / "summary.csv"]
    elif name.endswith(("-oeq-piac", "-oeq")):
        suffix = "-oeq-piac" if name.endswith("-oeq-piac") else "-oeq"
        base = name[: -len(suffix)]
        mcq_dir = parent.parent / base
        stamp = oeq_csv.name.split("_summary.csv")[0]
        candidates = [
            mcq_dir / f"{stamp}_summary.csv",
            *sorted(mcq_dir.glob("*_summary.csv")),
        ]
    else:
        return {}
    if not mcq_dir.is_dir():
        return {}
    for path in candidates:
        if path.exists():
            with path.open(encoding="utf-8") as f:
                return {r["qid"]: r for r in csv.DictReader(f) if r.get("qid")}
    return {}


HTML_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>OEQ results — __TITLE__</title>
<style>
  :root {
    color-scheme:light;
    --bg:#f4f6f8; --panel:#ffffff; --line:#d9dee7; --txt:#18202b; --muted:#667085;
    --accent:#2563eb;
  }
  * { box-sizing:border-box; }
  html, body { height:100%; }
  body { margin:0; background:var(--bg); color:var(--txt); display:flex;
         flex-direction:column;
         font:14px/1.45 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif; }
  header { padding:14px 18px; border-bottom:1px solid var(--line); background:var(--panel);
           flex:0 0 auto; }
  h1 { margin:0 0 6px; font-size:16px; }
  .sub { color:var(--muted); font-size:12px; }
  .stats { display:flex; flex-wrap:wrap; gap:14px; margin-top:10px; }
  .stat { background:#f8fafc; border:1px solid var(--line); border-radius:8px;
          padding:6px 10px; font-size:12px; }
  .stat b { font-size:15px; color:var(--accent); }
  .dist { display:flex; gap:4px; align-items:flex-end; height:34px; }
  .bar { width:22px; border-radius:3px 3px 0 0; background:var(--accent); position:relative; }
  .bar span { position:absolute; top:-15px; left:0; right:0; text-align:center;
              font-size:10px; color:var(--muted); }
  .bar small { position:absolute; bottom:-15px; left:0; right:0; text-align:center;
               font-size:10px; color:var(--muted); }
  .controls { display:flex; flex-wrap:wrap; gap:8px; padding:10px 18px;
              border-bottom:1px solid var(--line); background:var(--panel);
              flex:0 0 auto; }
  input,select { background:#fff; color:var(--txt); border:1px solid var(--line);
                 border-radius:6px; padding:6px 8px; font-size:13px; }
  input#q { flex:1; min-width:220px; }
  input#summaryFile { min-width:360px; }
  .file-button { background:var(--accent); color:#fff; border-radius:6px; padding:6px 10px;
                 font-size:13px; cursor:pointer; white-space:nowrap; }
  .file-button:hover { filter:brightness(.94); }
  .column-picker { position:relative; }
  .column-picker summary { background:#fff; color:var(--txt); border:1px solid var(--line);
                           border-radius:6px; padding:6px 9px; font-size:13px; cursor:pointer;
                           list-style:none; white-space:nowrap; }
  .column-picker summary::-webkit-details-marker { display:none; }
  .column-picker summary::after { content:" ▾"; color:var(--muted); }
  .column-picker[open] summary::after { content:" ▴"; }
  .column-menu { position:absolute; right:0; z-index:10; margin-top:5px; width:260px;
                 max-height:420px; overflow:auto; padding:9px; background:#fff;
                 border:1px solid var(--line); border-radius:8px;
                 box-shadow:0 12px 28px #10182822; }
  .column-actions { display:flex; gap:6px; padding-bottom:7px; margin-bottom:5px;
                    border-bottom:1px solid var(--line); }
  .column-actions button { background:#f8fafc; color:var(--accent); border:1px solid var(--line);
                           border-radius:5px; padding:4px 7px; cursor:pointer; font-size:11px; }
  .column-option { display:flex; gap:7px; align-items:center; padding:4px 3px;
                   color:var(--muted); cursor:pointer; font-size:12px; }
  .column-option:hover { color:var(--txt); }
  .count { color:var(--muted); font-size:12px; align-self:center; margin-left:auto; }
  .wrap { overflow:auto; flex:1 1 auto; min-height:0; }
  table { border-collapse:collapse; width:100%; }
  th,td { border-bottom:1px solid var(--line); padding:8px 10px; text-align:left;
          vertical-align:top; }
  th { position:sticky; top:0; background:#eef2f7; cursor:pointer; white-space:nowrap;
       font-size:12px; user-select:none; }
  th:hover { color:var(--accent); }
  th .arrow { color:var(--accent); font-size:10px; }
  tr:hover td { background:#f8fafc; }
  td.q, td.ref, td.resp, td.rat { min-width:200px; max-width:360px; }
  td.prompt { min-width:240px; max-width:380px; white-space:pre-wrap;
              font-size:11.5px; color:var(--muted); }
  td.aud { width:236px; }
  td.aud audio { width:230px; height:32px; }
  td.aud .noaudio { color:var(--muted); font-size:11px; }
  td.qid { font-family:ui-monospace,monospace; font-size:11px; color:var(--muted);
           white-space:nowrap; }
  .cat { font-size:11px; color:var(--muted); white-space:nowrap; }
  .score { display:inline-block; min-width:22px; text-align:center; border-radius:6px;
           padding:2px 7px; font-weight:600; color:#0b0d12; }
  .s0{background:#e5534b;} .s1{background:#e0833b;} .s2{background:#d9b441;}
  .s3{background:#9fd356;} .s4{background:#54c98a;} .sx{background:#e5e7eb; color:#475467;}
  .err { color:#e5534b; font-size:11px; }
  tr.hall td { box-shadow: inset 3px 0 0 #e5534b; }
  .hbadge { background:#e5534b; color:#0b0d12; border-radius:6px; padding:1px 7px;
            font-weight:600; font-size:11px; }
  .muted2 { color:var(--muted); font-size:11px; }
  td.long { cursor:zoom-in; }
  td.long .text { display:-webkit-box; overflow:hidden; -webkit-box-orient:vertical;
                  -webkit-line-clamp:3; white-space:pre-wrap; }
  td.long.expanded { cursor:zoom-out; }
  td.long.expanded .text { display:block; overflow:visible; }
  td.oeq-answer { min-width:220px; max-width:420px; white-space:pre-wrap; }
  td.oeq-answer .text { display:block; overflow:visible; }
  mark { background:#dbeafe; color:#1e3a8a; }
  .empty { padding:40px; text-align:center; color:var(--muted); }
  @media (min-width:1600px) {
    header { display:grid; grid-template-columns:minmax(280px, .7fr) minmax(0, 2fr);
             gap:18px; align-items:center; padding:8px 12px; }
    h1 { margin-bottom:2px; }
    .stats { margin-top:0; gap:6px; align-items:center; }
    .stat { padding:4px 7px; }
    .stat b { font-size:13px; }
    .controls { padding:6px 12px; gap:6px; }
    input, select { padding:4px 6px; font-size:12px; }
    th, td { padding:4px 6px; }
    td.q, td.ref, td.resp, td.rat { min-width:180px; max-width:280px; }
    td.prompt { min-width:200px; max-width:300px; }
    td.aud { width:176px; }
    td.aud audio { width:170px; height:28px; }
  }
</style>
</head>
<body>
<header>
  <div class="heading">
    <h1>Exp 0 — MCQ + OEQ results</h1>
    <div class="sub" id="subtitle">__SUBTITLE__</div>
  </div>
  <div class="stats" id="stats"></div>
</header>
<div class="controls">
  <input id="summaryFile" type="search" list="summaryFileOptions"
         placeholder="Search summary files…" title="Search by benchmark, model, timestamp, or path">
  <datalist id="summaryFileOptions"></datalist>
  <label class="file-button" for="localSummaryFiles">Open CSV files…</label>
  <input id="localSummaryFiles" type="file" accept=".csv,text/csv" multiple hidden>
  <input id="q" type="search" placeholder="Search all fields…">
  <select id="piac"></select>
  <select id="c1"></select>
  <select id="c2"></select>
  <select id="c3"></select>
  <select id="score">
    <option value="">any score</option>
    <option value="0">0</option><option value="1">1</option>
    <option value="x">unscored</option>
  </select>
  <select id="confidence"></select>
  <details class="column-picker" id="columnPicker">
    <summary>other columns <span id="extraCount"></span></summary>
    <div class="column-menu">
      <div class="column-actions">
        <button type="button" id="showAllColumns">show all</button>
        <button type="button" id="hideExtraColumns">hide extras</button>
      </div>
      <div id="extraColumns"></div>
    </div>
  </details>
  <span class="count" id="count"></span>
</div>
<div class="wrap">
  <table>
    <thead><tr id="head"></tr></thead>
    <tbody id="body"></tbody>
  </table>
  <div class="empty" id="empty" style="display:none">No rows match.</div>
</div>
<script>
let ROWS = __DATA__;
let COLS = __COLS__;
const SUMMARY_FILES = __SUMMARY_FILES__;
const CURRENT_SUMMARY = __CURRENT_SUMMARY__;
const LABELS = {qid:"qid", category:"PIAC", skills:"skills", category_1:"cat1", category_2:"cat2", category_3:"cat3",
  question:"question", answer_format:"answer format", example_answer:"example",
  prompt:"full prompt to ALM", reference_answer:"reference", response:"answer OEQ",
  mcq_response:"raw answer MCQ", mcq_pred_letter:"letter answer MCQ",
  mcq_pred:"prediction MCQ", mcq_correct:"result MCQ", mcq_prompt:"MCQ prompt",
  judge_score:"score", judge_score_norm:"norm", verdict:"verdict",
  judge_confidence:"confidence", judge_rationale:"rationale",
  skipped:"skipped", error:"error"};
const TRUTHY = v => /^(true|1|yes)$/i.test((v??"").toString().trim());
const LONG = new Set(["question","prompt","reference_answer","mcq_response","judge_rationale"]);
const ESSENTIAL_COLS = ["question","reference_answer","response","mcq_pred","mcq_correct"];
const EXTRA_COLS = new Set();
let sortCol = "qid", sortDir = 1;

function uniq(col){ return [...new Set(ROWS.map(r=>r[col]).filter(Boolean))].sort(); }
function fillSelect(id, col, label){
  const s=document.getElementById(id);
  s.innerHTML = `<option value="">all ${label}</option>` +
    uniq(col).map(v=>`<option>${esc(v)}</option>`).join("");
}
function esc(s){ return (s??"").toString().replace(/[&<>]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;"}[c])); }
function hl(s, q){ s=esc(s); if(!q) return s;
  try{ return s.replace(new RegExp("("+q.replace(/[.*+?^${}()|[\\]\\\\]/g,"\\\\$&")+")","ig"),"<mark>$1</mark>"); }
  catch(e){ return s; } }
function scoreCell(v){
  if(v===""||v==null) return `<span class="score sx">–</span>`;
  return `<span class="score s${v}">${v}</span>`;
}
const SERVED = location.protocol !== "file:";
function audioCell(r){
  const key = r.audio || r.qid;
  if(!key) return `<td class="aud"></td>`;
  if(!SERVED) return `<td class="aud"><span class="noaudio">run with --serve to play</span></td>`;
  return `<td class="aud"><audio controls preload="none" src="/audio/${encodeURIComponent(key)}"></audio></td>`;
}

function render(){
  const q=document.getElementById("q").value.trim().toLowerCase();
  const fp=document.getElementById("piac").value;
  const fc=document.getElementById("confidence").value;
  const f1=document.getElementById("c1").value, f2=document.getElementById("c2").value,
        f3=document.getElementById("c3").value, fs=document.getElementById("score").value;
  let rows = ROWS.filter(r=>{
    if(fp && r.category!==fp) return false;
    if(fc && r.judge_confidence!==fc) return false;
    if(f1 && r.category_1!==f1) return false;
    if(f2 && r.category_2!==f2) return false;
    if(f3 && r.category_3!==f3) return false;
    if(fs==="x"){ if(r.judge_score!=="") return false; }
    else if(fs!=="" && r.judge_score!==fs) return false;
    if(q){ const hay=Object.values(r).map(v=>(v??"").toString()).join(" ").toLowerCase();
           if(!hay.includes(q)) return false; }
    return true;
  });
  rows.sort((a,b)=>{
    let x=a[sortCol]??"", y=b[sortCol]??"";
    if(sortCol==="judge_score"||sortCol==="judge_score_norm"){ x=parseFloat(x); y=parseFloat(y);
      if(isNaN(x))x=-1; if(isNaN(y))y=-1; }
    return (x>y?1:x<y?-1:0)*sortDir;
  });
  const visibleCols=[...ESSENTIAL_COLS.filter(c=>COLS.includes(c)),
    ...COLS.filter(c=>!ESSENTIAL_COLS.includes(c) && EXTRA_COLS.has(c))];
  const head=`<th class="noSort">audio</th>`+visibleCols.map(c=>`<th data-c="${c}">${LABELS[c]||c}${sortCol===c?` <span class="arrow">${sortDir>0?"▲":"▼"}</span>`:""}</th>`).join("");
  document.getElementById("head").innerHTML=head;
  document.querySelectorAll("th[data-c]").forEach(th=>th.onclick=()=>{
    const c=th.dataset.c; if(sortCol===c) sortDir*=-1; else {sortCol=c; sortDir=1;} render();
  });
  const body=rows.map(r=>`<tr>`+audioCell(r)+visibleCols.map(c=>{
    if(c==="judge_score") return `<td>${scoreCell(r[c])}</td>`;
    if(c==="qid") return `<td class="qid">${esc(r[c])}</td>`;
    if(c.startsWith("category")) return `<td class="cat">${esc(r[c])}</td>`;
    if(c==="error") return `<td class="err">${esc(r[c])}</td>`;
    if(c==="response") return `<td class="resp oeq-answer"><div class="text">${hl(r[c], q)}</div></td>`;
    if(LONG.has(c)){
      const cls={question:"q",prompt:"prompt",reference_answer:"ref",response:"resp",mcq_response:"resp",judge_rationale:"rat"}[c];
      return `<td class="${cls} long" title="Click to expand"><div class="text">${hl(r[c], q)}</div></td>`;
    }
    return `<td>${hl(r[c], q)}</td>`;
  }).join("")+"</tr>").join("");
  document.getElementById("body").innerHTML=body;
  document.querySelectorAll("td.long").forEach(td=>td.onclick=()=>td.classList.toggle("expanded"));
  document.getElementById("empty").style.display = rows.length?"none":"block";
  document.getElementById("count").textContent = `${rows.length} / ${ROWS.length} rows`;
}

function parseCsv(text){
  const records=[]; let record=[], field="", quoted=false;
  text=text.replace(/^\\uFEFF/,"");
  for(let i=0;i<text.length;i++){
    const char=text[i];
    if(quoted){
      if(char==='"' && text[i+1]==='"'){ field+='"'; i++; }
      else if(char==='"') quoted=false;
      else field+=char;
    } else if(char==='"') quoted=true;
    else if(char===","){ record.push(field); field=""; }
    else if(char==="\\n"){
      record.push(field.replace(/\\r$/, "")); records.push(record); record=[]; field="";
    } else field+=char;
  }
  if(field || record.length){ record.push(field.replace(/\\r$/, "")); records.push(record); }
  const headers=(records.shift()||[]).map(header=>header.trim());
  const rows=records.filter(values=>values.some(value=>value!=="")).map(values=>
    Object.fromEntries(headers.map((header,index)=>[header,values[index]??""])));
  return {headers,rows};
}

async function loadLocalSummaries(files){
  const parsed=await Promise.all([...files].map(async file=>({
    name:file.name, ...parseCsv(await file.text()),
  })));
  const isMcq=file=>file.headers.includes("pred_answer") || file.headers.includes("pred_letter");
  const mcq=parsed.find(isMcq);
  const oeq=parsed.find(file=>!isMcq(file) &&
    (file.headers.includes("reference_answer") || file.headers.includes("judge_score")));
  if(!oeq && !mcq){ alert("Choose an OEQ or MCQ summary CSV."); return; }

  let rows;
  if(oeq){
    rows=oeq.rows.map(row=>({...row}));
    if(mcq){
      const byQid=new Map(mcq.rows.map(row=>[row.qid,row]));
      rows.forEach(row=>{
        const match=byQid.get(row.qid)||{};
        row.mcq_pred_letter=match.pred_letter||"";
        row.mcq_pred=match.pred_answer||"";
        row.mcq_correct=match.correct||"";
        row.mcq_response=match.response||"";
        row.mcq_prompt=match.prompt||"";
      });
    }
  } else {
    rows=mcq.rows.map(row=>({...row, reference_answer:row.correct_answer||"", response:"",
      mcq_pred_letter:row.pred_letter||"", mcq_pred:row.pred_answer||"",
      mcq_correct:row.correct||"", mcq_response:row.response||""}));
  }

  ROWS=rows;
  COLS=[...new Set(rows.flatMap(row=>Object.keys(row)))];
  EXTRA_COLS.clear();
  document.getElementById("summaryFile").value=parsed.map(file=>file.name).join(" + ");
  document.getElementById("subtitle").textContent=`local file${parsed.length===1?"":"s"}: ${parsed.map(file=>file.name).join(" + ")} — ${rows.length} rows`;
  document.getElementById("q").value="";
  fillSelect("piac","category","PIEC"); fillSelect("confidence","judge_confidence","confidence"); fillSelect("c1","category_1","cat1");
  fillSelect("c2","category_2","cat2"); fillSelect("c3","category_3","cat3");
  setupColumnPicker(); stats(); render();
}

function setupSummaryFilePicker(){
  const input=document.getElementById("summaryFile");
  const options=document.getElementById("summaryFileOptions");
  SUMMARY_FILES.forEach(path=>{
    const option=document.createElement("option");
    option.value=path;
    options.appendChild(option);
  });
  input.value=CURRENT_SUMMARY;
  const loadMatch=()=>{
    const query=input.value.trim().toLowerCase();
    const match=SUMMARY_FILES.find(path=>path.toLowerCase()===query)
      || SUMMARY_FILES.find(path=>path.toLowerCase().includes(query));
    const url=new URL(location.href);
    if(match){
      input.value=match;
      url.searchParams.set("summary",match);
      url.searchParams.delete("summary_file");
    } else {
      const filePath=input.value.trim()
        .replace(/\\s+—\\s+\\d+\\s+rows?\\s*$/i,"")
        .replace(/^file:\\/\\//i,"")
        .replace(/^file:/i,"");
      if(!filePath.toLowerCase().endsWith(".csv")) return;
      url.searchParams.delete("summary");
      url.searchParams.set("summary_file",filePath);
    }
    location.assign(url);
  };
  input.addEventListener("change",loadMatch);
  input.addEventListener("keydown",event=>{
    if(event.key==="Enter"){ event.preventDefault(); loadMatch(); }
  });
  document.getElementById("localSummaryFiles").addEventListener("change",event=>{
    if(event.target.files.length) loadLocalSummaries(event.target.files);
    event.target.value="";
  });
}

function setupColumnPicker(){
  const optional=COLS.filter(c=>!ESSENTIAL_COLS.includes(c));
  const root=document.getElementById("extraColumns");
  root.innerHTML=optional.map(c=>`<label class="column-option"><input type="checkbox" value="${esc(c)}">${esc(LABELS[c]||c)}</label>`).join("");
  const updateCount=()=>{
    document.getElementById("extraCount").textContent=EXTRA_COLS.size ? `(${EXTRA_COLS.size})` : "";
  };
  root.querySelectorAll("input").forEach(box=>box.addEventListener("change",()=>{
    if(box.checked) EXTRA_COLS.add(box.value); else EXTRA_COLS.delete(box.value);
    updateCount(); render();
  }));
  document.getElementById("showAllColumns").onclick=()=>{
    root.querySelectorAll("input").forEach(box=>{ box.checked=true; EXTRA_COLS.add(box.value); });
    updateCount(); render();
  };
  document.getElementById("hideExtraColumns").onclick=()=>{
    EXTRA_COLS.clear(); root.querySelectorAll("input").forEach(box=>{ box.checked=false; });
    updateCount(); render();
  };
  updateCount();
}

function stats(){
  const scored=ROWS.filter(r=>r.judge_score!=="" && r.judge_score!=null);
  const norms=scored.map(r=>parseFloat(r.judge_score_norm)).filter(v=>!isNaN(v));
  const mean = norms.length? norms.reduce((a,b)=>a+b,0)/norms.length : 0;
  const dist=[0,0]; scored.forEach(r=>{const s=parseInt(r.judge_score); if(s===0||s===1)dist[s]++;});
  const mx=Math.max(1,...dist);
  const bars=dist.map((n,i)=>`<div class="bar s${i}" style="height:${6+28*n/mx}px"><span>${n}</span><small>${i}</small></div>`).join("");
  const PIEC=["perceptual","inferential","experiential","contextual"];
  const piacStats=PIEC.map(c=>{
    const v=scored.filter(r=>r.category===c).map(r=>parseFloat(r.judge_score_norm)).filter(x=>!isNaN(x));
    if(!v.length) return "";
    const m=v.reduce((a,b)=>a+b,0)/v.length;
    return `<div class="stat">${c} <b>${m.toFixed(3)}</b> <small style="color:var(--muted)">(n=${v.length})</small></div>`;
  }).join("");
  const confidence=Object.fromEntries(["low","mid","high"].map(c=>[c,ROWS.filter(r=>r.judge_confidence===c).length]));
  document.getElementById("stats").innerHTML =
    `<div class="stat">questions <b>${ROWS.length}</b></div>`+
    `<div class="stat">judged <b>${scored.length}</b></div>`+
    `<div class="stat">binary accuracy <b>${mean.toFixed(3)}</b></div>`+
    `<div class="stat">confidence <b>${confidence.low}/${confidence.mid}/${confidence.high}</b> <small>low/mid/high</small></div>`+
    `<div class="stat">score dist&nbsp;&nbsp;<span class="dist">${bars}</span></div>`+
    piacStats;
}

fillSelect("piac","category","PIEC"); fillSelect("confidence","judge_confidence","confidence"); fillSelect("c1","category_1","cat1");
fillSelect("c2","category_2","cat2"); fillSelect("c3","category_3","cat3");
["q","piac","confidence","c1","c2","c3","score"].forEach(id=>document.getElementById(id).addEventListener("input",render));
setupSummaryFilePicker(); setupColumnPicker(); stats(); render();
</script>
</body>
</html>"""


def build_html(
    rows: list[dict],
    title: str,
    subtitle: str,
    summary_files: list[str] | None = None,
    current_summary: str = "",
) -> str:
    # Show whatever columns the CSV actually has, including PIEC confidence.
    cols = list(rows[0].keys()) if rows else COLUMNS
    return (HTML_TEMPLATE
            .replace("__TITLE__", title)
            .replace("__SUBTITLE__", subtitle)
            .replace("__COLS__", json.dumps(cols))
            .replace("__SUMMARY_FILES__", json.dumps(summary_files or []))
            .replace("__CURRENT_SUMMARY__", json.dumps(current_summary))
            .replace("__DATA__", json.dumps(rows, ensure_ascii=False)))


def serve(default_csv: Path, port: int) -> None:
    """Serve the viewer at / with audio (Range-enabled) at /audio/<name>."""
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            parsed = urlparse(self.path)
            path = unquote(parsed.path)
            if path in ("/", "/index.html"):
                summaries = available_summary_files()
                summary_map = {
                    summary.relative_to(ROOT).as_posix(): summary for summary in summaries
                }
                default_key = default_csv.relative_to(ROOT).as_posix()
                params = parse_qs(parsed.query)
                requested = params.get("summary", [default_key])[0]
                csv_path = summary_map.get(requested, default_csv)
                if external := params.get("summary_file", [""])[0]:
                    cleaned = re.sub(r"\s+—\s+\d+\s+rows?\s*$", "", external)
                    cleaned = re.sub(r"^file:(?://)?", "", cleaned, flags=re.IGNORECASE)
                    candidate = Path(cleaned).expanduser().resolve()
                    if candidate.is_relative_to(ROOT) and candidate.is_file() and candidate.suffix.lower() == ".csv":
                        csv_path = candidate
                rows = load_rows(csv_path)
                current = csv_path.relative_to(ROOT).as_posix()
                if current not in summary_map:
                    summary_map[current] = csv_path
                html = build_html(
                    rows,
                    csv_path.stem,
                    f"{csv_path} — {len(rows)} rows",
                    list(summary_map),
                    current,
                )
                body = html.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            if path.startswith("/audio/"):
                return self._audio(path[len("/audio/"):])
            self.send_error(404)

        def _audio(self, name):
            target = _resolve_audio(name)
            if not target or not target.is_file():
                return self.send_error(404, "audio not found")
            size = target.stat().st_size
            start, end, status = 0, size - 1, 200
            rng = self.headers.get("Range")
            if rng and (m := re.match(r"bytes=(\d*)-(\d*)", rng)):
                if m.group(1):
                    start = int(m.group(1))
                if m.group(2):
                    end = int(m.group(2))
                status = 206
            length = end - start + 1
            self.send_response(status)
            self.send_header("Content-Type", MIME.get(target.suffix.lower(), "application/octet-stream"))
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Length", str(length))
            if status == 206:
                self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
            self.end_headers()
            with open(target, "rb") as f:
                f.seek(start)
                self.wfile.write(f.read(length))

    class DualStack(ThreadingHTTPServer):
        address_family = socket.AF_INET6
        allow_reuse_address = True

        def server_bind(self):
            with contextlib.suppress(Exception):
                self.socket.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
            return super().server_bind()

    print(f"Indexed {len(_audio_index())} audio keys under {AUDIO_ROOT}")
    print(f"Serving viewer + audio at  http://localhost:{port}   (Ctrl-C to stop)")
    DualStack(("::", port), Handler).serve_forever()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("csv", nargs="?", help="OEQ summary CSV (default: latest exp-0 run)")
    ap.add_argument("-o", "--out", help="output HTML path (default: <csv stem>.html)")
    ap.add_argument("--serve", action="store_true",
                    help="serve the viewer with audio playback instead of writing a file")
    ap.add_argument("--port", type=int, default=8000)
    args = ap.parse_args()

    if args.csv:
        csv_path = Path(args.csv).resolve()
    else:
        matches = available_summary_files()
        if not matches:
            sys.exit(f"No CSV given and none found under results/ (tried {DEFAULT_GLOBS})")
        csv_path = matches[-1]
    if not csv_path.exists():
        sys.exit(f"CSV not found: {csv_path}")

    if args.serve:
        serve(csv_path, args.port)
        return

    rows = load_rows(csv_path)
    subtitle = f"{csv_path} — {len(rows)} rows"
    summaries = available_summary_files()
    summary_files = [path.relative_to(ROOT).as_posix() for path in summaries]
    current = csv_path.relative_to(ROOT).as_posix() if csv_path.is_relative_to(ROOT) else str(csv_path)
    html = build_html(rows, csv_path.stem, subtitle, summary_files, current)
    out_path = Path(args.out) if args.out else csv_path.with_suffix(".html")
    out_path.write_text(html, encoding="utf-8")
    print(f"Wrote {out_path}  ({len(rows)} rows)")
    print(f"Open: file://{out_path.resolve()}")
    print(f"To play audio:  python renderers/oeq_report/oeq_report.py {csv_path} --serve")


if __name__ == "__main__":
    main()
