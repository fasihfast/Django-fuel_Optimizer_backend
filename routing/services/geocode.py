"""
Thin wrapper around the free "Open-Meteo Geocoding API".

Why this instead of Nominatim (OpenStreetMap)? Nominatim is also free, but
its public server aggressively blocks plain script/requests traffic with
a 403 depending on your IP/region, even with a correct User-Agent - this
is a known, fairly common headache and not something we can fix from our
side. Open-Meteo's geocoding endpoint is free, needs no API key, and
doesn't have that problem.

Docs: https://open-meteo.com/en/docs/geocoding-api

This module is used in two places:
1. The `load_fuel_stations` management command - a ONE-TIME offline step
   that geocodes every unique (city, state) in the CSV once and caches
   the result in the database. This is what keeps our live API fast and
   keeps us from hammering a free public service on every request.
2. The live API view - to geocode the user-supplied start/finish
   locations (2 calls per request, which is within the "2-3 calls is
   acceptable" budget from the assessment brief).
"""
import time

import requests
from django.conf import settings

# Maps "IL" -> "Illinois" etc. so we can disambiguate same-named cities in
# different states (Open-Meteo's `admin1` field returns the full state name,
# not the abbreviation our CSV/users give us).
US_STATE_NAMES = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas",
    "CA": "California", "CO": "Colorado", "CT": "Connecticut", "DE": "Delaware",
    "FL": "Florida", "GA": "Georgia", "HI": "Hawaii", "ID": "Idaho",
    "IL": "Illinois", "IN": "Indiana", "IA": "Iowa", "KS": "Kansas",
    "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine", "MD": "Maryland",
    "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota", "MS": "Mississippi",
    "MO": "Missouri", "MT": "Montana", "NE": "Nebraska", "NV": "Nevada",
    "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico", "NY": "New York",
    "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma",
    "OR": "Oregon", "PA": "Pennsylvania", "RI": "Rhode Island", "SC": "South Carolina",
    "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas", "UT": "Utah",
    "VT": "Vermont", "VA": "Virginia", "WA": "Washington", "WV": "West Virginia",
    "WI": "Wisconsin", "WY": "Wyoming", "DC": "District of Columbia",
}


class GeocodeError(Exception):
    """Raised when a location string can't be turned into coordinates."""


def _query_open_meteo(name: str, count: int = 10) -> list:
    params = {"name": name, "count": count, "language": "en", "country": "US"}
    response = requests.get(
        settings.GEOCODE_API_URL,
        params=params,
        timeout=10,
    )
    response.raise_for_status()
    return response.json().get("results") or []


def _pick_best_match(results: list, state_hint):
    """
    Open-Meteo returns results ranked by relevance/population, so the first
    one is usually right. If the caller gave us a state (e.g. "IL"), prefer
    a result whose `admin1` (full state name) matches, to correctly
    disambiguate things like "Springfield, IL" vs "Springfield, MO".
    """
    if state_hint:
        full_state_name = US_STATE_NAMES.get(state_hint.strip().upper())
        if full_state_name:
            matches = [r for r in results if r.get("admin1") == full_state_name]
            if matches:
                return matches[0]
    return results[0]


def geocode_place(query: str) -> dict:
    """
    Geocode a place string, e.g. "Chicago, IL" or "Chicago, Illinois".
    (Open-Meteo searches by place *name*, so a full street address like
    "350 5th Ave, New York, NY" should just be shortened to "New York, NY"
    for best results - city/state level is what this API is built for.)

    Returns: {"latitude": float, "longitude": float, "display_name": str}
    Raises: GeocodeError if nothing is found.
    """
    parts = [p.strip() for p in query.split(",")]
    place_name = parts[0]
    state_hint = parts[-1] if len(parts) >= 2 else None

    results = _query_open_meteo(place_name)
    if not results:
        raise GeocodeError(f"Could not geocode location: {query!r}")

    match = _pick_best_match(results, state_hint)
    state_full = match.get("admin1", "")
    return {
        "latitude": float(match["latitude"]),
        "longitude": float(match["longitude"]),
        "display_name": f"{match.get('name', place_name)}, {state_full}, USA".strip(", "),
    }


def geocode_city_state(city: str, state: str):
    """
    Used only by the offline management command to geocode fuel stations.
    Returns None (instead of raising) on failure, since we're geocoding
    thousands of rows and a handful of misses shouldn't kill the batch job.

    Sleeps briefly after each call - Open-Meteo doesn't publish a hard
    rate limit for this endpoint, but pacing requests is good manners on
    any free shared service.
    """
    try:
        results = _query_open_meteo(city)
        if not results:
            return None
        match = _pick_best_match(results, state)
        result = {"latitude": float(match["latitude"]), "longitude": float(match["longitude"])}
    except (requests.RequestException, KeyError, ValueError):
        result = None
    finally:
        time.sleep(0.3)
    return result
