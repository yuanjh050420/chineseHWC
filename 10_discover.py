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
    ap.add_argument("--search-max-queries", type=int, default=0, help="cap on-site search terms per source (0=config default)")
    ap.add_argument("--search-time-budget", type=float, default=0, help="wall-clock seconds per source for on-site search (0=config default)")
    ap.add_argument("--with-search", action="store_true", help="enable on-site search sweep (weekly runs are RSS-only unless set; search is bounded and best from a home IP)")
    ap.add_argument("--backfill", action="store_true",
                    help="RETROSPECTIVE build-up: full recency window + thorough on-site search "
                         "(all species×keyword queries, generous per-site time budget). On-site search "
                         "is the ONLY channel that reaches back in time; RSS carries only recent items. "
                         "Run once from a home IP to seed the last ~year. Slower than a weekly run.")
    ap.add_argument("--resolve-gnews", action="store_true",
                    help="decode any Google News redirect links already in the cache into real "
                         "publisher URLs, then exit (no crawling). Run this to repair a prior "
                         "--google-news-only run whose links weren't decoded.")
    ap.add_argument("--google-news-only", action="store_true",
                    help="query ONLY the Google News aggregator (skip all curated-outlet RSS + on-site "
                         "search). Use to chase RECENT items from outlets whose own search is blocked; "
                         "Google News is time-sortable so this targets the last year. Requires "
                         "google_news_rss.enabled: true in config/sources.yaml.")
    args = ap.parse_args()
    # Backfill: reach back as far as each outlet's search allows. Implies full window
    # + forced search sweep with the per-site caps lifted (weekly caps exist only to
    # keep the routine run fast; a one-time backfill should be thorough).
    if args.backfill:
        args.full = True
        args.with_search = True
    # Weekly runs default to RSS-only: RSS is the primary channel and reliable from
    # any IP, while on-site search is slow and low-yield from datacenter IPs. Enable
    # search explicitly with --with-search (recommended when running from a home IP).
    if args.weekly and not args.with_search:
        args.no_search = True

    st = search_terms()
    lookback = st.get("weekly_lookback_days") if args.weekly and not args.full else None
    queries = build_queries()
    srcs = all_sources()
    if args.google_news_only:
        srcs = []  # skip every curated outlet; only the Google News block below runs
    elif args.sources:
        want = set(args.sources.split(","))
        srcs = [s for s in srcs if s["key"] in want]

    con = cache.connect()

    # Repair mode: decode Google News redirect links already in the cache, then exit.
    if args.resolve_gnews:
        from tools import gnews
        stats = gnews.resolve_gnews(con)
        print(f"[resolve-gnews] {stats}")
        return

    totals = {"rss": 0, "search": 0, "google_news": 0}
    for s in srcs:
        r = sr = 0
        if not args.no_rss:
            r = discover.discover_rss(con, s, lookback)
        if not args.seed_liveness and not args.no_search:
            defs = discover._sources().get("defaults", {})
            if args.backfill:
                # thorough one-time sweep: all queries, generous budget, more candidates/site
                mq = args.search_max_queries or len(queries)
                tb = args.search_time_budget or defs.get("backfill_search_time_budget_s", 600)
                cap = defs.get("backfill_max_candidates_per_source", 300)
            else:
                mq = args.search_max_queries or defs.get("search_max_queries", 20)
                tb = args.search_time_budget or defs.get("search_time_budget_s", 120)
                cap = s.get("max_candidates_per_source", 60)
            sr = discover.discover_search(con, s, queries, cap, max_queries=mq, time_budget_s=tb)
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
