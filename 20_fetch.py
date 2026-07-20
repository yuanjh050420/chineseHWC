#!/usr/bin/env python3
"""Stage 2 (Fetch) — download discovered candidate URLs and extract article text.

Polite + resumable + bot-block resilient (see tools/http.py):
  - per-host rate limiting, rotating UAs, robots.txt, retry/backoff
  - charset detection (fixes GB2312/GBK mojibake on older CN pages)
  - anti-bot interstitials detected and marked 'blocked' (not ingested as text)
  - CAPTURES PUBLICATION DATE from page metadata + the discovery feed's pubdate,
    because the incident year/month often live only in the header, not the body.

Resumable: only fetches candidates not already cached ok/dead. Safe to re-run.

Examples:
  ./20_fetch.py                     # fetch all pending discovered candidates
  ./20_fetch.py --limit 200         # cap this run
  ./20_fetch.py --workers 8
  ./20_fetch.py --source chinanews  # only candidates from one outlet
"""
from __future__ import annotations  # py3.9: keep `str | None` hints lazy (user's Mac is 3.9.6)
import argparse, sys, threading
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
sys.path.insert(0, str(Path(__file__).resolve().parent))
import re as _re
import trafilatura
from tools import http, cache

_wlock = threading.Lock()

# og:image / twitter:image — a representative photo for the article, used as a
# popup thumbnail on the dashboard. Best-effort; many CN pages omit it.
_OG_IMAGE_RE = _re.compile(
    r'<meta[^>]+(?:property|name)=["\'](?:og:image|twitter:image)(?::url)?["\'][^>]+content=["\']([^"\']+)["\']',
    _re.I)
_OG_IMAGE_RE2 = _re.compile(
    r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:property|name)=["\'](?:og:image|twitter:image)(?::url)?["\']',
    _re.I)


def _extract_image(html: str, base_url: str) -> str | None:
    for rx in (_OG_IMAGE_RE, _OG_IMAGE_RE2):
        m = rx.search(html or "")
        if m:
            u = m.group(1).strip()
            if u.startswith("//"):
                u = "https:" + u
            elif u.startswith("/"):
                from urllib.parse import urljoin
                u = urljoin(base_url, u)
            if u.startswith("http"):
                return u[:500]
    return None


def fetch_one(url: str, feed_pubdate: str = "") -> tuple:
    try:
        resp = http.fetch(url)
        if resp.status_code >= 400:
            return url, ("dead", resp.status_code, None, None, None, None, None, f"http {resp.status_code}")
        html = resp.text
        text = trafilatura.extract(html, include_comments=False, favor_recall=True)
        md = trafilatura.extract_metadata(html)
        title = md.title if md else None
        # publication date: prefer page metadata, fall back to the feed's pubdate
        pub = (md.date if md and md.date else None) or (feed_pubdate or None)
        img = (md.image if md and getattr(md, "image", None) else None) or _extract_image(html, resp.url)
        if text and len(text) > 80:
            return url, ("ok", resp.status_code, resp.url, text, title, pub, img, None)
        return url, ("dead", resp.status_code, resp.url, None, None, pub, None, "no extractable text")
    except http.Blocked as e:
        return url, ("blocked", None, None, None, None, None, None, str(e)[:200])
    except Exception as e:
        return url, ("error", None, None, None, None, None, None, str(e)[:200])


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--limit", type=int, help="max candidates to fetch this run")
    ap.add_argument("--workers", type=int, default=12)
    ap.add_argument("--source", help="only fetch candidates from this source_key")
    ap.add_argument("--force", action="store_true", help="refetch even if cached ok/dead")
    args = ap.parse_args()

    con = cache.connect()
    q = "SELECT url, pubdate FROM discovered"
    params = []
    if args.source:
        q += " WHERE source_key = ?"; params.append(args.source)
    cands = con.execute(q, params).fetchall()

    def done(u):
        r = con.execute("SELECT status FROM fetched WHERE url=?", (u,)).fetchone()
        return r and r[0] in ("ok", "dead")

    todo = [(r["url"], r["pubdate"] or "") for r in cands if args.force or not done(r["url"])]
    if args.limit:
        todo = todo[: args.limit]
    print(f"[fetch] candidates: {len(cands)} | to fetch: {len(todo)}", flush=True)

    stats = {"ok": 0, "dead": 0, "blocked": 0, "error": 0}
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(fetch_one, u, pd): u for u, pd in todo}
        n = 0
        for fut in as_completed(futs):
            url, (status, code, final, text, title, pub, img, err) = fut.result()
            with _wlock:
                cache.save_fetched(con, url, status, http_code=code, final_url=final,
                                   text=text, title=title, pub_date=pub, image_url=img, error=err)
            stats[status] += 1
            n += 1
            if n % 25 == 0:
                print(f"[fetch] {n}/{len(todo)} {stats}", flush=True)
    print(f"[fetch] done {stats}")
    ok = con.execute("SELECT COUNT(*) FROM fetched WHERE status='ok'").fetchone()[0]
    print(f"[fetch] total articles with text: {ok}")


if __name__ == "__main__":
    main()
