#!/usr/bin/env python3
"""Stage 4 (Geocode) — assign WGS-84 lon/lat + uncertainty to extracted incidents.

Follows the `geocode-news` skill: coordinates come from a GAZETTEER (Nominatim/OSM
by default), every point gets a coordinateUncertaintyInMeters from the bounding
box, and unresolved places return no point rather than a guess.

IMPORTANT: the 520 historical rows keep their MANUAL Google-Maps coordinates and
are NOT re-geocoded here (manual township coords are more precise than automated
county-centroid lookup). This stage only geocodes NEW extracted incidents.

Amap/高德 is available as an opt-in fallback (--prefer-amap) but is deprecated for
precision: it returns authority-fuzzed GCJ-02 coords, so its points get inflated
uncertainty. Nominatim is the default.

Place lookups are cached by (province|county|district) so repeated places cost one
request. Nominatim public policy: <=1 req/s (handled in tools/geocode).

Examples:
  ./40_geocode.py                 # geocode all un-geocoded extracted incidents
  ./40_geocode.py --prefer-amap   # use Amap first (needs AMAP_KEY); coarser
"""
import argparse, sys, os, json, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from tools import cache, geocode as geo

def _load_dotenv():
    p = Path(__file__).resolve().parent / ".env"
    if p.exists():
        for line in p.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1); os.environ.setdefault(k.strip(), v.strip())

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--prefer-amap", action="store_true", help="try Amap before Nominatim (coarser; needs AMAP_KEY)")
    ap.add_argument("--force", action="store_true", help="re-geocode places already cached")
    args = ap.parse_args()
    _load_dotenv()

    con = cache.connect()
    # pull included, not-yet-geocoded extracted rows
    rows = con.execute("SELECT url, row_json FROM extracted WHERE include=1").fetchall()
    incidents = []
    for r in rows:
        try: d = json.loads(r["row_json"])
        except Exception: continue
        if d: incidents.append(d)
    print(f"[geocode] included incidents: {len(incidents)}", flush=True)

    def cache_get(key):
        return con.execute("SELECT * FROM geocoded WHERE place_key=?", (key,)).fetchone()

    resolved = unresolved = cached = 0
    for d in incidents:
        prov, cty, dist = d.get("Province"), d.get("County"), d.get("District")
        key = f"{prov}|{cty}|{dist}"
        hit = None if args.force else cache_get(key)
        if hit is None:
            res = geo.geocode(prov, cty, dist, prefer_amap=args.prefer_amap)
            con.execute("""INSERT OR REPLACE INTO geocoded
                (place_key,lon,lat,uncertainty_m,resolved,source,matched,remarks,geocoded_at)
                VALUES(?,?,?,?,?,?,?,?,?)""",
                (key, res["lon"], res["lat"], res["uncertainty_m"], int(res["resolved"]),
                 res["source"], res["matched"], res["remarks"], time.time()))
            con.commit()
            hit = cache_get(key)
        else:
            cached += 1
        if hit["resolved"]:
            resolved += 1
        else:
            unresolved += 1
    print(f"[geocode] resolved={resolved} unresolved={unresolved} (cache hits={cached})")
    print("[geocode] coordinates written to the geocoded cache; the store stage joins them onto incident rows.")

if __name__ == "__main__":
    main()
