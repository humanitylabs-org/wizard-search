#!/usr/bin/env python3
"""Wizard Search: private image search + AI overview, served inside Wizard's link sheet.

Routes (all under /wizard-search):
  GET  /                      the app (dark, phone-first)
  GET  /api/images?q=         image results (Bing images over the Thales residential tunnel; Bright Data fallback)
  GET  /api/web?q=            web results (Bright Data SERP, parsed; local Firecrawl router fallback)
  GET  /api/overview?q=       short cited answer over the web results (Tinfoil private inference)
  GET  /img/<id>.jpg          full-size image proxy, only for ids issued by a recent image search
  GET  /api/health

Loopback only; the private gateway adds Tailnet identity. Queries are never logged.
"""
from __future__ import annotations

import base64
import hashlib
import html
import ipaddress
import json
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
import os
import re
import socket
import subprocess
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import OrderedDict
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
WEB = ROOT / "web"
PREFIX = "/wizard-search"
PORT = int(os.environ.get("WIZARD_SEARCH_PORT", "9288"))
SOCKS = os.environ.get("WIZARD_SEARCH_SOCKS", "socks5h://127.0.0.1:18889")  # Thales residential egress
LLM_URL = os.environ.get("TINFOIL_PROXY_URL", "http://127.0.0.1:3301/v1/chat/completions")
LLM_MODEL = os.environ.get("WIZARD_SEARCH_MODEL", "gpt-oss-120b")
FIRECRAWL_URL = os.environ.get("FIRECRAWL_ROUTER_URL", "http://127.0.0.1:3003/v2/search")
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36"


