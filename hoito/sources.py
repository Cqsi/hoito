"""Exa tools for the agent, plus the source registry every citation points into."""
import asyncio
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

from exa_py import AsyncExa

from .config import OFFICIAL, PRIVATE

SEARCH_TTL = 3600       # cache searches for an hour so repeat demos are fast
EXCERPT_CHARS = 900     # page text shown to the model per search result (full text is kept for quote checks)
MAX_SHOWN = 8           # results shown to the model per search
READ_CHARS = 9000       # page text shown to the model by read_page


def domain(url: str) -> str:
    host = urlparse(url).netloc.lower()
    try:
        host = host.encode().decode("idna")  # xn--espootnn-5zaba.fi → espootänään.fi
    except UnicodeError:
        pass
    return host[4:] if host.startswith("www.") else host


@dataclass
class Source:
    id: str
    url: str
    title: str
    domain: str
    published: str | None
    crawled: str | None
    kind: str                 # official | private | news
    text: str = ""            # everything we fetched; quotes are checked against this
    live: bool = False        # fetched within the last minute by read_page


@dataclass
class Registry:
    """One per question. Same URL → same source id, with the longest text kept."""
    by_url: dict[str, Source] = field(default_factory=dict)
    exa_cost: float = 0.0
    exa_calls: int = 0

    def add(self, r, kind: str, live: bool = False) -> Source:
        text = "\n".join(filter(None, [getattr(r, "text", None), *(getattr(r, "highlights", None) or [])]))
        s = self.by_url.get(r.url)
        if s is None:
            s = Source(id=f"S{len(self.by_url) + 1}", url=r.url, title=(r.title or domain(r.url)).strip(),
                       domain=domain(r.url), published=(r.published_date or None), crawled=getattr(r, "crawl_date", None),
                       kind=kind, text=text, live=live)
            self.by_url[r.url] = s
        else:
            if len(text) > len(s.text):
                s.text = text
            s.live = s.live or live
            s.crawled = getattr(r, "crawl_date", None) or s.crawled
        return s

    def get(self, sid: str) -> Source | None:
        return next((s for s in self.by_url.values() if s.id == sid), None)

    def public(self) -> list[dict]:
        return [{k: v for k, v in s.__dict__.items() if k != "text"} for s in self.by_url.values()]


_client: AsyncExa | None = None
_cache: dict[tuple, tuple[float, object]] = {}
_gate: asyncio.Semaphore | None = None  # Exa allows 10 search QPS per team; stay well under it


def client() -> AsyncExa:
    global _client
    if _client is None:
        _client = AsyncExa(api_key=os.environ["EXA_API_KEY"])
    return _client


async def exa_call(method: str, *args, **kw):
    """Every Exa request goes through here: at most 5 at a time, retried with backoff on 429/5xx."""
    global _gate
    if _gate is None:
        _gate = asyncio.Semaphore(int(os.getenv("HOITO_EXA_PARALLEL", "5")))
    for attempt in range(4):
        async with _gate:
            try:
                return await getattr(client(), method)(*args, **kw)
            except Exception as e:
                msg = str(e)
                if attempt == 3 or not any(code in msg for code in ("429", "502", "503", "504")):
                    raise
        await asyncio.sleep(0.6 * 2 ** attempt)


def _cost(resp) -> float:
    c = getattr(resp, "cost_dollars", None)
    return float(getattr(c, "total", 0) or 0) if c else 0.0


async def _search(reg: Registry, cache_key: tuple, **kw):
    hit = _cache.get(cache_key)
    if hit and time.time() - hit[0] < SEARCH_TTL:
        return hit[1]
    resp = await exa_call("search", **kw)
    reg.exa_calls += 1
    reg.exa_cost += _cost(resp)
    _cache[cache_key] = (time.time(), resp)
    return resp


def _format(reg: Registry, results, kind: str, chars: int = EXCERPT_CHARS) -> dict:
    out = []
    for r in results[:MAX_SHOWN]:
        s = reg.add(r, kind)
        hl = [h.strip() for h in (r.highlights or []) if h and h.strip()]
        body = "\n…\n".join(hl) if hl else (r.text or "")
        out.append({"source_id": s.id, "title": s.title, "url": s.url, "published": s.published,
                    "excerpt": body[:chars]})
    return {"results": out} if out else {"results": [], "note": "No results. Try other words (Finnish or English) or other domains."}


# Requests follow Exa's build-with-exa guidance: query + objective + bare highlights.
# includeDomains is a deliberate product rule (official and approved provider sites only), not decoration.
_HL = {"highlights": True}


async def search_official(reg: Registry, query: str, objective: str, domains: list[str] | None = None) -> dict:
    doms = sorted(set(domains or OFFICIAL))
    resp = await _search(reg, ("off", query, objective, tuple(doms)), query=query, objective=objective, type="auto",
                         include_domains=doms, user_location="FI", contents=_HL)
    return _format(reg, resp.results, "official")


async def search_private(reg: Registry, query: str, objective: str) -> dict:
    resp = await _search(reg, ("priv", query, objective), query=query, objective=objective, type="auto",
                         include_domains=PRIVATE, user_location="FI", contents=_HL)
    return _format(reg, resp.results, "private")


async def news_check(reg: Registry, query: str, objective: str, days: int = 30) -> dict:
    """News from the last 30 days: a bounded window the product enforces, so the date filter is a hard rule."""
    since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%dT00:00:00.000Z")
    resp = await _search(reg, ("news", query, objective, since[:10]), query=query, objective=objective, type="auto",
                         start_published_date=since, user_location="FI", contents=_HL)
    return _format(reg, resp.results, "news", chars=1200)


async def read_page(reg: Registry, url: str) -> dict:
    """Fetches the page live (max_age_hours=0) so fees and opening hours are today's."""
    resp = await exa_call("get_contents", [url], text={"max_characters": 30000}, max_age_hours=0, livecrawl_timeout=12000)
    reg.exa_calls += 1
    reg.exa_cost += _cost(resp)
    if not resp.results or not (resp.results[0].text or "").strip():
        # Live fetch failed or came back empty (some sites block crawlers): use Exa's cached copy instead.
        resp = await exa_call("get_contents", [url], text={"max_characters": 30000})
        reg.exa_calls += 1
        reg.exa_cost += _cost(resp)
        if not resp.results or not (resp.results[0].text or "").strip():
            return {"error": "Could not fetch this page. Cite the search excerpt instead, or pick another result."}
        live = False
    else:
        live = True
    r = resp.results[0]
    kind = "private" if domain(r.url) in PRIVATE else "official"
    s = reg.add(r, kind, live=live)
    return {"source_id": s.id, "title": s.title, "url": s.url, "published": s.published,
            "fetched": "live, just now" if live else "cached copy", "text": (r.text or "")[:READ_CHARS]}


async def run_tool(reg: Registry, name: str, args: dict) -> dict:
    fn = {"search_official": search_official, "search_private": search_private,
          "news_check": news_check, "read_page": read_page}[name]
    return await asyncio.wait_for(fn(reg, **args), timeout=45)
