"""Score extractor output against the coded ground truth, field by field.

Field-level matching rules (lenient where the manuscript's coding is itself fuzzy):
  - species, conflict_type: exact string match (canonical vocab).
  - year: exact. month: exact.
  - province/county: match if either contains the other after stripping
    admin suffixes (省/市/县/区/自治州...). District is free text -> not scored hard.
  - victim: normalized token-set match (Sheep == 羊 etc. handled by English coding).
  - number_of_victims / number_of_deaths: exact integer, treating NaN==None==blank.
Include/exclude is scored separately (all ground-truth rows are TRUE incidents,
so recall on include=true is the measurable quantity here).
"""
from __future__ import annotations
import re, math
import pandas as pd

_ADMIN = re.compile(r"(省|市|自治区|自治州|自治县|地区|盟|县|区|旗|州)$")

def _norm_place(s):
    if not s or (isinstance(s, float) and math.isnan(s)): return ""
    s = str(s).strip()
    return _ADMIN.sub("", s)

def _place_match(gt, pred):
    g, p = _norm_place(gt), _norm_place(pred)
    if not g and not p: return True
    if not g or not p: return False
    return g in p or p in g or g == p

def _int_or_none(v):
    """Parse a count that may be free text in the ground truth:
    '1'->1, '30+'->30, '3+1'->4 (compound events summed), '未知'/''/nan->None."""
    if v is None: return None
    if isinstance(v, float) and math.isnan(v): return None
    if isinstance(v, (int,)): return v
    s = str(v).strip()
    if not s or s in ("未知", "不详", "nan", "None"): return None
    # compound like '3+1' or '0+10' -> sum the integer parts
    parts = re.findall(r"\d+", s)
    if not parts: return None
    if "+" in s and len(parts) > 1:
        return sum(int(x) for x in parts)
    return int(parts[0])   # leading integer of '30+', '15', etc.

def _num_match(gt, pred):
    g, p = _int_or_none(gt), _int_or_none(pred)
    # If ground truth didn't record a count, don't penalize the model either way.
    if g is None: return True
    return g == p

def _str_match(gt, pred):
    g = (str(gt).strip() if gt is not None and not (isinstance(gt,float) and math.isnan(gt)) else "")
    p = (str(pred).strip() if pred is not None else "")
    return g == p

def _victim_match(gt, pred):
    def toks(x):
        if not x or (isinstance(x,float) and math.isnan(x)): return set()
        return set(re.split(r"[+/、,\s]+", str(x).strip().lower())) - {""}
    g, p = toks(gt), toks(pred)
    if not g and not p: return True
    if not g or not p: return False
    return bool(g & p)  # any overlap (compound victims)

def score_row(gt: dict, pred: dict) -> dict:
    return {
        "species":      _str_match(gt.get("Species"), pred.get("species")),
        "conflict_type":_str_match(gt.get("Type of conflict (standard)"), pred.get("conflict_type")),
        "year":         _num_match(gt.get("Year"), pred.get("year")),
        "month":        _num_match(gt.get("Month"), pred.get("month")),
        "province":     _place_match(gt.get("Province"), pred.get("province")),
        "county":       _place_match(gt.get("County"), pred.get("county")),
        "victim":       _victim_match(gt.get("Victem"), pred.get("victim")),
        "n_victims":    _num_match(gt.get("Number of victems"), pred.get("number_of_victims")),
        "n_deaths":     _num_match(gt.get("Number of deaths"), pred.get("number_of_deaths")),
        "included":     bool(pred.get("include")),
    }

def summarize(scored: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(scored)
    acc = (df.mean(numeric_only=True) * 100).round(1)
    return acc.rename("accuracy_%").to_frame()
