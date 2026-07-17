"""Discovery helpers: turn curated outlets + search terms into candidate URLs.

Two channels (per the user's "named sites + RSS only" choice):
  1. RSS feeds the outlet actually publishes (probed for liveness).
  2. On-site search pages (search_url templates) queried with species×keyword terms.
The optional Google News RSS aggregator is OFF by default (config toggle).

Everything is best-effort and logged: which feeds were live, how many items each
channel returned. A feed that 404s is recorded, not silently dropped.
"""
from __future__ import annotations
import time, urllib.parse, datetime as dt
import feedparser
from . import http, cache
from .config import all_sources, sources as _sources, build_queries


def probe_feed(url: str) -> tuple[bool, int, list[dict]]:
    """Fetch+parse an RSS/Atom feed. Returns (ok, n_items, items)."""
    try:
        resp = http.fetch(url)
        if resp.status_code >= 400:
            return False, 0, []
        fp = feedparser.parse(resp.content)
        items = []
        for e in fp.entries:
            link = e.get("link")
            if not link:
                continue
            pub = e.get("published") or e.get("updated") or ""
            items.append({"url": link, "title": e.get("title", ""), "pubdate": pub})
        return (len(items) > 0), len(items), items
    except http.Blocked:
        return False, 0, []
    except Exception:
        return False, 0, []


def within_window(pubdate: str, lookback_days: int | None) -> bool:
    if not lookback_days:
        return True
    try:
        t = feedparser._parse_date(pubdate)
        if not t:
            return True  # keep undated; dedup + extract will sort it out
        d = dt.datetime(*t[:6])
        return d >= dt.datetime.utcnow() - dt.timedelta(days=lookback_days)
    except Exception:
        return True


def discover_rss(con, source: dict, lookback_days: int | None) -> int:
    """Poll all candidate RSS feeds for one source; cache candidate URLs."""
    added = 0
    for feed in source.get("rss", []) or []:
        ok, n, items = probe_feed(feed)
        cache.log_liveness(con, source["key"], feed, "rss", ok, n)
        if not ok:
            continue
        rows = [{"url": it["url"], "source_key": source["key"], "title": it["title"],
                 "pubdate": it["pubdate"], "query": "rss"}
                for it in items if within_window(it["pubdate"], lookback_days)]
        cache.save_discovered(con, rows)
        added += len(rows)
    return added


def discover_search(con, source: dict, queries: list[dict], max_per_source: int) -> int:
    """Query the outlet's on-site search for each species×keyword term and scrape
    result-page links. Search-result HTML varies per site, so we extract anchor
    hrefs that look like article URLs on the same host and let the fetch+extract
    stages decide. Best-effort; a site whose search blocks us is logged."""
    tmpl = source.get("search_url")
    if not tmpl:
        return 0
    import re
    from bs4 import BeautifulSoup
    host = urllib.parse.urlparse(tmpl).netloc
    seen, rows = set(), []
    for q in queries:
        if len(rows) >= max_per_source:
            break
        url = tmpl.replace("{q}", urllib.parse.quote(q["query"]))
        try:
            resp = http.fetch(url)
        except http.Blocked:
            cache.log_liveness(con, source["key"], tmpl, "search", False, 0, note=f"blocked: {q['query']}")
            break
        except Exception:
            continue
        if resp.status_code >= 400:
            continue
        soup = BeautifulSoup(resp.text, "lxml")
        for a in soup.find_all("a", href=True):
            href = urllib.parse.urljoin(url, a["href"])
            # keep same-outlet article-looking links; drop nav/search/js
            if host.split(".")[-2] not in href:
                continue
            if any(x in href for x in ("search", "javascript:", "#", "login", "/tag/")):
                continue
            if not re.search(r"/(20\d{2}|a?\d{5,}|\w+/\d)", href):
                continue
            if href in seen:
                continue
            seen.add(href)
            rows.append({"url": href, "source_key": source["key"],
                         "title": a.get_text(strip=True)[:200], "pubdate": "",
                         "query": q["query"]})
            if len(rows) >= max_per_source:
                break
    cache.save_discovered(con, rows)
    cache.log_liveness(con, source["key"], tmpl, "search", len(rows) > 0, len(rows))
    return len(rows)


def discover_google_news(con, queries: list[dict], max_items: int) -> int:
    """OFF by default. Opt-in fallback: general-engine aggregator."""
    cfg = _sources().get("google_news_rss", {})
    if not cfg.get("enabled"):
        return 0
    ep = cfg["endpoint"]
    rows = []
    for q in queries:
        url = ep.replace("{q}", urllib.parse.quote(q["query"]))
        ok, n, items = probe_feed(url)
        for it in items[:max_items]:
            rows.append({"url": it["url"], "source_key": "google_news",
                         "title": it["title"], "pubdate": it["pubdate"], "query": q["query"]})
    cache.save_discovered(con, rows)
    cache.log_liveness(con, "google_news", ep, "rss", len(rows) > 0, len(rows))
    return len(rows)
