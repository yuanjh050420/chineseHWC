#!/usr/bin/env python3
"""Re-fetch article text for the ground-truth benchmark sample and cache it.
Resumable: re-running only fetches URLs not already cached ok/dead."""
import sys, json, time, threading
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import pandas as pd
import trafilatura
from tools import http, cache

ROOT = Path(__file__).resolve().parent.parent
sample = pd.read_parquet(ROOT / "benchmark" / "gt_sample.parquet")
con = cache.connect()

# One writer connection guarded by a lock (sqlite + threads).
_wlock = threading.Lock()

def already_done(url):
    r = con.execute("SELECT status FROM fetched WHERE url=?", (url,)).fetchone()
    return r and r[0] in ("ok", "dead")

def work(url):
    try:
        resp = http.fetch(url)
        if resp.status_code >= 400:
            return url, ("dead", resp.status_code, None, None, None, f"http {resp.status_code}")
        # Pass the charset-corrected unicode text (http.fetch fixed resp.encoding).
        # Trafilatura decodes robustly; feeding it the corrected .text avoids the
        # Latin-1 mojibake that older GB2312/GBK CN pages otherwise produce.
        html = resp.text
        text = trafilatura.extract(html, include_comments=False, favor_recall=True)
        md = trafilatura.extract_metadata(html)
        title = md.title if md else None
        if text and len(text) > 80:
            return url, ("ok", resp.status_code, resp.url, text, title, None)
        return url, ("dead", resp.status_code, resp.url, None, None, "no extractable text")
    except http.Blocked as e:
        return url, ("blocked", None, None, None, None, str(e)[:200])
    except Exception as e:
        return url, ("error", None, None, None, None, str(e)[:200])

todo = [u for u in sample["URL"].tolist() if not already_done(u)]
cached = len(sample) - len(todo)
stats = {"ok": 0, "dead": 0, "blocked": 0, "error": 0, "cached": cached}
print(f"to fetch: {len(todo)} (cached: {cached})", flush=True)

# 12 workers across ~10 hosts; per-host limiter keeps each host polite.
with ThreadPoolExecutor(max_workers=12) as ex:
    futs = {ex.submit(work, u): u for u in todo}
    done = 0
    for fut in as_completed(futs):
        url, (status, code, final, text, title, err) = fut.result()
        with _wlock:
            cache.save_fetched(con, url, status, http_code=code, final_url=final,
                               text=text, title=title, error=err)
        stats[status] += 1
        done += 1
        if done % 20 == 0:
            print(f"[{done}/{len(todo)}] {stats}", flush=True)

print("FINAL", json.dumps(stats))
# summary of what we can benchmark on
ok = con.execute("SELECT COUNT(*) FROM fetched WHERE status='ok'").fetchone()[0]
print(f"articles with usable text: {ok}")
