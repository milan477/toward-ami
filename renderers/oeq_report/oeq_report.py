"""Generate a self-contained HTML viewer for exp-0 MCQ + OEQ results.

Reads ``summary.csv`` from an ``exp_0_mcq_oeq/.../<date>/oeq`` run directory
(and merges its sibling MCQ summary). Legacy ``*_summary.csv`` runs remain
supported. Open with ``--serve`` to play local audio from ``data/audio/``.

Usage:
    python renderers/oeq_report/oeq_report.py --serve
    python renderers/oeq_report/oeq_report.py results/exp_0_mcq_oeq/mmar/gemini-3-flash-preview/2026-07-18_17-37-06/oeq/summary.csv --serve
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
from urllib.parse import unquote, urlparse

ROOT = Path(__file__).resolve().parents[2]
AUDIO_ROOT = ROOT / "data" / "audio"
# Prefer dated experiment runs, then fall back to the older variant layout.
DEFAULT_GLOBS = [
    str(ROOT / "results" / "exp_0_mcq_oeq" / "*" / "*" / "*" / "oeq" / "summary.csv"),
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
           "response", "judge_score", "judge_score_norm", "judge_rationale",
           "skipped", "error"]


def _result_date(path: str) -> str:
    result = Path(path)
    if result.name == "summary.csv" and result.parent.name == "oeq":
        return result.parent.parent.name
    return result.name.split("_summary.csv")[0]


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
    --bg:#0f1117; --panel:#171a21; --line:#262b36; --txt:#e6e8ee; --muted:#9aa3b2;
    --accent:#6ea8fe;
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
  .stat { background:#11141b; border:1px solid var(--line); border-radius:8px;
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
  input,select { background:#11141b; color:var(--txt); border:1px solid var(--line);
                 border-radius:6px; padding:6px 8px; font-size:13px; }
  input#q { flex:1; min-width:220px; }
  .count { color:var(--muted); font-size:12px; align-self:center; margin-left:auto; }
  .wrap { overflow:auto; flex:1 1 auto; min-height:0; }
  table { border-collapse:collapse; width:100%; }
  th,td { border-bottom:1px solid var(--line); padding:8px 10px; text-align:left;
          vertical-align:top; }
  th { position:sticky; top:0; background:#1b1f29; cursor:pointer; white-space:nowrap;
       font-size:12px; user-select:none; }
  th:hover { color:var(--accent); }
  th .arrow { color:var(--accent); font-size:10px; }
  tr:hover td { background:#141821; }
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
  .s3{background:#9fd356;} .s4{background:#54c98a;} .sx{background:#444; color:#bbb;}
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
  mark { background:#3a4a6b; color:#fff; }
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
    <div class="sub">__SUBTITLE__</div>
  </div>
  <div class="stats" id="stats"></div>
</header>
<div class="controls">
  <input id="q" type="search" placeholder="Search question / answer / reference / rationale / qid…">
  <select id="piac"></select>
  <select id="c1"></select>
  <select id="c2"></select>
  <select id="c3"></select>
  <select id="score">
    <option value="">any score</option>
    <option value="0">0</option><option value="1">1</option><option value="2">2</option>
    <option value="3">3</option><option value="4">4</option>
    <option value="x">unscored</option>
  </select>
  <select id="hall">
    <option value="">any hallucination</option>
    <option value="1">hallucinated</option>
    <option value="0">clean</option>
  </select>
  <select id="columns" title="Choose how much run metadata to display">
    <option value="results">result columns</option>
    <option value="all">all columns</option>
  </select>
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
const ROWS = __DATA__;
const COLS = __COLS__;
const LABELS = {qid:"qid", category:"PIAC", skills:"skills", category_1:"cat1", category_2:"cat2", category_3:"cat3",
  question:"question", answer_format:"answer format", example_answer:"example",
  prompt:"full prompt to ALM", reference_answer:"reference", response:"OEQ answer",
  mcq_pred:"MCQ pred", mcq_correct:"MCQ ✓", mcq_response:"MCQ raw", mcq_prompt:"MCQ prompt",
  judge_score:"score", judge_score_norm:"norm", verdict:"verdict", grounded:"grounded",
  hallucinated:"halluc?", hallucination_level:"halluc level", judge_rationale:"rationale",
  skipped:"skipped", error:"error"};
const TRUTHY = v => /^(true|1|yes)$/i.test((v??"").toString().trim());
const LONG = new Set(["question","prompt","reference_answer","response","judge_rationale"]);
const RESULT_COLS = new Set(["qid","category","category_2","category_3","question",
  "reference_answer","response","mcq_pred","mcq_correct","judge_score","verdict",
  "grounded","hallucinated","judge_rationale","error"]);
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
  const fh=document.getElementById("hall").value;
  const f1=document.getElementById("c1").value, f2=document.getElementById("c2").value,
        f3=document.getElementById("c3").value, fs=document.getElementById("score").value;
  let rows = ROWS.filter(r=>{
    if(fp && r.category!==fp) return false;
    if(fh==="1" && !TRUTHY(r.hallucinated)) return false;
    if(fh==="0" && TRUTHY(r.hallucinated)) return false;
    if(f1 && r.category_1!==f1) return false;
    if(f2 && r.category_2!==f2) return false;
    if(f3 && r.category_3!==f3) return false;
    if(fs==="x"){ if(r.judge_score!=="") return false; }
    else if(fs!=="" && r.judge_score!==fs) return false;
    if(q){ const hay=(r.qid+" "+r.question+" "+r.reference_answer+" "+r.response+" "+r.judge_rationale).toLowerCase();
           if(!hay.includes(q)) return false; }
    return true;
  });
  rows.sort((a,b)=>{
    let x=a[sortCol]??"", y=b[sortCol]??"";
    if(sortCol==="judge_score"||sortCol==="judge_score_norm"){ x=parseFloat(x); y=parseFloat(y);
      if(isNaN(x))x=-1; if(isNaN(y))y=-1; }
    return (x>y?1:x<y?-1:0)*sortDir;
  });
  const columnMode=document.getElementById("columns").value;
  const visibleCols=columnMode==="all" ? COLS : COLS.filter(c=>RESULT_COLS.has(c));
  const head=`<th class="noSort">audio</th>`+visibleCols.map(c=>`<th data-c="${c}">${LABELS[c]||c}${sortCol===c?` <span class="arrow">${sortDir>0?"▲":"▼"}</span>`:""}</th>`).join("");
  document.getElementById("head").innerHTML=head;
  document.querySelectorAll("th[data-c]").forEach(th=>th.onclick=()=>{
    const c=th.dataset.c; if(sortCol===c) sortDir*=-1; else {sortCol=c; sortDir=1;} render();
  });
  const body=rows.map(r=>`<tr class="${TRUTHY(r.hallucinated)?'hall':''}">`+audioCell(r)+visibleCols.map(c=>{
    if(c==="judge_score") return `<td>${scoreCell(r[c])}</td>`;
    if(c==="qid") return `<td class="qid">${esc(r[c])}</td>`;
    if(c==="hallucinated") return `<td>${TRUTHY(r[c])?'<span class="hbadge">yes</span>':'<span class="muted2">no</span>'}</td>`;
    if(c.startsWith("category")) return `<td class="cat">${esc(r[c])}</td>`;
    if(c==="error") return `<td class="err">${esc(r[c])}</td>`;
    if(LONG.has(c)){
      const cls={question:"q",prompt:"prompt",reference_answer:"ref",response:"resp",judge_rationale:"rat"}[c];
      return `<td class="${cls} long" title="Click to expand"><div class="text">${hl(r[c], q)}</div></td>`;
    }
    return `<td>${hl(r[c], q)}</td>`;
  }).join("")+"</tr>").join("");
  document.getElementById("body").innerHTML=body;
  document.querySelectorAll("td.long").forEach(td=>td.onclick=()=>td.classList.toggle("expanded"));
  document.getElementById("empty").style.display = rows.length?"none":"block";
  document.getElementById("count").textContent = `${rows.length} / ${ROWS.length} rows`;
}

function stats(){
  const scored=ROWS.filter(r=>r.judge_score!=="" && r.judge_score!=null);
  const norms=scored.map(r=>parseFloat(r.judge_score_norm)).filter(v=>!isNaN(v));
  const mean = norms.length? norms.reduce((a,b)=>a+b,0)/norms.length : 0;
  const dist=[0,0,0,0,0]; scored.forEach(r=>{const s=parseInt(r.judge_score); if(s>=0&&s<=4)dist[s]++;});
  const mx=Math.max(1,...dist);
  const bars=dist.map((n,i)=>`<div class="bar s${i}" style="height:${6+28*n/mx}px"><span>${n}</span><small>${i}</small></div>`).join("");
  const PIAC=["perceptual","inferential","affective","contextual"];
  const piacStats=PIAC.map(c=>{
    const v=scored.filter(r=>r.category===c).map(r=>parseFloat(r.judge_score_norm)).filter(x=>!isNaN(x));
    if(!v.length) return "";
    const m=v.reduce((a,b)=>a+b,0)/v.length;
    return `<div class="stat">${c} <b>${(m*4).toFixed(2)}</b> <small style="color:var(--muted)">(n=${v.length})</small></div>`;
  }).join("");
  const nHall=ROWS.filter(r=>TRUTHY(r.hallucinated)).length;
  const hasHall=ROWS.some(r=>r.hallucinated!==undefined && r.hallucinated!=="");
  document.getElementById("stats").innerHTML =
    `<div class="stat">questions <b>${ROWS.length}</b></div>`+
    `<div class="stat">judged <b>${scored.length}</b></div>`+
    `<div class="stat">mean 0-4 <b>${(mean*4).toFixed(2)}</b></div>`+
    `<div class="stat">mean 0-1 <b>${mean.toFixed(3)}</b></div>`+
    (hasHall?`<div class="stat">hallucination <b>${scored.length?((nHall/scored.length)*100).toFixed(0):0}%</b> <small style="color:var(--muted)">(${nHall})</small></div>`:"")+
    `<div class="stat">score dist&nbsp;&nbsp;<span class="dist">${bars}</span></div>`+
    piacStats;
}

fillSelect("piac","category","PIAC"); fillSelect("c1","category_1","cat1");
fillSelect("c2","category_2","cat2"); fillSelect("c3","category_3","cat3");
["q","piac","hall","c1","c2","c3","score","columns"].forEach(id=>document.getElementById(id).addEventListener("input",render));
stats(); render();
</script>
</body>
</html>"""


