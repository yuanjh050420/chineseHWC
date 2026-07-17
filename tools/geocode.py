"""Geocode Chinese admin place text -> (lon, lat, uncertainty), following the
project's `geocode-news` skill (point-radius method; Chapman & Wieczorek 2020).

Method rules this implements:
  * COORDINATES COME FROM A GAZETTEER, never an estimated/fuzzed source.
  * EVERY resolved point carries a positive coordinateUncertaintyInMeters,
    derived from the gazetteer bounding box (preferred) or a feature-type default.
  * Failures return an explicit unresolved result, never a fabricated point.

The extractor has already done the skill's stages 1-2 (recognize + resolve) by
emitting clean Province/County/District admin fields; this module does stages 3-5
(gazetteer lookup + uncertainty + provenance) on those fields.

Backends, in preference order:
  - Nominatim/OSM (default): true WGS-84, returns a bounding box -> real radius.
    Public server limit 1 req/s. Weekly volume is small, so this is fine.
  - Amap/高德 (AMAP_KEY, opt-in fallback): DEPRECATED for precision. Amap returns
    GCJ-02 coordinates the Chinese authorities offset ("fuzz"); we convert the
    datum but the residual imprecision is real, so Amap points get an inflated
    uncertainty and a remark. Use only when Nominatim can't resolve a place.
"""
from __future__ import annotations
import os, time, math
import requests

_NOMINATIM = "https://nominatim.openstreetmap.org/search"
_AMAP = "https://restapi.amap.com/v3/geocode/geo"

_EARTH_R = 6_371_008.8

# Feature-type default radii (m) — fallback only; a real bbox always wins.
# County/township tier per the skill's uncertainty table.
_DEFAULT_RADIUS = {"district": 2_000, "county": 50_000, "province": 200_000}
_AMAP_EXTRA_UNCERTAINTY = 5_000  # residual GCJ-02 fuzz penalty added to Amap points


def _haversine(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1); dl = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return 2*_EARTH_R*math.asin(min(1.0, math.sqrt(a)))


def _radius_from_bbox(lat, lon, south, north, west, east):
    corners = [(south, west), (south, east), (north, west), (north, east)]
    return max(_haversine(lat, lon, la, lo) for la, lo in corners)

# --- GCJ-02 <-> WGS-84 conversion (standard China offset algorithm) ---
_A = 6378245.0
_EE = 0.00669342162296594323

def _out_of_china(lng, lat):
    return not (73.66 < lng < 135.05 and 3.86 < lat < 53.55)

def _transform_lat(x, y):
    ret = -100.0 + 2.0*x + 3.0*y + 0.2*y*y + 0.1*x*y + 0.2*math.sqrt(abs(x))
    ret += (20.0*math.sin(6.0*x*math.pi) + 20.0*math.sin(2.0*x*math.pi)) * 2.0/3.0
    ret += (20.0*math.sin(y*math.pi) + 40.0*math.sin(y/3.0*math.pi)) * 2.0/3.0
    ret += (160.0*math.sin(y/12.0*math.pi) + 320*math.sin(y*math.pi/30.0)) * 2.0/3.0
    return ret

def _transform_lng(x, y):
    ret = 300.0 + x + 2.0*y + 0.1*x*x + 0.1*x*y + 0.1*math.sqrt(abs(x))
    ret += (20.0*math.sin(6.0*x*math.pi) + 20.0*math.sin(2.0*x*math.pi)) * 2.0/3.0
    ret += (20.0*math.sin(x*math.pi) + 40.0*math.sin(x/3.0*math.pi)) * 2.0/3.0
    ret += (150.0*math.sin(x/12.0*math.pi) + 300.0*math.sin(x/30.0*math.pi)) * 2.0/3.0
    return ret

def gcj02_to_wgs84(lng, lat):
    if _out_of_china(lng, lat):
        return lng, lat
    dlat = _transform_lat(lng - 105.0, lat - 35.0)
    dlng = _transform_lng(lng - 105.0, lat - 35.0)
    radlat = lat / 180.0 * math.pi
    magic = math.sin(radlat)
    magic = 1 - _EE * magic * magic
    sqrtmagic = math.sqrt(magic)
    dlat = (dlat * 180.0) / ((_A * (1 - _EE)) / (magic * sqrtmagic) * math.pi)
    dlng = (dlng * 180.0) / (_A / sqrtmagic * math.cos(radlat) * math.pi)
    return lng - dlng, lat - dlat


