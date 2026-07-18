"""LLM extractor: Chinese news article -> coded human–large-carnivore conflict
incident, matching the manuscript's schema and inclusion criteria.

Two backends, one prompt:
  - production/GitHub: the `anthropic` SDK with ANTHROPIC_API_KEY.
  - in-session benchmarking: `host.llm` (pass call_llm=host_llm_adapter).
Both return the same JSON contract, so the benchmark measures the real prompt.
"""
from __future__ import annotations
import json, os, re
from .config import schema, conflict_types, species_list

# ---- The extraction contract (schema-constrained JSON) ----
_FIELDS = {
    "include": "true if this article reports a REAL human–large-carnivore conflict incident meeting all 3 criteria; false otherwise",
    "exclude_reason": "if include=false, one short phrase why (e.g. 'zoo animal', 'sighting in wilderness', 'not a large carnivore', 'no location', 'roadkill')",
    "species": "canonical English species name from the allowed list, or null",
    "year": "4-digit year of the incident (not the article publication year if they differ), or null",
    "month": "month 1-12, or null",
    "province": "Chinese province text (e.g. 四川省), or null",
    "county": "Chinese county/city text (e.g. 宝兴县), or null",
    "district": "most specific Chinese place named — township/village/site (>= township), or null",
    "conflict_type": "exactly one of the allowed conflict types, or null",
    "victim": "victim type in English (Human, Sheep, Cow, Goat, Yak, Horse, Camel, Pig, Dog, Chicken, Duck, Goose, ...); compound like 'Goose+Duck' allowed; null if none",
    "number_of_victims": "integer count of animals/people affected, or null",
    "number_of_deaths": "integer count of deaths, or null",
    "confidence": "your 0-1 confidence in this extraction",
}

def _allowed_species() -> list[str]:
    return [s["english"] for s in species_list()]

def build_system() -> str:
    sp = _allowed_species()
    cts = conflict_types()
    return f"""You are a wildlife-conflict data coder. You read a Chinese (or Taiwanese) news
article and extract ONE human–large-carnivore conflict incident into structured fields,
following a published coding protocol EXACTLY.

ALLOWED SPECIES (use the exact English name, else null):
{json.dumps(sp, ensure_ascii=False)}

ALLOWED CONFLICT TYPES (choose exactly one):
{json.dumps(cts, ensure_ascii=False)}
Guidance on conflict_type:
- "Attack livestock": predation/killing/injury of farmed animals (sheep, cattle, yak, horse, pig, poultry).
- "Attack domestic dog": specifically a pet/guard dog attacked.
- "Enter human settlements": animal entered village/town/residential/farmland area (no attack, or entry is the story).
- "Attack human": a person was injured or killed.
- "Damage property": structures/beehives/crops/vehicles damaged (use the specific ones below when apt).
- "Damage beehive": beehives raided (mainly Asiatic black bear).
- "Damage crops": crops/orchards damaged.
Pick the single PRIMARY conflict of the incident.

THREE INCLUSION CRITERIA (all must hold for include=true):
1. Professional media report with accurate time (>= month) AND accurate location (>= township).
2. Reflects a NEGATIVE impact of a WILD carnivore on people/property. EXCLUDE zoo/captive
   animals, roadkill, mere sightings with no impact, and misidentified non-carnivores.
3. For events without direct damage (e.g. sightings), the animal must be in a human-dominated
   landscape (village, farmland, road, residential) — NOT remote wilderness or PA core zones.

DATE OF THE INCIDENT (critical — this is often wrong):
- Extract the year/month the CONFLICT HAPPENED, not the article's publication date and
  not any other year mentioned (a past case referenced for context, a policy year, a
  republished-article date).
- A PUBLICATION DATE is provided above the article. Chinese articles usually report
  the incident as having happened shortly before publication ("近日"/"日前"/"上月"). If the
  body gives no explicit incident date, USE THE PUBLICATION DATE's year and month.
- If the body gives an explicit incident date, prefer it; but if it conflicts wildly with
  the publication date (e.g. body says a year AFTER publication, or a decade earlier that
  is clearly a cited past case), trust the publication date for THIS incident.
- Never output a year later than the publication year, or a year > current year.

CONSERVATIVE COUNTING (apply precisely — do NOT inflate):
- "two or three" -> 2 ; "more than ten"/"十几"/"十余" -> 11 ; casualties reported with no
  number -> 1.
- number_of_deaths = individuals that DIED in THIS incident. number_of_victims = total
  individuals affected (killed + injured) in THIS incident.
- Count ONLY animals/people harmed in the single reported incident. Do NOT sum unrelated
  figures, cumulative annual totals, historical tallies, or compensation statistics that
  appear elsewhere in the article. If the article gives a clear incident count (e.g. "咬死
  15只羊"), use exactly that number, not a larger aggregate mentioned for background.

Return ONLY a JSON object with these keys:
{json.dumps(_FIELDS, ensure_ascii=False, indent=1)}

OUTPUT RULES (strict):
- Output the JSON object and NOTHING else. No explanation, no reasoning, no markdown
  fences, no text before or after. Your entire reply must be parseable as JSON.
- If the article is unreadable/mojibake, still return the JSON with include=false and
  exclude_reason="unreadable_or_encoding". Never reply in prose.
- Put any brief justification inside exclude_reason, not outside the JSON."""

