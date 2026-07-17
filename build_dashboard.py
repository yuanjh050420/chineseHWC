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
    df["Year"] = pd.to_numeric(df["Year"], errors="coerce")
    df["Month"] = pd.to_numeric(df["Month"], errors="coerce")
    df["Longitude"] = pd.to_numeric(df["Longitude"], errors="coerce")
    df["Latitude"] = pd.to_numeric(df["Latitude"], errors="coerce")
    df["unc"] = pd.to_numeric(df["coordinateUncertaintyInMeters"], errors="coerce")
    return df

def build_records(df):
    recs = []
    for _, r in df.iterrows():
        if pd.isna(r["Longitude"]) or pd.isna(r["Latitude"]):
            continue
        recs.append({
            "id": r.get("No.") or "",
            "sp": r["Species"], "yr": None if pd.isna(r["Year"]) else int(r["Year"]),
            "mo": None if pd.isna(r["Month"]) else int(r["Month"]),
            "prov": (r.get("Province") or ""), "cty": (r.get("County") or ""),
            "type": r["Type of conflict (standard)"],
            "vic": (r.get("Victem") if not pd.isna(r.get("Victem")) else ""),
            "lon": round(float(r["Longitude"]), 4), "lat": round(float(r["Latitude"]), 4),
            "unc": None if pd.isna(r["unc"]) else int(r["unc"]),
            "src": ("new" if r.get("source") == "monitor" else "hist"),
            "url": (r.get("URL") or ""),
            "title": (r.get("title") if not pd.isna(r.get("title")) else ""),
        })
    return recs

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default="docs/index.html")
    ap.add_argument("--title", default="China Human–Large-Carnivore Conflict Monitor")
    args = ap.parse_args()

    df = _clean(store.load())
    recs = build_records(df)
    n_hist = sum(1 for r in recs if r["src"] == "hist")
    n_new = sum(1 for r in recs if r["src"] == "new")
    payload = {
        "records": recs,
        "species_colors": SPECIES_COLORS,
        "conflict_types": conflict_types(),
        "generated": dt.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
        "n_total": len(recs), "n_hist": n_hist, "n_new": n_new,
        "title": args.title,
    }
    html = (HTML_TEMPLATE
            .replace("__TITLE__", args.title)
            .replace("__PAYLOAD__", json.dumps(payload, ensure_ascii=False)))
    out = Path(args.out); out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    print(f"[dashboard] wrote {out} ({out.stat().st_size//1024} KB) — {len(recs)} incidents, "
          f"{n_hist} historical + {n_new} new")

# The template is kept in a separate module to keep this file readable.
from tools.dashboard_template import HTML_TEMPLATE

if __name__ == "__main__":
    main()
