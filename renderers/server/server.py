"""Tiny dependency-free web UI to browse benchmark questions + their audio.

Reads benchmark CSVs (recursively) under --data-dir and serves the audio under
data/audio/<dataset>/. Audio files are matched to each question's audio_url by
indexing what's on disk (formats differ per dataset: "./audio/X.wav",
"data/X.wav", "sdd:415600", multi-clip "a.wav; b.wav", ...), so questions whose
audio hasn't been downloaded simply show up without a player.

The default --data-dir is data/benchmarks, whose CSVs are named
<name>_<stage>.csv (raw/normalized/cleaned/ready); each is discovered by its
filename stem (e.g. "mmar_normalized", "mmar_ready"). Any other flat directory
of CSVs also works (e.g. --data-dir data/af_next).

Run:
    python renderers/server/server.py            # then open http://localhost:8000
    python renderers/server/server.py --port 9000 --data-dir data/af_next
"""

import argparse
import contextlib
import json
import re
import socket
from functools import lru_cache
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

import pandas as pd

ROOT       = Path(__file__).resolve().parents[2]
AUDIO_DIR  = ROOT / "data" / "audio"
HTML_FILE  = Path(__file__).parent / "index.html"
AUDIO_EXTS = {".wav", ".mp3", ".flac", ".ogg", ".m4a", ".opus"}
MIME = {
    ".wav": "audio/wav", ".mp3": "audio/mpeg", ".flac": "audio/flac",
    ".ogg": "audio/ogg", ".m4a": "audio/mp4", ".opus": "audio/opus",
}

DATA_DIR = ROOT / "data" / "benchmarks"   # overridden by --data-dir


# --- Data loading ---------------------------------------------------------

def _dataset_map() -> dict[str, Path]:
    """Map dataset key (CSV filename stem) → path, found recursively under DATA_DIR.

    Supports both the nested benchmark layout (data/benchmarks/<name>/<name>_<stage>.csv)
    and any flat directory of CSVs (e.g. data/af_next)."""
    return {p.stem: p for p in sorted(DATA_DIR.rglob("*.csv"))
            if not p.name.startswith(".")}


@lru_cache(maxsize=None)
def _load_df(dataset: str) -> pd.DataFrame:
    return pd.read_csv(_dataset_map()[dataset], dtype=str, keep_default_na=False)


def datasets() -> list[str]:
    return sorted(_dataset_map())


# --- Audio resolution -----------------------------------------------------

@lru_cache(maxsize=None)
def _audio_index(dataset: str) -> dict[str, str]:
    """Map several lookup keys (filename, stem, leading id) → relative path."""
    base = AUDIO_DIR / dataset
    idx: dict[str, str] = {}
    if base.exists():
        for p in base.rglob("*"):
            if p.is_file() and p.suffix.lower() in AUDIO_EXTS:
                rel = p.relative_to(base).as_posix()
                for key in (p.name, p.stem, p.name.split(".")[0]):
                    idx.setdefault(key, rel)
    return idx


def resolve_audio(dataset: str, audio_url: str) -> list[str]:
    """Return playable /audio/... URLs for the clips that exist on disk."""
    idx = _audio_index(dataset)
    urls: list[str] = []
    for piece in str(audio_url).split(";"):
        piece = piece.strip()
        if not piece:
            continue
        name = piece.split("/")[-1]
        if ":" in name:                     # e.g. "sdd:415600" → "415600"
            name = name.split(":", 1)[1]
        for cand in (name, name.rsplit(".", 1)[0], name.split(".", 1)[0]):
            if cand in idx:
                urls.append(f"/audio/{dataset}/{idx[cand]}")
                break
    return urls


# --- API handlers ---------------------------------------------------------

def api_datasets() -> dict:
    out = []
    for name in datasets():
        df = _load_df(name)
        idx = _audio_index(name)
        out.append({
            "name": name,
            "count": len(df),
            "columns": list(df.columns),
            "audio_on_disk": len(set(idx.values())),
        })
    return {"datasets": out}


def api_questions(params: dict) -> dict:
    dataset = (params.get("dataset", [None])[0]) or (datasets()[0] if datasets() else None)
    if dataset not in datasets():
        return {"error": f"unknown dataset {dataset!r}", "datasets": datasets()}

    df = _load_df(dataset)
    search   = (params.get("search", [""])[0] or "").strip().lower()
    category = (params.get("category", [""])[0] or "").strip()
    qtype    = (params.get("type", [""])[0] or "").strip()
    only_aud = (params.get("audio_only", [""])[0] or "") in ("1", "true")
    page     = max(1, int(params.get("page", ["1"])[0] or 1))
    size     = min(200, max(1, int(params.get("page_size", ["25"])[0] or 25)))

    rows = df.to_dict("records")
    if category:
        rows = [r for r in rows if r.get("category_1", "") == category]
    if qtype:
        rows = [r for r in rows if r.get("question_type", "") == qtype]
    if search:
        rows = [r for r in rows
                if search in r.get("question", "").lower()
                or search in r.get("correct_answer", "").lower()]

    # attach resolved audio
    for r in rows:
        r["_audio"] = resolve_audio(dataset, r.get("audio_url", ""))
    if only_aud:
        rows = [r for r in rows if r["_audio"]]

    total = len(rows)
    start = (page - 1) * size
    page_rows = rows[start:start + size]
    return {
        "dataset": dataset,
        "columns": list(df.columns),
        "editable": "qid" in df.columns and "category" in df.columns,
        "review_categories": REVIEW_CATEGORIES,
        "total": total,
        "page": page,
        "page_size": size,
        "rows": page_rows,
    }


