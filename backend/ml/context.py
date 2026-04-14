import json
import os
import sys

# Make backend/ importable so agents package is accessible from ml/
_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from agents.data_agent import resolve_business_codes as _agent_resolve_codes

# -------------------------------------------------------------------
# Hardcoded NAICS lookup (~30 common B2C business types)
# -------------------------------------------------------------------
NAICS_LOOKUP = {
    "bakery": "311811",
    "bread shop": "311811",
    "pastry shop": "311811",
    "restaurant": "722511",
    "fast food": "722513",
    "coffee shop": "722515",
    "cafe": "722515",
    "bar": "722410",
    "clothing store": "448140",
    "apparel store": "448140",
    "shoe store": "448210",
    "salon": "812112",
    "hair salon": "812112",
    "barbershop": "812111",
    "nail salon": "812113",
    "gym": "713940",
    "fitness center": "713940",
    "yoga studio": "713940",
    "florist": "453110",
    "flower shop": "453110",
    "grocery": "445110",
    "grocery store": "445110",
    "convenience store": "445131",
    "gift shop": "453220",
    "jewelry store": "448310",
    "bookstore": "451211",
    "pet store": "453910",
    "pharmacy": "446110",
    "hardware store": "444110",
    "furniture store": "442110",
}

# -------------------------------------------------------------------
# Hardcoded MSA lookup (~50 major US cities)
# -------------------------------------------------------------------
MSA_LOOKUP = {
    "new york": "35620",
    "los angeles": "31080",
    "chicago": "16980",
    "houston": "26420",
    "dallas": "19100",
    "plano": "19100",
    "austin": "12420",
    "seattle": "42660",
    "miami": "33100",
    "atlanta": "12060",
    "boston": "14460",
    "san francisco": "41860",
    "phoenix": "38060",
    "philadelphia": "37980",
    "san antonio": "41700",
    "san diego": "41740",
    "denver": "19740",
    "portland": "38900",
    "las vegas": "29820",
    "detroit": "19820",
    "minneapolis": "33460",
    "tampa": "45300",
    "orlando": "36740",
    "charlotte": "16740",
    "nashville": "34980",
    "raleigh": "39580",
    "richmond": "40060",       # Fixed: removed duplicate
    "memphis": "32820",
    "louisville": "31140",
    "oklahoma city": "36420",
    "kansas city": "28140",
    "columbus": "18140",
    "indianapolis": "26900",
    "jacksonville": "27260",
    "salt lake city": "41620",
    "san jose": "41940",
    "sacramento": "40900",
    "pittsburgh": "38300",
    "cincinnati": "17140",
    "cleveland": "17460",
    "st louis": "41180",
    "baltimore": "12580",
    "washington": "47900",
    "new orleans": "35380",
    "buffalo": "15380",
    "hartford": "25540",
    "birmingham": "13820",
    "tucson": "46060",
    "fresno": "23420",
}

# -------------------------------------------------------------------
# Valid code sets for validation
# VALID_NAICS uses a broader set so Haiku-returned codes
# that are real NAICS codes but not in our lookup table still pass.
# -------------------------------------------------------------------
VALID_NAICS = {
    # Food & Beverage
    "311811", "722511", "722513", "722515", "722410", "722514",
    "445110", "445131", "445132", "445210", "445230", "445291",
    # Retail - Clothing & Accessories
    "448110", "448120", "448130", "448140", "448150", "448190",
    "448210", "448310", "448320",
    # Retail - General
    "452111", "452112", "452319", "453110", "453210", "453220",
    "453310", "453910", "453920", "453930", "453991", "453998",
    # Health & Personal Care
    "446110", "446120", "446191", "446199",
    # Personal Services
    "812111", "812112", "812113", "812191", "812199",
    "812210", "812220", "812310", "812320", "812331", "812332",
    # Fitness & Recreation
    "713940", "713910", "713920", "713930", "713950", "713990",
    # Home & Garden
    "444110", "444120", "444130", "444190", "444210", "444220",
    # Furniture & Electronics
    "442110", "442210", "442291", "442299",
    "443141", "443142",
    # Books & Hobby
    "451110", "451120", "451130", "451140", "451211", "451212",
    # Auto
    "441110", "441120", "441210", "441222", "441228",
    "441310", "441320",
    # Other
    "621111", "621210", "621310", "621320", "621330", "621340",
    "624110", "624120", "624190", "624210",
}

VALID_MSA = set(MSA_LOOKUP.values())


