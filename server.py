#!/usr/bin/env python3
"""Wizard Search: private image search + AI overview, served inside Wizard's link sheet.

Routes (all under /wizard-search):
  GET  /                      the app (dark, phone-first)
  GET  /api/images?q=         image results (Bing images over the Thales residential tunnel; Bright Data fallback)
  GET  /api/web?q=            web results (Bright Data SERP, parsed; local Firecrawl router fallback)
  GET  /api/overview?q=       short cited answer over the web results (Tinfoil private inference)
  GET  /img/<id>.jpg          full-size image proxy, only for ids issued by a recent image search
  POST /api/translate         {"items": [...], "to": "English"} → same-order translations (Tinfoil gemma4-31b, gpt-oss fallback)
  POST /api/read-image        screenshot bytes → {"lines": [...]} (Tinfoil gemma4-31b vision), for screens with no text layer
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
import unicodedata
import urllib.parse
import urllib.request
from collections import OrderedDict
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
WEB = ROOT / "web"
PREFIX = os.environ.get("WIZARD_SEARCH_BASE", "/wizard-search").rstrip("/")
PORT = int(os.environ.get("WIZARD_SEARCH_PORT", "9288"))
SOCKS = os.environ.get("WIZARD_SEARCH_SOCKS", "")
LLM_URL = os.environ.get("TINFOIL_PROXY_URL", "")
LLM_MODEL = os.environ.get("WIZARD_SEARCH_MODEL", "gpt-oss-120b")
FIRECRAWL_URL = os.environ.get("FIRECRAWL_ROUTER_URL", "")
# Free, keyless default: the SearXNG metasearch sidecar that ships in this app's Compose file.
SEARXNG_URL = os.environ.get("SEARXNG_URL", "").rstrip("/")
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36"


TINFOIL_KEY = os.environ.get("TINFOIL_API_KEY", "")
# Optional AI overviews through the Tinfoil app on this box: the owner turns them on from Search's page, Tinfoil
# issues Search its own box-only token, and Search keeps it in DATA_DIR (0600). TINFOIL_PROXY_URL (operator
# setting) still wins when set. Search never sees the Tinfoil API key.
DATA_DIR = Path(os.environ.get("WIZARD_SEARCH_DATA", "/data"))
TINFOIL_APP = os.environ.get("WIZARD_SEARCH_TINFOIL_APP", "http://wizard-tinfoil:18804").rstrip("/")
LINK_FILE = "overview-provider.json"


def _link() -> dict | None:
    try:
        d = json.loads((DATA_DIR / LINK_FILE).read_text())
        return d if d.get("provider") == "tinfoil" and d.get("token") else None
    except (OSError, ValueError):
        return None


def _pick(models: list, *want: str) -> str:
    for m in want:
        if m in models:
            return m
    return models[0] if models else want[0]


def llm() -> dict | None:
    """Where AI calls go right now: the operator's proxy, the linked Tinfoil app, or nowhere."""
    if LLM_URL:
        return {"via": "proxy", "url": LLM_URL, "key": TINFOIL_KEY, "model": LLM_MODEL, "translate": TRANSLATE_MODEL,
                "fallback": TRANSLATE_FALLBACK, "vision": VISION_MODEL}
    link = _link()
    if not link:
        return None
    models = link.get("models") or []
    main = _pick(models, LLM_MODEL, *(link.get("recommended") or []))
    return {"via": "tinfoil-app", "url": TINFOIL_APP + "/v1/chat/completions", "key": link["token"], "model": main,
            "translate": _pick(models, TRANSLATE_MODEL, main), "fallback": _pick(models, TRANSLATE_FALLBACK, main),
            "vision": _pick(models, VISION_MODEL, main)}


TINFOIL_PROBE = {"at": 0.0, "data": None}


def tinfoil_app_status(force: bool = False) -> dict:
    """Is the Tinfoil app installed and connected on this box? Cached ~90 s; never raises."""
    if not force and time.time() - TINFOIL_PROBE["at"] < 90 and TINFOIL_PROBE["data"] is not None:
        return TINFOIL_PROBE["data"]
    out = {"installed": False, "connected": False}
    try:
        with urllib.request.urlopen(TINFOIL_APP + "/api/connection", timeout=2) as r:  # nosec B310 box-only peer
            d = json.load(r)
        out = {"installed": True, "connected": d.get("status") == "connected" or bool(d.get("credentialStored"))}
    except Exception:
        pass
    link = _link()
    if link and out["installed"]:
        # Removed on the Tinfoil page: drop the dead link so the switch shows Off instead of failing answers.
        try:
            urllib.request.urlopen(urllib.request.Request(TINFOIL_APP + "/v1/models", headers={"Authorization": "Bearer " + link["token"]}), timeout=3).close()  # nosec B310
        except urllib.error.HTTPError as e:
            if e.code == 401:
                unlink_tinfoil_file()
        except Exception:
            pass
    TINFOIL_PROBE.update(at=time.time(), data=out)
    return out


