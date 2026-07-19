#!/usr/bin/env python3
"""Build a self-contained static HTML dashboard from the master incident store.

Output: docs/index.html — a single file with ALL incident data inlined as JSON
and Leaflet/Chart.js loaded from CDN. No server, no build step, no external data
file. This is what GitHub Pages serves and what the WordPress page embeds via
<iframe>. Designed to be dropped into rolandkays.com unchanged.

Panels:
  - Interactive Leaflet map of incidents (colored by species; popups with detail;
    new monitored points optionally show their uncertainty radius).
  - Yearly trend (stacked by conflict type).
  - Species composition and conflict-type composition bar charts.
  - Headline stat cards + a "last updated" stamp and historical-vs-new counts.
  - Client-side filters (species, conflict type, year range) that drive all panels.

Examples:
  ./build_dashboard.py                       # -> docs/index.html
  ./build_dashboard.py --out docs/index.html
  ./build_dashboard.py --title "China Human–Carnivore Conflict Monitor"
"""
import argparse, sys, json, datetime as dt
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import pandas as pd
from tools import store
from tools.config import schema, conflict_types

SPECIES_COLORS = {
    "Asiatic Black Bear": "#1f77b4", "Brown Bear": "#8c564b", "Grey Wolf": "#7f7f7f",
    "Tiger": "#ff7f0e", "Leopard": "#e377c2", "Snow Leopard": "#17becf",
    "Eurasian Lynx": "#bcbd22", "Asiatic Golden Cat": "#d62728", "Clouded Leopard": "#9467bd",
    "Dhole": "#2ca02c", "Sun Bear": "#000000", "Golden Jackal": "#aec7e8", "Wolverine": "#c49c94",
}

def _clean(df):
    df = df.copy()
    for c in ["Year", "Month", "Longitude", "Latitude"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df["unc"] = pd.to_numeric(df["coordinateUncertaintyInMeters"], errors="coerce")
    return df

def _incident_date(r):
    """Best ISO date for an incident: Year+Month (day=1), else discovered_date, else None."""
    yr, mo = r.get("Year"), r.get("Month")
    if not pd.isna(yr):
        y = int(yr); m = int(mo) if not pd.isna(mo) else 1
        m = min(max(m, 1), 12)
        return f"{y:04d}-{m:02d}-01"
    d = str(r.get("discovered_date") or "").strip()
    return d[:10] if len(d) >= 7 else None

def _s(v):
    return "" if (v is None or (isinstance(v, float) and pd.isna(v)) or pd.isna(v)) else str(v)

def build_records(df):
    """MONITOR-ONLY records (source=='monitor'). Historical 520 seed rows are excluded
    by design — this dashboard is a live monitor, not the paper's archive."""
    recs = []
    for _, r in df.iterrows():
        if r.get("source") != "monitor":
            continue
        if pd.isna(r["Longitude"]) or pd.isna(r["Latitude"]):
            continue
        recs.append({
            "id": _s(r.get("No.")),
            "sp": r["Species"], "yr": None if pd.isna(r["Year"]) else int(r["Year"]),
            "mo": None if pd.isna(r["Month"]) else int(r["Month"]),
            "date": _incident_date(r),
            "disc": _s(r.get("discovered_date"))[:10],
            "prov": _s(r.get("Province")), "cty": _s(r.get("County")), "dist": _s(r.get("District")),
            "type": r["Type of conflict (standard)"],
            "vic": _s(r.get("Victem")),
            "nv": _s(r.get("Number of victems")), "nd": _s(r.get("Number of deaths")),
            "lon": round(float(r["Longitude"]), 4), "lat": round(float(r["Latitude"]), 4),
            "unc": None if pd.isna(r["unc"]) else int(r["unc"]),
            "url": _s(r.get("URL")),
            "title": _s(r.get("title")),
            "sum_en": _s(r.get("summary_en")), "sum_zh": _s(r.get("summary_zh")),
            "img": _s(r.get("image_url")),
            "review": int(r.get("needs_review") or 0),
        })
    # newest incident first
    recs.sort(key=lambda x: (x["date"] or "0000"), reverse=True)
    return recs

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default="docs/index.html")
    ap.add_argument("--title", default="China Human–Large-Carnivore Conflict Monitor")
    ap.add_argument("--recent-weeks", type=int, default=8,
                    help="default timeline window (weeks back from today); user can widen it in the UI")
    args = ap.parse_args()

    df = _clean(store.load())
    recs = build_records(df)
    payload = {
        "records": recs,
        "species_colors": SPECIES_COLORS,
        "conflict_types": conflict_types(),
        "generated": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "today": dt.date.today().isoformat(),
        "recent_weeks": args.recent_weeks,
        "n_total": len(recs),
        "title": args.title,
    }
    html = (HTML_TEMPLATE
            .replace("__TITLE__", args.title)
            .replace("__PAYLOAD__", json.dumps(payload, ensure_ascii=False)))
    out = Path(args.out); out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    print(f"[dashboard] wrote {out} ({out.stat().st_size//1024} KB) — {len(recs)} monitored incidents "
          f"(historical seed excluded), default window {args.recent_weeks} weeks")

# The template is kept in a separate module to keep this file readable.
from tools.dashboard_template import HTML_TEMPLATE

if __name__ == "__main__":
    main()