def geocode_nominatim(query: str, email: str = "", tier: str = "county") -> dict | None:
    """Return {lon, lat, uncertainty_m, source, remarks} or None. Uncertainty
    from the returned bounding box (preferred) else the feature-type default."""
    try:
        headers = {"User-Agent": f"chineseHWC-monitor/1.0 ({email})" if email else "chineseHWC-monitor/1.0"}
        r = requests.get(_NOMINATIM, params={"q": query, "format": "json", "limit": 1,
                                             "countrycodes": "cn,tw", "addressdetails": 0},
                         headers=headers, timeout=20)
        arr = r.json()
        if not arr:
            return None
        hit = arr[0]
        lon, lat = float(hit["lon"]), float(hit["lat"])
        bb = hit.get("boundingbox")
        if bb and len(bb) == 4:
            south, north, west, east = float(bb[0]), float(bb[1]), float(bb[2]), float(bb[3])
            unc = _radius_from_bbox(lat, lon, south, north, west, east)
            remarks = "radius from OSM bounding box"
        else:
            unc = _DEFAULT_RADIUS.get(tier, 50_000)
            remarks = f"radius from {tier} feature-type default (no bbox)"
        return {"lon": lon, "lat": lat, "uncertainty_m": max(unc, 100.0),
                "source": "nominatim/OSM", "remarks": remarks}
    except Exception:
        return None


def geocode_amap(query: str, key: str, tier: str = "county") -> dict | None:
    """Opt-in fallback. Amap fuzzes coords (GCJ-02) and returns no bbox, so we
    convert the datum and inflate uncertainty by a fixed penalty + type default."""
    try:
        r = requests.get(_AMAP, params={"address": query, "key": key, "output": "json"}, timeout=15)
        d = r.json()
        if d.get("status") == "1" and d.get("geocodes"):
            lng, lat = map(float, d["geocodes"][0]["location"].split(","))
            lng, lat = gcj02_to_wgs84(lng, lat)
            unc = _DEFAULT_RADIUS.get(tier, 50_000) + _AMAP_EXTRA_UNCERTAINTY
            return {"lon": lng, "lat": lat, "uncertainty_m": unc, "source": "amap/高德",
                    "remarks": "GCJ-02 converted to WGS-84; coords authority-fuzzed, uncertainty inflated"}
    except Exception:
        return None
    return None


def geocode(province, county, district, amap_key=None, email="", prefer_amap=False) -> dict:
    """Resolve an admin place to a point-radius georeference.
    Tries most-specific place first, backing off district -> county -> province.
    Returns a dict: {lon, lat, uncertainty_m, resolved, verbatim, matched, source, remarks}.
    Never fabricates: unresolved -> {resolved: False}."""
    amap_key = amap_key or os.environ.get("AMAP_KEY")
    email = email or os.environ.get("GEOCODE_CONTACT_EMAIL", "")
    tiers = [("district", district), ("county", county), ("province", province)]
    present = [(t, v) for t, v in tiers if v and str(v).strip() and str(v) != "nan"]
    verbatim = "".join(str(v) for _, v in present)
    # build cumulative queries from most specific (all parts) to least
    for i in range(len(present)):
        parts = present[i:]                       # drop the most-specific failing tier
        query = "".join(str(v) for _, v in parts)
        tier = parts[0][0]
        res = None
        use_amap_first = prefer_amap and amap_key
        if use_amap_first:
            res = geocode_amap(query, amap_key, tier)
        if res is None:
            res = geocode_nominatim(query, email, tier)
            time.sleep(1.1)                        # Nominatim <=1 req/s
        if res is None and amap_key and not use_amap_first:
            res = geocode_amap(query, amap_key, tier)
        if res:
            res.update({"resolved": True, "verbatim": verbatim, "matched": query})
            return res
    return {"resolved": False, "lon": None, "lat": None, "uncertainty_m": None,
            "verbatim": verbatim, "matched": None, "source": None,
            "remarks": "unresolved: no gazetteer hit at any admin tier"}