def build_user(article_text: str, hint_species: str | None = None, title: str | None = None,
               pub_date: str | None = None) -> str:
    hint = f"\n(Discovery search suggested this may involve: {hint_species}. Verify against the text; correct if wrong.)" if hint_species else ""
    t = f"TITLE: {title}\n" if title else ""
    # Publication date is critical for the year/month fields — it is frequently the
    # ONLY date signal (the incident date is often just "近日"/"日前" in the body).
    p = f"PUBLICATION DATE: {pub_date}\n" if pub_date else ""
    body = article_text[:6000]
    return f"{t}{p}\nARTICLE:\n{body}{hint}"

_JSON_RE = re.compile(r"\{.*\}", re.S)

def parse_response(text: str) -> dict:
    m = _JSON_RE.search(text or "")
    if not m:
        # No JSON found — usually the model declined to code an unreadable/mojibake
        # article. Treat as an exclude that needs human review, not a silent drop.
        low = (text or "").lower()
        reason = "unreadable_or_encoding" if any(k in low for k in
                 ("encod", "decode", "unreadable", "garbled", "corrupt")) else "no_json_output"
        return {"include": False, "exclude_reason": reason, "confidence": 0, "needs_review": True}
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        # tolerate trailing commas / single quotes
        s = m.group(0).replace("'", '"')
        s = re.sub(r",\s*}", "}", s); s = re.sub(r",\s*]", "]", s)
        try:
            return json.loads(s)
        except Exception:
            return {"include": False, "exclude_reason": "json decode failed", "confidence": 0}


def to_row(parsed: dict, url: str, model: str, discovered_date: str = "", title: str = "") -> dict:
    """Map parsed extraction -> master-schema row dict (14 cols + provenance)."""
    def i(v):
        try: return int(v)
        except Exception: return None
    return {
        "Species": parsed.get("species"),
        "No.": None,  # assigned at store time
        "Year": i(parsed.get("year")),
        "Month": i(parsed.get("month")),
        "Province": parsed.get("province"),
        "County": parsed.get("county"),
        "District": parsed.get("district"),
        "Longitude": None, "Latitude": None,  # geocode stage fills these
        "Type of conflict (standard)": parsed.get("conflict_type"),
        "Victem": parsed.get("victim"),
        "Number of victems": i(parsed.get("number_of_victims")),
        "Number of deaths": i(parsed.get("number_of_deaths")),
        "URL": url,
        "source": "monitor",
        "discovered_date": discovered_date,
        "extract_model": model,
        "extract_confidence": parsed.get("confidence"),
        "title": title or parsed.get("title") or "",
    }


# ---- backends ----
def extract_with_anthropic(article_text, model=None, hint_species=None, title=None, client=None):
    import anthropic
    model = model or os.environ.get("HWC_EXTRACT_MODEL", "claude-haiku-4-5")
    client = client or anthropic.Anthropic()
    msg = client.messages.create(
        model=model, max_tokens=700, system=build_system(),
        messages=[{"role": "user", "content": build_user(article_text, hint_species, title)}],
    )
    return parse_response(msg.content[0].text), model


def extract_with_callable(article_text, call_llm, model="host.llm", hint_species=None, title=None):
    """call_llm(system, user) -> str. Used for in-session benchmarking via host.llm."""
    out = call_llm(build_system(), build_user(article_text, hint_species, title))
    return parse_response(out), model