def api_categories(params: dict) -> dict:
    dataset = (params.get("dataset", [None])[0]) or (datasets()[0] if datasets() else None)
    if dataset not in datasets():
        return {"categories": []}
    df = _load_df(dataset)
    cats = sorted({c for c in df.get("category_1", pd.Series(dtype=str)) if c})
    return {"categories": cats}


# The listener-action review categories (must match annotate.py). When a dataset
# carries a `category` column, the frontend lets a reviewer reassign it.
REVIEW_CATEGORIES = ["perceptual", "inferential", "affective", "contextual"]
EDITABLE_FIELDS = {"category", "piac", "answer_format"}
# `category` and `piac` hold the same content-category value — edit one, write both.
PIAC_ALIASES = ("category", "piac")


def api_update(body: dict) -> dict:
    """Persist a single edited cell back to the dataset's CSV on disk (by qid)."""
    dataset = body.get("dataset")
    qid = str(body.get("qid", ""))
    field = body.get("field")
    value = "" if body.get("value") is None else str(body.get("value"))
    if dataset not in datasets():
        return {"ok": False, "error": f"unknown dataset {dataset!r}"}
    if field not in EDITABLE_FIELDS:
        return {"ok": False, "error": f"field {field!r} is not editable"}
    if field in PIAC_ALIASES and value and value not in REVIEW_CATEGORIES:
        return {"ok": False, "error": f"invalid category {value!r}"}

    path = _dataset_map()[dataset]
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    if "qid" not in df.columns:
        return {"ok": False, "error": f"{dataset} has no qid column; not editable"}
    mask = df["qid"] == qid
    if not mask.any():
        return {"ok": False, "error": f"qid {qid!r} not found"}
    # Editing the content category writes both aliases so they never drift.
    targets = PIAC_ALIASES if field in PIAC_ALIASES else (field,)
    for col in targets:
        if col not in df.columns:
            df[col] = ""
        df.loc[mask, col] = value
    df.to_csv(path, index=False)
    _load_df.cache_clear()  # so subsequent reads reflect the edit
    return {"ok": True, "dataset": dataset, "qid": qid, "field": field, "value": value}


# --- HTTP server ----------------------------------------------------------

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):  # quieter console
        pass

    def _send_json(self, obj: dict, status: int = 200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self):
        body = HTML_FILE.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _serve_audio(self, dataset: str, relpath: str):
        base = (AUDIO_DIR / dataset).resolve()
        target = (base / relpath).resolve()
        if not str(target).startswith(str(base)) or not target.is_file():
            self.send_error(404, "audio not found")
            return
        size = target.stat().st_size
        ctype = MIME.get(target.suffix.lower(), "application/octet-stream")

        # Minimal HTTP Range support so the browser can seek.
        rng = self.headers.get("Range")
        start, end = 0, size - 1
        status = 200
        if rng:
            m = re.match(r"bytes=(\d*)-(\d*)", rng)
            if m:
                if m.group(1):
                    start = int(m.group(1))
                if m.group(2):
                    end = int(m.group(2))
                status = 206

        length = end - start + 1
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(length))
        if status == 206:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.end_headers()
        with open(target, "rb") as f:
            f.seek(start)
            self.wfile.write(f.read(length))

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        params = parse_qs(parsed.query)

        if path in ("/", "/index.html"):
            return self._send_html()
        if path == "/api/datasets":
            return self._send_json(api_datasets())
        if path == "/api/categories":
            return self._send_json(api_categories(params))
        if path == "/api/questions":
            return self._send_json(api_questions(params))
        if path.startswith("/audio/"):
            parts = unquote(path[len("/audio/"):]).split("/", 1)
            if len(parts) == 2:
                return self._serve_audio(parts[0], parts[1])
            return self.send_error(404)
        self.send_error(404)

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path != "/api/update":
            return self.send_error(404)
        length = int(self.headers.get("Content-Length", 0) or 0)
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            return self._send_json({"ok": False, "error": "bad json"}, status=400)
        result = api_update(body)
        return self._send_json(result, status=200 if result.get("ok") else 400)


class DualStackServer(ThreadingHTTPServer):
    """Accept both IPv4 and IPv6 so `localhost` works regardless of how it resolves
    (browsers often try ::1 before 127.0.0.1)."""
    address_family = socket.AF_INET6
    allow_reuse_address = True

    def server_bind(self):
        with contextlib.suppress(Exception):
            self.socket.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
        return super().server_bind()


def main():
    global DATA_DIR
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--host", default="localhost",
                    help="Bind address. 'localhost' (default) listens on IPv4+IPv6.")
    ap.add_argument("--data-dir", default=str(DATA_DIR),
                    help="Directory of benchmark CSVs, searched recursively "
                         "(default: data/benchmarks)")
    args = ap.parse_args()

    DATA_DIR = (ROOT / args.data_dir) if not Path(args.data_dir).is_absolute() else Path(args.data_dir)
    if not datasets():
        raise SystemExit(f"No CSVs found in {DATA_DIR}")

    print(f"Serving {len(datasets())} dataset(s) from {DATA_DIR}: {', '.join(datasets())}")
    print(f"Open  http://localhost:{args.port}   (or http://127.0.0.1:{args.port})")
    if args.host in ("", "localhost", "::"):
        server = DualStackServer(("::", args.port), Handler)
    else:
        server = ThreadingHTTPServer((args.host, args.port), Handler)
    server.serve_forever()


if __name__ == "__main__":
    main()