def build_html(rows: list[dict], title: str, subtitle: str) -> str:
    # Show whatever columns the CSV actually has (in header order), so PIAC-judge
    # extras (skills, verdict, grounded, hallucinated, hallucination_level) appear.
    cols = list(rows[0].keys()) if rows else COLUMNS
    return (HTML_TEMPLATE
            .replace("__TITLE__", title)
            .replace("__SUBTITLE__", subtitle)
            .replace("__COLS__", json.dumps(cols))
            .replace("__DATA__", json.dumps(rows, ensure_ascii=False)))


def serve(html: str, port: int) -> None:
    """Serve the viewer at / with audio (Range-enabled) at /audio/<name>."""
    body = html.encode("utf-8")

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            path = unquote(urlparse(self.path).path)
            if path in ("/", "/index.html"):
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
        csv_path = Path(args.csv)
    else:
        matches = []
        for pattern in DEFAULT_GLOBS:
            matches = sorted(set(glob.glob(pattern)), key=_result_date)
            if matches:
                break
        if not matches:
            sys.exit(f"No CSV given and none found under results/ (tried {DEFAULT_GLOBS})")
        csv_path = Path(matches[-1])
    if not csv_path.exists():
        sys.exit(f"CSV not found: {csv_path}")

    rows = load_rows(csv_path)
    subtitle = f"{csv_path} — {len(rows)} rows"
    html = build_html(rows, csv_path.stem, subtitle)

    if args.serve:
        serve(html, args.port)
        return

    out_path = Path(args.out) if args.out else csv_path.with_suffix(".html")
    out_path.write_text(html, encoding="utf-8")
    print(f"Wrote {out_path}  ({len(rows)} rows)")
    print(f"Open: file://{out_path.resolve()}")
    print(f"To play audio:  python renderers/oeq_report/oeq_report.py {csv_path} --serve")


if __name__ == "__main__":
    main()