def _haiku_map(business_type: str, city: str, state: str) -> dict:
    """Use the Data Agent (Ollama) to map business type and location to NAICS + MSA codes."""
    return _agent_resolve_codes(business_type, city, state)


def _validate_naics(code: str) -> bool:
    return code in VALID_NAICS


def _validate_msa(code: str) -> bool:
    return code in VALID_MSA


def _fallback_naics() -> str:
    """Return most generic retail NAICS if all else fails."""
    return "452319"  # General merchandise store


def _fallback_msa() -> str:
    """Return Dallas MSA as safe fallback."""
    return "19100"


def extract_context_from_dict(twin: dict) -> dict:
    """
    Build business context from an in-memory twin_layer dict.
    Same output as extract_context() but no file I/O.
    Used by build_market_snapshot() in ml/main.py.
    """
    meta = twin.get("meta") or {}
    bp   = twin.get("business_profile") or {}
    loc  = bp.get("location") or {}

    business_name    = str(meta.get("business_name") or "Business")
    business_type    = str(bp.get("business_type") or "").lower().strip()
    city             = str(loc.get("city") or "").lower().strip()
    state            = str(loc.get("state") or "").lower().strip()
    forecast_horizon = meta.get("forecast_horizon_months") or 6

    naics_code = NAICS_LOOKUP.get(business_type)
    msa_code   = MSA_LOOKUP.get(city)

    if not naics_code or not msa_code:
        print(f"[context] Missing codes — calling Data Agent (NAICS missing: {not naics_code}, MSA missing: {not msa_code})...")
        agent_result = _haiku_map(business_type, city, state)

        if not naics_code:
            naics_code = agent_result.get("naics_code", "")
            if not _validate_naics(naics_code):
                print(f"[context] Invalid NAICS '{naics_code}' returned, using fallback.")
                naics_code = _fallback_naics()

        if not msa_code:
            msa_code = agent_result.get("msa_code", "")
            if not _validate_msa(msa_code):
                print(f"[context] Invalid MSA '{msa_code}' returned, using fallback.")
                msa_code = _fallback_msa()

    context = {
        "business_name":           business_name,
        "business_type":           business_type,
        "city":                    city,
        "state":                   state,
        "naics_code":              naics_code,
        "msa_code":                msa_code,
        "forecast_horizon_months": forecast_horizon,
    }

    print(f"[context] Resolved → NAICS: {naics_code}, MSA: {msa_code}")
    return context


def extract_context(ip_path: str) -> dict:
    """
    Read IP file and return business context with NAICS + MSA codes.

    Returns:
        {
            business_name, business_type, city, state,
            naics_code, msa_code,
            forecast_horizon_months
        }
    """
    # --- Load IP file ---
    if not os.path.exists(ip_path):
        raise FileNotFoundError(f"IP file not found: {ip_path}")

    with open(ip_path, "r") as f:
        ip = json.load(f)

    business_name = ip["meta"]["business_name"]
    business_type = ip["business_profile"]["business_type"].lower().strip()
    city = ip["business_profile"]["location"]["city"].lower().strip()
    state = ip["business_profile"]["location"]["state"].lower().strip()
    # forecast_horizon_months lives in meta for IP2, default to 6
    forecast_horizon = (
        ip.get("meta", {}).get("forecast_horizon_months")
        or ip.get("simulation_parameters", {}).get("forecast_horizon_months")
        or 6
    )

    # --- NAICS + MSA mapping ---
    naics_code = NAICS_LOOKUP.get(business_type)
    msa_code = MSA_LOOKUP.get(city)

    # If either is missing, make a single Haiku call to resolve both
    if not naics_code or not msa_code:
        print(f"[context] Missing codes — calling Claude Haiku (NAICS missing: {not naics_code}, MSA missing: {not msa_code})...")
        haiku_result = _haiku_map(business_type, city, state)

        if not naics_code:
            naics_code = haiku_result.get("naics_code", "")
            if not _validate_naics(naics_code):
                print(f"[context] Invalid NAICS '{naics_code}' returned, using fallback.")
                naics_code = _fallback_naics()

        if not msa_code:
            msa_code = haiku_result.get("msa_code", "")
            if not _validate_msa(msa_code):
                print(f"[context] Invalid MSA '{msa_code}' returned, using fallback.")
                msa_code = _fallback_msa()

    context = {
        "business_name": business_name,
        "business_type": business_type,
        "city": city,
        "state": state,
        "naics_code": naics_code,
        "msa_code": msa_code,
        "forecast_horizon_months": forecast_horizon,
    }

    print(f"[context] Resolved → NAICS: {naics_code}, MSA: {msa_code}")
    return context
