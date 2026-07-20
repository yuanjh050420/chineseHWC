"""Google News RSS link decoding.

Google News RSS feeds return links as opaque redirect tokens on news.google.com
(e.g. .../rss/articles/CBMi...), NOT the real publisher URL. They must be decoded
to the underlying article URL before we can fetch text — and so that provenance
points at the real outlet, not Google.

We use the `googlenewsdecoder` package (pure-Python; calls Google's own decoding
endpoint). Decoding is the ONLY step that touches news.google.com; the resulting
real URLs are fetched normally through tools/http.py with full robots.txt respect
against each publisher. Kept isolated here so the dependency is optional: if it's
not installed, resolve_gnews is a no-op and logs a clear message.
"""
from __future__ import annotations
import time

_GN_PREFIXES = ("https://news.google.com/rss/articles/",
                "https://news.google.com/articles/",
                "http://news.google.com/rss/articles/")


def is_gnews_redirect(url: str) -> bool:
    return bool(url) and url.startswith(_GN_PREFIXES)


def decode_one(url: str, interval: float = 1.0):
    """Decode a single Google News redirect -> real URL, or None on failure."""
    try:
        from googlenewsdecoder import gnewsdecoder
    except Exception:
        return None
    try:
        res = gnewsdecoder(url, interval=interval)
        if res and res.get("status") and res.get("decoded_url"):
            return res["decoded_url"]
    except Exception:
        return None
    return None


def resolve_gnews(con, interval: float = 1.0, progress_every: int = 25) -> dict:
    """Decode every un-resolved Google News redirect URL sitting in `discovered`,
    rewriting each row's url to the real publisher URL in place.

    Handles the PK-collision case (several Google tokens can decode to the same
    real story): if the real URL already exists, the redirect row is dropped.
    Resumable — decoded rows no longer match the redirect prefix, so a re-run only
    processes what's left. Returns {total, decoded, merged, failed}."""
    try:
        from googlenewsdecoder import gnewsdecoder  # noqa: F401
    except Exception:
        print("[gnews] googlenewsdecoder not installed — cannot decode Google News "
              "links. `pip install googlenewsdecoder` then re-run. Skipping.", flush=True)
        return {"total": 0, "decoded": 0, "merged": 0, "failed": 0, "skipped": True}

    rows = con.execute(
        "SELECT url FROM discovered WHERE url LIKE 'https://news.google.com/%articles/%' "
        "OR url LIKE 'http://news.google.com/%articles/%'").fetchall()
    total = len(rows)
    decoded = merged = failed = 0
    print(f"[gnews] decoding {total} Google News links (~{interval}s each, be patient)...", flush=True)
    for i, r in enumerate(rows, 1):
        old = r["url"]
        real = decode_one(old, interval=interval)
        if not real:
            failed += 1
        else:
            try:
                con.execute("UPDATE discovered SET url=? WHERE url=?", (real, old))
                decoded += 1
            except Exception:
                # real URL already present -> drop the redirect duplicate
                con.execute("DELETE FROM discovered WHERE url=?", (old,))
                merged += 1
        if i % progress_every == 0 or i == total:
            con.commit()
            print(f"[gnews] {i}/{total} · decoded={decoded} merged={merged} failed={failed}", flush=True)
    con.commit()
    return {"total": total, "decoded": decoded, "merged": merged, "failed": failed}
