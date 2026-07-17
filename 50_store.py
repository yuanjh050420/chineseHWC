#!/usr/bin/env python3
"""Stage 5 (Store) — assemble extracted+geocoded incidents into master rows,
dedup, and append to the master store. Splits a human-review queue.

What it does, in order, for each INCLUDED extracted incident:
  1. Join geocoded lon/lat + uncertainty (from the geocoded cache) onto the row.
  2. YEAR/MONTH FALLBACK: if the extractor left year/month blank, fill them from
     the article's publication/discovery date. (Per the project decision: on
     weekly runs the discovery date bounds the incident date well, so this makes
     the historically-weak year field reliable going forward.)
  3. Assign a stable incident id (e.g. ABB188) per species prefix.
  4. Route rows flagged needs_review to data/master/review_queue.csv INSTEAD of the
     master store — nothing low-confidence enters the published data silently, and
     nothing is dropped (recall-favoring policy). You review, then --promote.
  5. Dedup (URL + fuzzy species/year/month/county) and append the rest to master.

Examples:
  ./50_store.py                 # process extracted -> master + review_queue
  ./50_store.py --promote       # move human-approved review_queue rows into master
  ./50_store.py --dry-run
"""
import argparse, sys, os, json, datetime as dt
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import pandas as pd
from tools import cache, store
from tools.config import columns

REVIEW_CSV = store.DATA / "master" / "review_queue.csv"

def _year_month_from_date(s):
    """Parse a pubdate/discovery string -> (year, month) or (None, None)."""
    if not s: return None, None
    import dateutil.parser as dp
    try:
        d = dp.parse(str(s), fuzzy=True, default=dt.datetime(1900,1,1))
        if d.year > 1900:
            return d.year, d.month
    except Exception:
        pass
    return None, None

def build_rows(con):
    """Return (master_rows_df, review_rows_df) assembled from the caches."""
    ex = con.execute("SELECT url, row_json, reason FROM extracted WHERE include=1").fetchall()
    # geocode lookup by place_key
    geo = {r["place_key"]: r for r in con.execute("SELECT * FROM geocoded").fetchall()}
    # discovery pubdate lookup
    fetched = {r["url"]: r["pub_date"] for r in con.execute("SELECT url, pub_date FROM fetched").fetchall()}
    disc = {r["url"]: r["pubdate"] for r in con.execute("SELECT url, pubdate FROM discovered").fetchall()}

    master_rows, review_rows = [], []
    existing = store.load()
    for r in ex:
        try: d = json.loads(r["row_json"])
        except Exception: continue
        if not d: continue
        # 1. geocode join
        key = f"{d.get('Province')}|{d.get('County')}|{d.get('District')}"
        g = geo.get(key)
        if g and g["resolved"]:
            d["Longitude"] = g["lon"]; d["Latitude"] = g["lat"]
            d["coordinateUncertaintyInMeters"] = g["uncertainty_m"]
            d["geocode_source"] = g["source"]; d["geocode_matched"] = g["matched"]
        else:
            d["geocode_source"] = "unresolved"; d["geocode_matched"] = ""
            d["coordinateUncertaintyInMeters"] = pd.NA
        # 2. year/month fallback from publication/discovery date
        pubdate = fetched.get(r["url"]) or disc.get(r["url"]) or ""
        d["discovered_date"] = (pubdate or "")[:10]
        if not d.get("Year") or not d.get("Month"):
            fy, fm = _year_month_from_date(pubdate)
            if not d.get("Year") and fy: d["Year"] = fy
            if not d.get("Month") and fm: d["Month"] = fm
        # normalize provenance defaults
        d.setdefault("source", "monitor")
        d.setdefault("needs_review", 0)
        needs_review = bool(d.pop("_needs_review", False)) or r["reason"] == "needs_review" \
                       or d.get("geocode_source") == "unresolved" or not d.get("Year")
        d["needs_review"] = int(needs_review)
        (review_rows if needs_review else master_rows).append(d)
    return pd.DataFrame(master_rows), pd.DataFrame(review_rows)

def _assign_ids(df, existing):
    if df.empty: return df
    df = df.copy()
    running = existing.copy()
    ids = []
    for _, r in df.iterrows():
        nid = store.next_id(r["Species"], running)
        ids.append(nid)
        running = pd.concat([running, pd.DataFrame([{"Species": r["Species"], "No.": nid}])], ignore_index=True)
    df["No."] = ids
    return df

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--promote", action="store_true", help="move approved review_queue.csv rows into master")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    con = cache.connect()

    if args.promote:
        if not REVIEW_CSV.exists():
            sys.exit("no review_queue.csv to promote")
        rev = pd.read_csv(REVIEW_CSV)
        # only promote rows a human marked keep=1 (add that column when reviewing)
        keep = rev[rev.get("keep", 1) == 1] if "keep" in rev.columns else rev
        keep = _assign_ids(keep, store.load())
        res = store.append(keep)
        print(f"[store] promoted {res['added']} reviewed rows -> master (dups: url={res['dup_url']} inc={res['dup_incident']})")
        REVIEW_CSV.unlink()
        return

    master_new, review_new = build_rows(con)
    print(f"[store] assembled: {len(master_new)} auto-accept, {len(review_new)} need review")
    if args.dry_run:
        print("[store] dry run — nothing written"); return

    if not master_new.empty:
        master_new = _assign_ids(master_new, store.load())
        for c in columns():
            if c not in master_new.columns: master_new[c] = pd.NA
        res = store.append(master_new[columns()])
        print(f"[store] added {res['added']} to master (dups: url={res['dup_url']} inc={res['dup_incident']}); total={res['total']}")
    if not review_new.empty:
        for c in columns():
            if c not in review_new.columns: review_new[c] = pd.NA
        mode = "a" if REVIEW_CSV.exists() else "w"
        review_new[columns()].to_csv(REVIEW_CSV, mode=mode, header=(mode=="w"), index=False)
        print(f"[store] wrote {len(review_new)} rows to review_queue.csv — review, set keep=1, then ./50_store.py --promote")

if __name__ == "__main__":
    main()