def _env_value(path: Path, key: str) -> str:
    try:
        for line in path.read_text().splitlines():
            if line.startswith(key + "="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    except OSError:
        pass
    return ""


HOME = Path.home()
TINFOIL_KEY = os.environ.get("TINFOIL_API_KEY") or _env_value(HOME / ".hermes/.env", "TINFOIL_API_KEY")
BD_TOKEN = os.environ.get("BRIGHTDATA_API_TOKEN") or _env_value(HOME / ".config/firecrawl-hybrid-router.env", "BRIGHTDATA_API_TOKEN")
BD_SERP_ZONE = os.environ.get("BRIGHTDATA_SERP_ZONE", "serp_api1")
BD_UNLOCK_ZONE = os.environ.get("BRIGHTDATA_UNLOCK_ZONE", "mcp_unlocker")


class TTLCache:
    def __init__(self, size: int, ttl: float):
        self.size, self.ttl, self.d, self.lock = size, ttl, OrderedDict(), threading.Lock()

    def get(self, k):
        with self.lock:
            v = self.d.get(k)
            if not v or time.time() - v[0] > self.ttl:
                self.d.pop(k, None)
                return None
            self.d.move_to_end(k)
            return v[1]

    def put(self, k, v):
        with self.lock:
            self.d[k] = (time.time(), v)
            self.d.move_to_end(k)
            while len(self.d) > self.size:
                self.d.popitem(last=False)


IMG_CACHE = TTLCache(200, 1800)
WEB_CACHE = TTLCache(200, 1800)
OVR_CACHE = TTLCache(200, 1800)
IMG_IDS = TTLCache(20000, 6 * 3600)
THUMBS = TTLCache(800, 3600)  # thumbnail bytes, so re-opening a search paints instantly  # id -> original image URL (the proxy serves nothing else)
INFLIGHT: dict[str, threading.Event] = {}
INFLIGHT_LOCK = threading.Lock()


def norm_q(q: str) -> str:
    return re.sub(r"\s+", " ", (q or "")).strip()[:300]


def curl(url: str, *, socks: bool, timeout: int = 15, binary: bool = False, max_bytes: int = 0):
    args = ["curl", "-s", "-L", "--max-redirs", "4", "-m", str(timeout), "-A", UA, "--compressed",
            "-H", "Accept-Language: en-US,en;q=0.9", "-w", "\n%{http_code} %{content_type}"]
    if socks:
        args += ["-x", SOCKS]
    if max_bytes:
        args += ["--max-filesize", str(max_bytes)]
    args.append(url)
    p = subprocess.run(args, capture_output=True, timeout=timeout + 5)
    body, _, tail = p.stdout.rpartition(b"\n")
    code, _, ctype = tail.decode("latin1").partition(" ")
    return (int(code) if code.isdigit() else 0), ctype.strip(), (body if binary else body.decode("utf8", "replace"))


def bd_request(payload: dict, timeout: int = 30) -> bytes:
    if not BD_TOKEN:
        raise RuntimeError("no bright data token")
    req = urllib.request.Request("https://api.brightdata.com/request", data=json.dumps(payload).encode(),
                                 headers={"Authorization": "Bearer " + BD_TOKEN, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:  # nosec B310 constant host
        return r.read()


# ---------------------------------------------------------------- images
def parse_bing_images(page: str) -> list[dict]:
    out, seen = [], set()
    marks = list(re.finditer(r'\bm="(\{[^"]+\})"', page))
    for i, m in enumerate(marks):
        try:
            d = json.loads(html.unescape(m.group(1)))
        except ValueError:
            continue
        full, thumb = d.get("murl") or "", d.get("turl") or ""
        if not full.startswith(("http://", "https://")) or full in seen:
            continue
        seen.add(full)
        item = {"full": full, "thumb": thumb or full, "title": re.sub("[\ue000\ue001]", "", html.unescape(d.get("t") or "")).strip(),
                "page": d.get("purl") or "", "desc": re.sub("[\ue000\ue001]", "", html.unescape(d.get("desc") or "")).strip()}
        # Dimensions sit in the same card ("3448&#215;2296").
        chunk = page[m.end(): marks[i + 1].start() if i + 1 < len(marks) else m.end() + 4000]
        dm = re.search(r'<span class="nowrap"[^>]*>(\d+)\s*(?:&#215;|×|x)\s*(\d+)', chunk)
        if dm:
            item["w"], item["h"] = int(dm.group(1)), int(dm.group(2))
        out.append(item)
    return out


def image_search(q: str) -> dict:
    qs = urllib.parse.urlencode({"q": q, "first": 1, "count": 60, "mmasync": 1, "setlang": "en-US", "adlt": "moderate"})
    url = "https://www.bing.com/images/async?" + qs
    items, source = [], ""
    try:
        code, _, page = curl(url, socks=True, timeout=12)
        if code == 200:
            items, source = parse_bing_images(page), "bing"
    except Exception:
        pass
    if len(items) < 6:
        try:
            page = bd_request({"zone": BD_UNLOCK_ZONE, "url": url, "format": "raw"}, timeout=30).decode("utf8", "replace")
            more = parse_bing_images(page)
            if len(more) > len(items):
                items, source = more, "bing via unlocker"
        except Exception:
            pass
    for it in items:
        iid = hashlib.sha1(it["full"].encode()).hexdigest()[:20]
        IMG_IDS.put(iid, it["full"])
        IMG_IDS.put("t" + iid, it["thumb"])
        it["id"] = iid
        it["host"] = urllib.parse.urlsplit(it["page"] or it["full"]).hostname or ""
        it["host"] = re.sub(r"^www\.", "", it["host"])
    return {"q": q, "source": source, "images": items}


# ---------------------------------------------------------------- web
STOP = set("a an the of in on for to and or is are was were be why how what when where who which does do did can i my me you your it its this that with from by at as about best top vs".split())


def _relevant(q: str, rows: list[dict]) -> bool:
    """The local search lane drops stop-words ("why is the sky blue" -> dictionary pages for "why").
    Keep its batch only when most results mention the query's content words."""
    words = [w for w in re.findall(r"[a-z0-9]+", q.lower()) if w not in STOP and len(w) > 1]
    if not words or not rows:
        return bool(rows)
    hits = sum(1 for r in rows if sum(w in (r["title"] + " " + r["snippet"] + " " + r["url"]).lower() for w in words) >= max(1, (len(words) + 1) // 2))
    return hits >= max(2, len(rows) // 2)


def _serp(q: str) -> list[dict]:
    gurl = "https://www.google.com/search?" + urllib.parse.urlencode({"q": q, "hl": "en", "num": 10})
    d = json.loads(bd_request({"zone": BD_SERP_ZONE, "url": gurl, "format": "raw", "data_format": "parsed_light"}, timeout=30))
    rows = [{"url": r["link"], "title": r.get("title") or r["link"], "snippet": r.get("description") or ""}
            for r in d.get("organic") or [] if r.get("link")]
    if not rows:
        raise RuntimeError("empty serp")
    return rows


def _local(q: str) -> list[dict]:
    req = urllib.request.Request(FIRECRAWL_URL, data=json.dumps({"query": q, "limit": 8}).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:  # nosec B310 loopback
        d = json.load(r)
    rows = [{"url": x["url"], "title": x.get("title") or x["url"], "snippet": x.get("description") or ""}
            for x in (d.get("data") or {}).get("web") or [] if x.get("url")]
    if not _relevant(q, rows):
        raise RuntimeError("off-topic local batch")
    return rows


POOL = ThreadPoolExecutor(max_workers=24)


def web_search(q: str) -> dict:
    """SERP is the quality lane but its latency swings 2-40 s per request, so: start it, hedge with a
    second SERP request after 5 s, run the local lane alongside, and take SERP when it lands within
    ~18 s; otherwise the first relevant batch from any lane."""
    started = time.time()
    futs = {POOL.submit(_serp, q): "serp", POOL.submit(_local, q): "local"}
    hedged = False
    local_rows = None
    while futs and time.time() - started < 32:
        done, _ = wait(list(futs), timeout=1.0, return_when=FIRST_COMPLETED)
        for f in done:
            lane = futs.pop(f)
            try:
                rows = f.result()
            except Exception:
                continue
            if lane == "serp":
                return _finish(q, rows, "serp")
            local_rows = rows
        if not hedged and time.time() - started > 5:
            futs[POOL.submit(_serp, q)] = "serp"
            hedged = True
        if local_rows and time.time() - started > 18:
            break
        if local_rows and not any(v == "serp" for v in futs.values()):
            break
    return _finish(q, local_rows or [], "local" if local_rows else "")


def _finish(q: str, rows: list[dict], source: str) -> dict:
    for r in rows:
        r["host"] = re.sub(r"^www\.", "", urllib.parse.urlsplit(r["url"]).hostname or "")
    return {"q": q, "source": source, "results": rows[:10]}


OVERVIEW_SYSTEM = """You write the short answer box at the top of a search results page.
Answer the query directly from the numbered sources. 2 to 5 sentences, plain words, no preamble, no headings.
Cite sources inline as [1], [2] right after the claim they support. Use only facts the sources support.
If the query is a name, place or thing, say what it is. If it asks for options or "best", name the top few.
If the sources do not answer it, say so in one sentence. Today is %s."""


def overview(q: str) -> dict:
    web = cached(WEB_CACHE, q, web_search)
    rows = web["results"][:8]
    if not rows:
        return {"q": q, "answer": "", "sources": [], "error": "no results"}
    ctx = "\n".join(f"[{i}] {r['title']} ({r['host']}): {r['snippet']}" for i, r in enumerate(rows, 1))
    body = {
        "model": LLM_MODEL, "max_tokens": 900, "temperature": 0.2, "reasoning_effort": "low",
        "messages": [{"role": "system", "content": OVERVIEW_SYSTEM % time.strftime("%Y-%m-%d")},
                     {"role": "user", "content": f"Query: {q}\n\nSources:\n{ctx}"}],
    }
    req = urllib.request.Request(LLM_URL, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json", "Authorization": "Bearer " + TINFOIL_KEY})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=40) as r:  # nosec B310 loopback
        d = json.load(r)
    answer = (d["choices"][0]["message"].get("content") or "").strip()
    answer = re.sub(r"【(\d+)[^】]*】", r"[\1]", answer)
    return {"q": q, "answer": answer, "sources": [{"n": i, "url": r["url"], "title": r["title"], "host": r["host"]} for i, r in enumerate(rows, 1)],
            "model": LLM_MODEL, "ms": int((time.time() - t0) * 1000)}


def cached(cache: TTLCache, q: str, fn):
    key = q.lower()
    hit = cache.get(key)
    if hit is not None:
        return hit
    tag = f"{id(cache)}:{key}"
    with INFLIGHT_LOCK:
        ev = INFLIGHT.get(tag)
        owner = ev is None
        if owner:
            ev = INFLIGHT[tag] = threading.Event()
    if not owner:
        ev.wait(45)
        hit = cache.get(key)
        if hit is not None:
            return hit
    try:
        val = fn(q)
        cache.put(key, val)
        return val
    finally:
        if owner:
            with INFLIGHT_LOCK:
                INFLIGHT.pop(tag, None)
            ev.set()


# ---------------------------------------------------------------- image proxy
def public_host(url: str) -> bool:
    try:
        host = urllib.parse.urlsplit(url).hostname or ""
        for info in socket.getaddrinfo(host, None):
            ip = ipaddress.ip_address(info[4][0])
            if not ip.is_global:
                return False
        return bool(host)
    except Exception:
        return False


def fetch_image(url: str):
    for socks in (False, True):
        if not socks and not public_host(url):
            continue
        try:
            code, ctype, body = curl(url, socks=socks, timeout=15, binary=True, max_bytes=20_000_000)
        except Exception:
            continue
        if code == 200 and ctype.startswith("image/") and body:
            return ctype, body
    return None


class H(BaseHTTPRequestHandler):
    server_version = "WizardSearch/1"

    def log_message(self, fmt, *args):  # never log queries
        pass

    def _send(self, code, body: bytes, ctype: str, extra: dict | None = None):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "frame-ancestors 'self'")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, code, obj):
        self._send(code, json.dumps(obj).encode(), "application/json", {"Cache-Control": "no-store"})

    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        u = urllib.parse.urlsplit(self.path)
        path = u.path
        if path == PREFIX:
            return self._send(308, b"", "text/plain", {"Location": PREFIX + "/" + (("?" + u.query) if u.query else "")})
        if not path.startswith(PREFIX + "/"):
            return self._send(404, b"not found", "text/plain")
        path = path[len(PREFIX):]
        qs = urllib.parse.parse_qs(u.query)
        q = norm_q((qs.get("q") or [""])[0])
        try:
            if path == "/api/health":
                return self._json(200, {"ok": True, "model": LLM_MODEL, "bd": bool(BD_TOKEN), "tinfoil": bool(TINFOIL_KEY)})
            if path in ("/api/images", "/api/web", "/api/overview"):
                if not q:
                    return self._json(400, {"error": "empty query"})
                cache, fn = {"/api/images": (IMG_CACHE, image_search), "/api/web": (WEB_CACHE, web_search),
                             "/api/overview": (OVR_CACHE, overview)}[path]
                return self._json(200, cached(cache, q, fn))
            m = re.fullmatch(r"/(img|thumb)/([0-9a-f]{20})\.jpg", path)
            if m:
                src = IMG_IDS.get(("t" if m.group(1) == "thumb" else "") + m.group(2))
                if not src:
                    return self._send(404, b"expired", "text/plain")
                got = THUMBS.get(m.group(2)) if m.group(1) == "thumb" else None
                if not got:
                    got = fetch_image(src)
                    if got and m.group(1) == "thumb" and len(got[1]) < 400_000:
                        THUMBS.put(m.group(2), got)
                if not got:
                    return self._send(302, b"", "text/plain", {"Location": src})
                return self._send(200, got[1], got[0], {"Cache-Control": "private, max-age=86400"})
            return self._static(path)
        except Exception as e:  # noqa: BLE001
            return self._json(502, {"error": type(e).__name__})

    def _static(self, path):
        if path in ("", "/"):
            path = "/index.html"
        f = (WEB / path.lstrip("/")).resolve()
        if WEB not in f.parents or not f.is_file():
            return self._send(404, b"not found", "text/plain")
        ctype = {".html": "text/html; charset=utf-8", ".js": "text/javascript", ".css": "text/css",
                 ".png": "image/png", ".svg": "image/svg+xml", ".webmanifest": "application/manifest+json"}.get(f.suffix, "application/octet-stream")
        return self._send(200, f.read_bytes(), ctype, {"Cache-Control": "no-cache"})


if __name__ == "__main__":
    ThreadingHTTPServer.daemon_threads = True
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), H)
    print(f"wizard-search on 127.0.0.1:{PORT}{PREFIX}/", flush=True)
    srv.serve_forever()