def overview_provider() -> dict:
    cfg = llm()
    return {"mode": cfg["via"] if cfg else "off", "model": cfg["model"] if cfg else None,
            "tinfoil": tinfoil_app_status()}


def link_tinfoil(token: str, models: list, recommended: list) -> dict:
    """Check the token Tinfoil just issued by listing models through it, then keep it (0600)."""
    if not isinstance(token, str) or not 20 <= len(token) <= 200 or not token.isascii():
        raise ValueError("bad token")
    req = urllib.request.Request(TINFOIL_APP + "/v1/models", headers={"Authorization": "Bearer " + token})
    with urllib.request.urlopen(req, timeout=8) as r:  # nosec B310 box-only peer
        live = [m.get("id") for m in json.load(r).get("data") or [] if isinstance(m, dict)]
    clean = lambda xs: [m for m in xs if isinstance(m, str) and m in live][:40]
    models = clean(models) or live
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp = DATA_DIR / (LINK_FILE + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump({"provider": "tinfoil", "token": token, "models": models, "recommended": clean(recommended),
                   "linkedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}, f)
    os.replace(tmp, DATA_DIR / LINK_FILE)
    with OVR_CACHE.lock:
        OVR_CACHE.d.clear()
    TINFOIL_PROBE["at"] = 0.0
    return overview_provider()


def unlink_tinfoil_file() -> None:
    try:
        (DATA_DIR / LINK_FILE).unlink()
    except FileNotFoundError:
        pass


def unlink_tinfoil() -> dict:
    unlink_tinfoil_file()
    TINFOIL_PROBE["at"] = 0.0
    return overview_provider()
BD_TOKEN = os.environ.get("BRIGHTDATA_API_TOKEN", "")
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
FULLS = TTLCache(24, 1800)  # full-size bytes just viewed, so Save doesn't fetch them again
THUMBS = TTLCache(800, 3600)  # thumbnail bytes, so re-opening a search paints instantly  # id -> original image URL (the proxy serves nothing else)
INFLIGHT: dict[str, threading.Event] = {}
INFLIGHT_LOCK = threading.Lock()


def norm_q(q: str) -> str:
    return re.sub(r"\s+", " ", (q or "")).strip()[:300]


def curl(url: str, *, socks: bool, timeout: int = 15, binary: bool = False, max_bytes: int = 0):
    if socks and not SOCKS:
        raise RuntimeError("SOCKS egress is not configured")
    args = ["curl", "-s", "-L", "--max-redirs", "4", "-m", str(timeout), "-A", UA, "--compressed",
            "-H", "Accept-Language: en-US,en;q=0.9", "-w", "\n%{http_code} %{content_type}"]
    if socks:
        args += ["-x", SOCKS]
    if max_bytes:
        args += ["--max-filesize", str(max_bytes)]
    if binary:
        # Never follow an image publisher redirect into a private network.
        args += ["--max-redirs", "0", "--proto", "=http,https"]
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


def _searx(q: str, category: str = "general") -> list[dict]:
    """Bundled SearXNG sidecar: free, no account, fans out to several public engines at once."""
    if not SEARXNG_URL:
        raise RuntimeError("searxng not configured")
    qs = urllib.parse.urlencode({"q": q, "format": "json", "categories": category, "language": "en", "safesearch": 1})
    req = urllib.request.Request(SEARXNG_URL + "/search?" + qs, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as r:  # nosec B310 private sidecar
        d = json.load(r)
    return [x for x in d.get("results") or [] if str(x.get("url", "")).startswith(("http://", "https://"))
            and urllib.parse.urlsplit(str(x["url"])).hostname]  # Bing sometimes yields "http:///videos/..."


def _searx_web(q: str) -> list[dict]:
    rows = [{"url": x["url"], "title": x.get("title") or x["url"], "snippet": x.get("content") or ""} for x in _searx(q)]
    if not rows:
        raise RuntimeError("empty searxng")
    return rows


def _searx_images(q: str) -> list[dict]:
    out, seen = [], set()
    for x in _searx(q, "images"):
        full = x.get("img_src") or ""
        if full.startswith("//"):
            full = "https:" + full
        if not full.startswith(("http://", "https://")) or full in seen:
            continue
        seen.add(full)
        thumb = x.get("thumbnail_src") or ""
        if thumb.startswith("//"):
            thumb = "https:" + thumb
        item = {"full": full, "thumb": thumb if thumb.startswith(("http://", "https://")) else full,
                "title": x.get("title") or "", "page": x.get("url") or full, "desc": x.get("content") or ""}
        dm = re.match(r"\s*(\d+)\s*[x×]\s*(\d+)", str(x.get("resolution") or ""))
        if dm:
            item["w"], item["h"] = int(dm.group(1)), int(dm.group(2))
        out.append(item)
        if len(out) >= 60:
            break
    return out


def image_search(q: str) -> dict:
    qs = urllib.parse.urlencode({"q": q, "first": 1, "count": 60, "mmasync": 1, "setlang": "en-US", "adlt": "moderate"})
    url = "https://www.bing.com/images/async?" + qs
    items, source = [], ""
    if SEARXNG_URL:
        try:
            items, source = _searx_images(q), "searxng"
        except Exception:
            pass
    if len(items) < 6 and SOCKS:
        try:
            code, _, page = curl(url, socks=True, timeout=12)
            more = parse_bing_images(page) if code == 200 else []
            if len(more) > len(items):
                items, source = more, "bing"
        except Exception:
            pass
    if len(items) < 6 and BD_TOKEN:
        try:
            page = bd_request({"zone": BD_UNLOCK_ZONE, "url": url, "format": "raw"}, timeout=30).decode("utf8", "replace")
            more = parse_bing_images(page)
            if len(more) > len(items):
                items, source = more, "bing via unlocker"
        except Exception:
            pass
    for it in items:
        if not it["page"].startswith(("https://", "http://")):
            it["page"] = it["full"]
        iid = hashlib.sha1(it["full"].encode()).hexdigest()[:20]
        IMG_IDS.put(iid, it["full"])
        IMG_IDS.put("t" + iid, it["thumb"])
        it["id"] = iid
        it["host"] = urllib.parse.urlsplit(it["page"] or it["full"]).hostname or ""
        it["host"] = re.sub(r"^www\.", "", it["host"])
    if not items:
        raise RuntimeError("image providers unavailable or returned no results")
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
    if not FIRECRAWL_URL:
        raise RuntimeError("local Firecrawl router not configured")
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
FC_CLOUD_URL = os.environ.get("FIRECRAWL_CLOUD_URL", "https://api.firecrawl.dev").rstrip("/")
FC_CLOUD_KEY = os.environ.get("FIRECRAWL_CLOUD_API_KEY", "")
DDG_COOLDOWN = {"until": 0.0}


def configuration() -> dict:
    providers = {"searxng": bool(SEARXNG_URL), "socks": bool(SOCKS), "firecrawl_cloud": bool(FC_CLOUD_KEY),
                 "brightdata": bool(BD_TOKEN), "firecrawl_router": bool(FIRECRAWL_URL),
                 "tinfoil": bool(llm())}
    web = any(providers[k] for k in ("searxng", "socks", "firecrawl_cloud", "brightdata", "firecrawl_router"))
    capabilities = {"web": web, "images": bool(SEARXNG_URL or SOCKS or BD_TOKEN), "overview": bool(web and llm())}
    return {"state": "configured" if web else "setup_required", "capabilities": capabilities,
            "providers": providers, "setup": "SETUP.md", "requirements": "setup.json",
            "notice": "Configured means settings are present, not that providers are reachable."}


def setup_error(capability: str) -> dict:
    return {"error": "setup_required", "capability": capability,
            "message": f"Configure {capability} providers using SETUP.md. No keys ship with Search.",
            "configuration": configuration()}


def _cloud(q: str) -> list[dict]:
    """Firecrawl Cloud search: consistently ~1.5-3 s, 2 credits a query (already-paid plan)."""
    if not FC_CLOUD_KEY:
        raise RuntimeError("no firecrawl cloud key")
    req = urllib.request.Request(FC_CLOUD_URL + "/v2/search", data=json.dumps({"query": q, "limit": 8}).encode(),
                                 headers={"Content-Type": "application/json", "Authorization": "Bearer " + FC_CLOUD_KEY})
    with urllib.request.urlopen(req, timeout=12) as r:  # nosec B310 constant host
        d = json.load(r)
    rows = [{"url": x["url"], "title": x.get("title") or x["url"], "snippet": x.get("description") or ""}
            for x in (d.get("data") or {}).get("web") or [] if x.get("url")]
    if not rows:
        raise RuntimeError("empty cloud")
    return rows


def _ddg(q: str) -> list[dict]:
    """DuckDuckGo HTML through the Thales residential egress: ~1 s and free, but it challenges after a
    handful of queries, so it sits out for 10 minutes after any challenge."""
    if not SOCKS or time.time() < DDG_COOLDOWN["until"]:
        raise RuntimeError("ddg cooling down")
    out = subprocess.run(["curl", "-s", "-m", "4", "-x", SOCKS, "-A", UA, "-H", "Accept-Language: en-US,en;q=0.9",
                          "--data-urlencode", "q=" + q, "--data", "kl=us-en", "https://html.duckduckgo.com/html/"],
                         capture_output=True, text=True, timeout=6).stdout
    rows = []
    for m in re.finditer(r'<a rel="nofollow" class="result__a" href="([^"]+)">(.*?)</a>.*?<a class="result__snippet"[^>]*>(.*?)</a>', out, re.S):
        u = html.unescape(m.group(1))
        red = re.search(r"uddg=([^&]+)", u)
        if red:
            u = urllib.parse.unquote(red.group(1))
        if not u.startswith(("http://", "https://")) or "duckduckgo.com/y.js" in u:
            continue
        clean = lambda v: " ".join(html.unescape(re.sub(r"<[^>]+>", " ", v)).split())
        rows.append({"url": u, "title": clean(m.group(2)), "snippet": clean(m.group(3))})
    if not rows:
        DDG_COOLDOWN["until"] = time.time() + 600
        raise RuntimeError("ddg challenged")
    return rows


def web_search(q: str) -> dict:
    """Speed first: DuckDuckGo (free, ~1 s) gets a 1.2 s head start, then Firecrawl Cloud (~1.5 s, paid) joins;
    the first relevant batch wins.
    Google SERP (Bright Data, 2-40 s) and the local lane only join if both fast lanes fail."""
    started = time.time()
    futs = {}
    if SEARXNG_URL:
        futs[POOL.submit(_searx_web, q)] = "searxng"
    if SOCKS and time.time() >= DDG_COOLDOWN["until"]:
        futs[POOL.submit(_ddg, q)] = "ddg"
    # Free lanes get a head start; a paid lane (if any) only joins when they stall.
    cloud_at = started + ((3.0 if SEARXNG_URL else 1.2) if futs else 0)  # free lane gets a short head start; paid lane only if it stalls
    cloud_started = slow_started = False
    while time.time() - started < 30:
        if not cloud_started and (time.time() >= cloud_at or not futs):
            if FC_CLOUD_KEY:
                futs[POOL.submit(_cloud, q)] = "cloud"
            cloud_started = True
        if not futs and not slow_started:
            if BD_TOKEN:
                futs[POOL.submit(_serp, q)] = "serp"
            if FIRECRAWL_URL:
                futs[POOL.submit(_local, q)] = "local"
            slow_started = True
        if not futs:
            break
        done, _ = wait(list(futs), timeout=0.2 if not cloud_started else 0.5, return_when=FIRST_COMPLETED)
        for f in done:
            lane = futs.pop(f)
            try:
                rows = f.result()
            except Exception:
                continue
            if lane in ("searxng", "ddg", "local") and not _relevant(q, rows):
                continue
            return _finish(q, rows, lane)
        fast_left = not cloud_started or any(v in ("searxng", "ddg", "cloud") for v in futs.values())
        if not slow_started and (not fast_left or time.time() - started > 6):
            if BD_TOKEN:
                futs[POOL.submit(_serp, q)] = "serp"
            if FIRECRAWL_URL:
                futs[POOL.submit(_local, q)] = "local"
            slow_started = True
    raise RuntimeError("web providers unavailable or returned no results")


def _finish(q: str, rows: list[dict], source: str) -> dict:
    rows = [r for r in rows if str(r.get("url", "")).startswith(("https://", "http://"))]
    for r in rows:
        r["host"] = re.sub(r"^www\.", "", urllib.parse.urlsplit(r["url"]).hostname or "")
        sn = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", r.get("snippet") or "")          # images
        sn = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", sn)                       # links -> text
        sn = re.sub(r"(^|\s)#{1,6}\s+", r"\1", sn)                                # headings
        sn = re.sub(r"[*_`]{1,3}", "", sn)
        r["snippet"] = " ".join(sn.split())[:320]
    return {"q": q, "source": source, "results": rows[:10]}


OVERVIEW_SYSTEM = """You write the short answer box at the top of a search results page.
Answer the query directly from the numbered sources. 2 to 5 sentences, plain words, no preamble, no headings.
Cite sources inline as [1], [2] right after the claim they support. Use only facts the sources support.
If the query is a name, place or thing, say what it is. If it asks for options or "best", name the top few.
If the sources do not answer it, say so in one sentence. Today is %s."""


def _overview_request(q: str, rows: list[dict], stream: bool) -> urllib.request.Request:
    ctx = "\n".join(f"[{i}] {r['title']} ({r['host']}): {r['snippet']}" for i, r in enumerate(rows, 1))
    cfg = llm() or {}
    body = {
        "model": cfg.get("model", LLM_MODEL), "max_tokens": 700, "temperature": 0.2, "reasoning_effort": "low", "stream": stream,
        "messages": [{"role": "system", "content": OVERVIEW_SYSTEM % time.strftime("%Y-%m-%d")},
                     {"role": "user", "content": f"Query: {q}\n\nSources:\n{ctx}"}],
    }
    return urllib.request.Request(cfg.get("url", ""), data=json.dumps(body).encode(),
                                  headers={"Content-Type": "application/json", "Authorization": "Bearer " + cfg.get("key", "")})


def _sources(rows: list[dict]) -> list[dict]:
    return [{"n": i, "url": r["url"], "title": r["title"], "host": r["host"]} for i, r in enumerate(rows, 1)]


def _fix_cites(text: str) -> str:
    return re.sub(r"【(\d+)[^】]*】", r"[\1]", text)


def overview(q: str) -> dict:
    web = cached(WEB_CACHE, q, web_search)
    rows = web["results"][:8]
    if not rows:
        return {"q": q, "answer": "", "sources": [], "error": "no results"}
    t0 = time.time()
    with urllib.request.urlopen(_overview_request(q, rows, False), timeout=40) as r:  # nosec B310 loopback
        d = json.load(r)
    answer = _fix_cites((d["choices"][0]["message"].get("content") or "").strip())
    return {"q": q, "answer": answer, "sources": _sources(rows), "model": (llm() or {}).get("model", LLM_MODEL), "ms": int((time.time() - t0) * 1000)}


def overview_stream(q: str, emit) -> None:
    """Server-sent events: `sources` as soon as results land, then `delta` tokens, then `done`."""
    hit = OVR_CACHE.get(q.lower())
    if hit is not None:
        emit("sources", {"sources": hit.get("sources", []), "source": "cache"})
        emit("delta", {"t": hit.get("answer", "")})
        emit("done", {"model": hit.get("model", ""), "cached": True, "error": hit.get("error", "")})
        return
    t0 = time.time()
    web = cached(WEB_CACHE, q, web_search)
    rows = web["results"][:8]
    emit("sources", {"sources": _sources(rows) if rows else [], "source": web.get("source", ""), "ms": int((time.time() - t0) * 1000)})
    if not rows:
        emit("done", {"error": "no results"})
        return
    parts = []
    with urllib.request.urlopen(_overview_request(q, rows, True), timeout=40) as r:  # nosec B310 loopback
        for raw in r:
            line = raw.decode("utf-8", "ignore").strip()
            if not line.startswith("data:") or line == "data: [DONE]":
                continue
            try:
                delta = (json.loads(line[5:]).get("choices") or [{}])[0].get("delta", {}).get("content")
            except ValueError:
                continue
            if delta:
                parts.append(delta)
                emit("delta", {"t": delta})
    answer = _fix_cites("".join(parts).strip())
    model = (llm() or {}).get("model", LLM_MODEL)
    OVR_CACHE.put(q.lower(), {"q": q, "answer": answer, "sources": _sources(rows), "model": model})
    emit("done", {"model": model, "ms": int((time.time() - t0) * 1000), "answer": answer})


TRANSLATE_MODEL = os.environ.get("WIZARD_TRANSLATE_MODEL", "gemma4-31b")
TRANSLATE_FALLBACK = os.environ.get("WIZARD_TRANSLATE_FALLBACK", "gpt-oss-120b")
VISION_MODEL = os.environ.get("WIZARD_VISION_MODEL", "gemma4-31b")
TRANSLATE_SYSTEM = (
    "Translate each numbered item into natural %s as it would read in an app, on a menu or on a sign. "
    "Keep numbers, prices, names, links and emoji. If an item is already %s, return it unchanged. "
    "Reply with JSON only, no code fence: {\"from\": \"<source language(s)>\", \"items\": [\"...\"]} "
    "with exactly one entry per input item, in the same order, without the item numbers.")
READ_IMAGE_SYSTEM = (
    "Read all the text visible in this phone screenshot, top to bottom, left to right, exactly as written "
    "(keep the original language and spelling). One entry per line of text; skip the clock, battery and other "
    "status-bar icons. Reply with JSON only, no code fence: {\"lines\": [\"...\"]}")
TRANSLATE_CACHE = TTLCache(2000, 6 * 3600)


def _llm(model: str, messages: list, max_tokens: int, timeout: int) -> str:
    body = {"model": model, "temperature": 0, "max_tokens": max_tokens, "messages": messages}
    if model.startswith("gpt-oss"):
        body["reasoning_effort"] = "low"
    cfg = llm() or {}
    req = urllib.request.Request(cfg.get("url", ""), data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json", "Authorization": "Bearer " + cfg.get("key", "")})
    with urllib.request.urlopen(req, timeout=timeout) as r:  # nosec B310 loopback Tinfoil proxy
        d = json.load(r)
    return (d["choices"][0]["message"].get("content") or "").strip()


def _json_reply(text: str) -> dict:
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
    m = re.search(r"\{.*\}", t, re.S)
    return json.loads(m.group(0) if m else t)


def _strip_num(s: str) -> str:
    return re.sub(r"^\s*\d{1,3}[.)]\s+", "", str(s)).strip()


def translate_items(items: list[str], to: str = "English") -> dict:
    """On-screen text → English, item by item (private Tinfoil inference). Cached per item."""
    items = [re.sub(r"\s+", " ", str(x or "")).strip()[:1200] for x in items][:150]
    out: list[str | None] = [TRANSLATE_CACHE.get(to + "\x00" + x) for x in items]
    todo = [i for i, x in enumerate(items) if out[i] is None and x]
    langs: set[str] = set()
    t0 = time.time()
    for start in range(0, len(todo), 40):
        chunk = todo[start:start + 40]
        prompt = "\n".join(f"{n + 1}. {items[i]}" for n, i in enumerate(chunk))
        got = None
        cfg = llm() or {}
        for model in dict.fromkeys((cfg.get("translate", TRANSLATE_MODEL), cfg.get("fallback", TRANSLATE_FALLBACK))):
            try:
                j = _json_reply(_llm(model, [{"role": "system", "content": TRANSLATE_SYSTEM % (to, to)},
                                             {"role": "user", "content": prompt}], 4000, 60))
                tr = [_strip_num(s) for s in (j.get("items") or [])]
                if len(tr) == len(chunk):
                    got = tr
                    f = j.get("from")
                    for lang in (f if isinstance(f, list) else str(f or "").split(",")):
                        if str(lang).strip():
                            langs.add(str(lang).strip())
                    break
            except Exception:  # noqa: BLE001
                continue
        if got is None:
            raise RuntimeError("translate failed")
        for i, t in zip(chunk, got):
            out[i] = t
            TRANSLATE_CACHE.put(to + "\x00" + items[i], t)
    return {"to": to, "from": ", ".join(sorted(langs)), "items": [o or "" for o in out], "ms": int((time.time() - t0) * 1000)}


def read_image(data: bytes, mime: str) -> dict:
    """Text in a screenshot (pictures, video frames, canvases) when the app exposes none. Tinfoil vision model."""
    t0 = time.time()
    url = f"data:{mime};base64," + base64.b64encode(data).decode()
    vision = (llm() or {}).get("vision", VISION_MODEL)
    j = _json_reply(_llm(vision, [{"role": "system", "content": READ_IMAGE_SYSTEM},
                                        {"role": "user", "content": [{"type": "image_url", "image_url": {"url": url}},
                                                                     {"type": "text", "text": "Read the text."}]}], 4000, 90))
    lines = [re.sub(r"\s+", " ", str(x)).strip() for x in (j.get("lines") or []) if str(x).strip()][:300]
    return {"lines": lines, "model": vision, "ms": int((time.time() - t0) * 1000)}


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
IMG_EXT = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp", "image/gif": ".gif", "image/avif": ".avif",
           "image/bmp": ".bmp", "image/heic": ".heic"}


def attachment(name: str, ctype: str) -> str:
    """Content-Disposition for a saved image: the result's title as the file name, the real type's extension.
    Android's URLUtil only reads a terminal quoted filename, so the ASCII name goes last-and-only."""
    ext = IMG_EXT.get(ctype.split(";")[0].strip().lower(), ".jpg")
    n = re.sub(r"[\\/:*?\"<>|\x00-\x1f\x7f]+", " ", name or "")
    n = unicodedata.normalize("NFKD", n).encode("ascii", "ignore").decode()
    n = re.sub(r"\s+", " ", n).strip(" .")[:80].strip(" .") or "image"
    if not n.lower().endswith(ext):
        n += ext
    return f'attachment; filename="{n}"'


def public_host(url: str) -> bool:
    try:
        parsed = urllib.parse.urlsplit(url)
        if parsed.scheme not in ("http", "https") or parsed.username or parsed.password:
            return False
        host = parsed.hostname or ""
        for info in socket.getaddrinfo(host, None):
            ip = ipaddress.ip_address(info[4][0])
            if not ip.is_global:
                return False
        return bool(host)
    except Exception:
        return False


def fetch_image(url: str):
    if not public_host(url):
        return None
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

    def _mcp(self, req):
        if not isinstance(req, dict):
            return self._json(400, {"error": "invalid request"})
        rid, method = req.get("id"), req.get("method")
        if "id" not in req:
            return self._send(202, b"", "application/json")
        tools = [{"name": "search_status", "description": "Read provider configuration (no secrets).", "inputSchema": {"type": "object", "properties": {}}}]
        for kind in ("web", "images", "overview"):
            tools.append({"name": "search_" + kind, "description": "Search " + kind + "; may consume configured provider credits.", "inputSchema": {"type": "object", "properties": {"q": {"type": "string", "minLength": 1, "maxLength": 300}}, "required": ["q"], "additionalProperties": False}})
        if method == "initialize":
            result = {"protocolVersion": "2024-11-05", "capabilities": {"tools": {}}, "serverInfo": {"name": "wizard-search", "version": "0.3.0"}}
        elif method == "ping":
            result = {}
        elif method == "tools/list":
            result = {"tools": tools}
        elif method == "tools/call":
            p = req.get("params") or {}
            name = p.get("name")
            error = False
            if name == "search_status":
                data = configuration()
            elif name in ("search_web", "search_images", "search_overview"):
                kind = name[7:]
                raw = (p.get("arguments") or {}).get("q")
                if not isinstance(raw, str) or not norm_q(raw):
                    data, error = {"error": "q must be a nonempty string"}, True
                elif not configuration()["capabilities"][kind]:
                    data, error = setup_error(kind), True
                else:
                    cache, fn = {"web": (WEB_CACHE, web_search), "images": (IMG_CACHE, image_search), "overview": (OVR_CACHE, overview)}[kind]
                    try:
                        data = cached(cache, norm_q(raw), fn)
                    except Exception:
                        data, error = {"error": "provider_unavailable"}, True
            else:
                data, error = {"error": "unknown tool"}, True
            result = {"content": [{"type": "text", "text": json.dumps(data)}], "isError": error}
        else:
            return self._json(200, {"jsonrpc": "2.0", "id": rid, "error": {"code": -32601, "message": "Method not found"}})
        return self._json(200, {"jsonrpc": "2.0", "id": rid, "result": result})

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

    def do_POST(self):
        """POST /api/translate {"items": [...], "to": "English"} and POST /api/read-image (image bytes).
        Used by the Wizard OS orb's Screen mode. Native callers only: a browser page from elsewhere is refused."""
        path = urllib.parse.urlsplit(self.path).path
        if not path.startswith(PREFIX + "/"):
            return self._json(404, {"error": "not found"})
        path = path[len(PREFIX):]
        origin = self.headers.get("Origin", "")
        if self.headers.get("Sec-Fetch-Site", "") == "cross-site" or (origin and urllib.parse.urlsplit(origin).netloc != self.headers.get("Host", "")):
            return self._json(403, {"error": "cross_origin_request"})
        try:
            n = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            n = -1
        if n <= 0 or n > 8 * 1024 * 1024:
            return self._json(413 if n > 0 else 400, {"error": "bad length"})
        body = self.rfile.read(n)
        try:
            if path == "/mcp":
                return self._mcp(json.loads(body))
            if path == "/api/overview-provider":
                # Owner choice from Search's own page (same-origin + X-Wizard-Request; cross-site refused above).
                if self.headers.get("X-Wizard-Request") != "1" or self.headers.get("Content-Type", "").split(";")[0] != "application/json":
                    return self._json(403, {"error": "use_search_page"})
                j = json.loads(body)
                if not isinstance(j, dict) or j.get("provider") not in ("tinfoil", "off"):
                    return self._json(400, {"error": "provider must be tinfoil or off"})
                if j["provider"] == "off":
                    return self._json(200, unlink_tinfoil())
                try:
                    return self._json(200, link_tinfoil(j.get("token"), j.get("models") or [], j.get("recommended") or []))
                except (ValueError, OSError, urllib.error.URLError):
                    return self._json(502, {"error": "tinfoil_unreachable"})
            if path in ("/api/translate", "/api/read-image") and not llm():
                return self._json(503, setup_error("overview"))
            if path == "/api/translate":
                j = json.loads(body)
                items = j.get("items")
                if not isinstance(items, list) or not items:
                    return self._json(400, {"error": "items required"})
                to = re.sub(r"[^A-Za-z ]", "", str(j.get("to") or "English"))[:30] or "English"
                return self._json(200, translate_items(items, to))
            if path == "/api/read-image":
                mime = (self.headers.get("Content-Type") or "").split(";")[0].strip().lower()
                if mime not in ("image/png", "image/jpeg", "image/webp"):
                    return self._json(415, {"error": "image required"})
                return self._json(200, read_image(body, mime))
            return self._json(404, {"error": "not found"})
        except Exception as e:  # noqa: BLE001
            return self._json(502, {"error": type(e).__name__})

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
                return self._json(200, {"ok": True, "version": "0.3.0", "revision": os.environ.get("WIZARD_SEARCH_REVISION", "development"), **configuration()})
            if path == "/api/overview-provider":
                return self._json(200, overview_provider())
            if path == "/api/config":
                return self._json(200, configuration())
            if path in ("/api/web", "/api/images", "/api/overview", "/api/overview-stream"):
                capability = "overview" if "overview" in path else path.rsplit("/", 1)[1]
                if not configuration()["capabilities"][capability]:
                    return self._json(503, setup_error(capability))
            if path in ("/setup.json", "/openapi.json", "/SETUP.md"):
                return self._send(200, (ROOT / path.lstrip("/")).read_bytes(), "text/plain; charset=utf-8" if path.endswith(".md") else "application/json")
            if path in ("/api/images", "/api/web", "/api/overview"):
                if not q:
                    return self._json(400, {"error": "empty query"})
                cache, fn = {"/api/images": (IMG_CACHE, image_search), "/api/web": (WEB_CACHE, web_search),
                             "/api/overview": (OVR_CACHE, overview)}[path]
                return self._json(200, cached(cache, q, fn))
            if path == "/api/overview-stream":
                if not q:
                    return self._json(400, {"error": "empty query"})
                return self._sse(lambda emit: overview_stream(q, emit))
            m = re.fullmatch(r"/(img|thumb)/([0-9a-f]{20})\.jpg", path)
            if m:
                src = IMG_IDS.get(("t" if m.group(1) == "thumb" else "") + m.group(2))
                if not src:
                    return self._send(404, b"expired", "text/plain")
                thumb = m.group(1) == "thumb"
                got = (THUMBS if thumb else FULLS).get(m.group(2))
                if not got:
                    got = fetch_image(src)
                    if got and thumb and len(got[1]) < 400_000:
                        THUMBS.put(m.group(2), got)
                    elif got and not thumb and len(got[1]) < 6_000_000:
                        FULLS.put(m.group(2), got)
                if not got:
                    return self._send(502, b"image unavailable", "text/plain")
                extra = {"Cache-Control": "private, max-age=86400"}
                if "dl" in qs:  # Save: a named attachment, so Android's download manager files it under that name
                    extra["Content-Disposition"] = attachment(qs["dl"][0], got[0])
                return self._send(200, got[1], got[0], extra)
            return self._static(path)
        except Exception as e:  # noqa: BLE001
            return self._json(502, {"error": type(e).__name__})

    def _sse(self, producer):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Accel-Buffering", "no")
        self.send_header("Connection", "close")
        self.end_headers()
        self.close_connection = True

        def emit(event, data):
            self.wfile.write(f"event: {event}\ndata: {json.dumps(data)}\n\n".encode())
            self.wfile.flush()
        try:
            producer(emit)
        except (BrokenPipeError, ConnectionResetError):
            return
        except Exception as e:  # noqa: BLE001
            try:
                emit("done", {"error": type(e).__name__})
            except OSError:
                pass

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
    bind = os.environ.get("WIZARD_SEARCH_BIND", "127.0.0.1")
    srv = ThreadingHTTPServer((bind, PORT), H)
    print(f"wizard-search on {bind}:{PORT}{PREFIX}/", flush=True)
    srv.serve_forever()
