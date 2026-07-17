#!/usr/bin/env python3
"""Stage 1 (Discover) — find candidate conflict-news URLs from curated outlets.

Channels (per project policy: named sites + RSS only):
  - Each outlet's own RSS feeds (probed for liveness).
  - Each outlet's on-site search, queried with the species×keyword Chinese terms.
  - Google News RSS: OFF by default; enable in config/sources.yaml only as a fallback.

Resumable & idempotent: candidate URLs are deduped into data/cache.sqlite
(`discovered` table). Feed liveness is logged (`source_liveness`) so recall gaps
are auditable. Run weekly with --weekly to restrict to recent items.

Examples:
  ./10_discover.py --seed-liveness         # just probe which feeds/searches work
  ./10_discover.py --weekly                # incremental: last N days (config)
  ./10_discover.py --full                  # ignore the recency window
  ./10_discover.py --sources chinanews,ltn # limit to specific outlets
  ./10_discover.py --no-search             # RSS only (skip on-site search)
"""
import argparse, sys, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from tools import cache, discover
from tools.config import all_sources, search_terms, build_queries


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--weekly", action="store_true", help="restrict to the recent window (config weekly_lookback_days)")
    ap.add_argument("--full", action="store_true", help="ignore the recency window (backfill)")
    ap.add_argument("--seed-liveness", action="store_true", help="only probe feed/search liveness, don't harvest")
    ap.add_argument("--sources", help="comma-separated source keys to limit to")
    ap.add_argument("--no-search", action="store_true", help="skip on-site search (RSS feeds only)")
    ap.add_argument("--no-rss", action="store_true", help="skip RSS (on-site search only)")
    args = ap.parse_args()

    st = search_terms()
    lookback = st.get("weekly_lookback_days") if args.weekly and not args.full else None
    queries = build_queries()
    srcs = all_sources()
    if args.sources:
        want = set(args.sources.split(","))
        srcs = [s for s in srcs if s["key"] in want]

    con = cache.connect()
    totals = {"rss": 0, "search": 0, "google_news": 0}
    for s in srcs:
        r = sr = 0
        if not args.no_rss:
            r = discover.discover_rss(con, s, lookback)
        if not args.seed_liveness and not args.no_search:
            sr = discover.discover_search(con, s, queries, s.get("max_candidates_per_source", 60))
        totals["rss"] += r; totals["search"] += sr
        print(f"[discover] {s['key']:<12} rss={r:<4} search={sr:<4}", flush=True)

    if not args.seed_liveness:
        totals["google_news"] = discover.discover_google_news(con, queries, 20)

    n_disc = con.execute("SELECT COUNT(*) FROM discovered").fetchone()[0]
    print(f"\n[discover] candidates this run: rss={totals['rss']} search={totals['search']} "
          f"google_news={totals['google_news']}")
    print(f"[discover] total candidates in store: {n_disc}")

    # liveness summary
    print("\n[liveness] most recent probe per source/feed:")
    rows = con.execute("""
        SELECT source_key, kind, ok, n_items, note FROM source_liveness
        WHERE checked_at > (SELECT MAX(checked_at) FROM source_liveness) - 3600
        ORDER BY source_key""").fetchall()
    for r in rows:
        flag = "OK " if r["ok"] else "-- "
        note = f"  ({r['note']})" if r["note"] else ""
        print(f"  {flag}{r['source_key']:<12} {r['kind']:<7} items={r['n_items']}{note}")


if __name__ == "__main__":
    main()
