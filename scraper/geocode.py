"""
One-time script: geocode all facilities and store lat/lon in the database.

Uses Nominatim (OpenStreetMap) — free, no API key required.
Nominatim's rate limit is 1 request/sec; this script enforces that.

Run from the project root:
    python3 -m scraper.geocode
"""
import sqlite3
import time
import requests
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "sessions.db"
_NOM_URL = "https://nominatim.openstreetmap.org/search"
_HEADERS = {"User-Agent": "parks-rec-finder/1.0 (educational project)"}


# Known addresses for facilities Nominatim can't find by name alone.
_KNOWN_ADDRESSES = {
    "Creston Outdoor Pool":     "4454 SE Powell Blvd, Portland, OR",
    "Grant Outdoor Pool":       "2300 NE 33rd Ave, Portland, OR",
    "Montavilla Outdoor Pool":  "320 SE 76th Ave, Portland, OR",
    "Pier Outdoor Pool":        "9341 N Columbia Blvd, Portland, OR",
    "Peninsula Outdoor Pool":   "700 N Rosa Parks Way, Portland, OR",
    "East Portland Indoor Pool": "740 SE 106th Ave, Portland, OR",
    "Matt Dishman Indoor Pool": "77 NE Knott St, Portland, OR",
    "Southwest Indoor Pool":    "6820 SW 45th Ave, Portland, OR",
    "Mt Scott Indoor Pool":     "5530 SE 72nd Ave, Portland, OR",
    "Sellwood Outdoor Pool":    "7951 SE 7th Ave, Portland, OR",
    "Cathedral Park is in North Portland. Meet in the grass near the parking lot, close to the entrance to the parking lot off N Bradford.  https://maps.app.goo.gl/nchJfCcZgTf8A7rYA":
        "N Bradford St & N Pittsburgh Ave, Portland, OR",
}

_ABBR = {
    "Cmty": "Community",
    "Ctr": "Center",
    "Mt ": "Mt. ",
    "Mt.": "Mount",
    "Cmty Ctr": "Community Center",
}


def _expand_abbr(name: str) -> str:
    for short, full in _ABBR.items():
        name = name.replace(short, full)
    return name


def _search_query(name: str) -> str:
    """Build a geocoding query from a facility name.

    Many names embed the address after a comma — use the street address
    for a tighter match. For abbreviated names, expand common shortenings.
    Falls back to just the name + city.
    """
    # Some facility names contain embedded full addresses with zip codes — extract just
    # the street number + street name before any comma or city/state/zip suffix.
    import re
    street_match = re.search(r'\d+\s+[NSEW]\w*\.?\s+\w+', name)
    if street_match:
        return f"{street_match.group()}, Portland, OR"

    parts = name.split(",", 1)
    if len(parts) == 2:
        addr = parts[1].strip()
        if any(c.isdigit() for c in addr):
            return f"{addr}, Portland, OR"

    return f"{_expand_abbr(name)}, Portland, OR"


def geocode_query(query: str):
    resp = requests.get(
        _NOM_URL,
        params={"q": query, "format": "json", "limit": 1, "countrycodes": "us"},
        headers=_HEADERS,
        timeout=10,
    )
    resp.raise_for_status()
    results = resp.json()
    if results:
        return float(results[0]["lat"]), float(results[0]["lon"])
    return None


def run():
    conn = sqlite3.connect(DB_PATH)
    facilities = conn.execute(
        "SELECT facility_id, name FROM facilities WHERE lat IS NULL"
    ).fetchall()

    if not facilities:
        print("All facilities already geocoded.")
        conn.close()
        return

    print(f"Geocoding {len(facilities)} facilities (1 request/sec)…\n")
    found = 0
    for fid, name in facilities:
        query = _KNOWN_ADDRESSES.get(name) or _search_query(name)
        print(f"  {name!r}\n    → {query!r} … ", end="", flush=True)
        result = geocode_query(query)
        if result:
            lat, lon = result
            conn.execute(
                "UPDATE facilities SET lat=?, lon=? WHERE facility_id=?",
                (lat, lon, fid),
            )
            conn.commit()
            print(f"({lat:.4f}, {lon:.4f})")
            found += 1
        else:
            print("not found")
        time.sleep(1.1)

    print(f"\nDone: {found}/{len(facilities)} facilities geocoded.")
    conn.close()


if __name__ == "__main__":
    run()
