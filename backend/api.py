from __future__ import annotations

from dataclasses import asdict
from datetime import date
from math import atan2, cos, radians, sin, sqrt
from pathlib import Path
from typing import Optional

import requests as http_requests
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

from backend.db import load_facility_coords, load_sessions
from backend.matching import (
    Registrant, SearchPreferences, eligible_sessions_for, find_matches, full_sessions_for,
)

app = FastAPI(title="Parks & Rec Finder API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_NOM_URL = "https://nominatim.openstreetmap.org/search"
_NOM_HEADERS = {"User-Agent": "parks-rec-finder/1.0 (educational project)"}


def _geocode(address: str) -> Optional[tuple[float, float]]:
    query = address if "portland" in address.lower() else f"{address}, Portland, OR"
    try:
        resp = http_requests.get(
            _NOM_URL,
            params={"q": query, "format": "json", "limit": 1, "countrycodes": "us"},
            headers=_NOM_HEADERS,
            timeout=5,
        )
        data = resp.json()
        if data:
            return float(data[0]["lat"]), float(data[0]["lon"])
    except Exception:
        pass
    return None


def _haversine_miles(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 3958.8
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return R * 2 * atan2(sqrt(a), sqrt(1 - a))


class RegistrantIn(BaseModel):
    label: str
    birth_date: str  # ISO date "YYYY-MM-DD"


class SearchRequest(BaseModel):
    registrants: list[RegistrantIn]
    day_pref: Optional[str] = None   # "weekday" | "weekend"
    time_pref: Optional[str] = None  # "morning" | "afternoon" | "evening"
    categories: Optional[list[str]] = None  # e.g. ["Aquatics", "Art"]; empty/omitted = any
    address: Optional[str] = None
    address_lat: Optional[float] = None  # pre-resolved coords from autocomplete
    address_lon: Optional[float] = None


@app.post("/search")
def search(req: SearchRequest):
    sessions = load_sessions()
    if not sessions:
        raise HTTPException(
            status_code=503,
            detail="Session data not available. Run `python -m scraper.ingest` to populate the database.",
        )

    registrants = [
        Registrant(label=r.label, birth_date=date.fromisoformat(r.birth_date))
        for r in req.registrants
    ]
    prefs = SearchPreferences(day_pref=req.day_pref, time_pref=req.time_pref, categories=req.categories)
    today = date.today()

    # Build facility → distance map if an address was provided.
    facility_distances: dict[str, float] = {}
    if req.address and req.address.strip():
        if req.address_lat is not None and req.address_lon is not None:
            user_lat, user_lon = req.address_lat, req.address_lon
        else:
            coords = _geocode(req.address.strip())
            if coords is None:
                raise HTTPException(
                    status_code=400,
                    detail="Address not found. Try a more specific address (e.g. '1234 NE Alberta St').",
                )
            user_lat, user_lon = coords
        for fid, (fac_lat, fac_lon) in load_facility_coords().items():
            facility_distances[fid] = round(
                _haversine_miles(user_lat, user_lon, fac_lat, fac_lon), 1
            )

    def _annotate(session_dict: dict) -> dict:
        fid = session_dict.get("facility_id")
        if fid and fid in facility_distances:
            session_dict["distance_miles"] = facility_distances[fid]
        return session_dict

    def _result_distance(result) -> float:
        first_session = next(iter(result.sessions_by_registrant.values()))
        return facility_distances.get(first_session.facility_id, float("inf"))

    results = find_matches(registrants, sessions, prefs, today=today)
    if facility_distances:
        results.sort(key=_result_distance)

    full_raw = {
        r.label: full_sessions_for(r, sessions, prefs, today) for r in registrants
    }
    if facility_distances:
        for label in full_raw:
            full_raw[label].sort(
                key=lambda s: facility_distances.get(s.facility_id, float("inf"))
            )

    return {
        "tier": results[0].tier if results else None,
        "results": [
            {
                "tier": r.tier,
                "sessions": {
                    label: _annotate(asdict(session))
                    for label, session in r.sessions_by_registrant.items()
                },
            }
            for r in results
        ],
        "full_sessions": {
            label: [_annotate(asdict(s)) for s in slist]
            for label, slist in full_raw.items()
        },
    }


@app.get("/categories")
def categories(birth_dates: list[str] = Query(default=[])):
    """Distinct activity categories available to filter on, e.g. "Aquatics", "Art".

    If birth_dates (ISO "YYYY-MM-DD") are given, only categories with at
    least one open, future, age-eligible session for one of those children
    are returned — so e.g. a toddler's parent won't see adult-only chips.
    """
    sessions = load_sessions()

    registrants = []
    for bd in birth_dates:
        try:
            registrants.append(Registrant(label=bd, birth_date=date.fromisoformat(bd)))
        except (ValueError, TypeError):
            continue

    if not registrants:
        return {"categories": sorted({s.category for s in sessions if s.category})}

    today = date.today()
    prefs = SearchPreferences()
    eligible_categories = {
        s.category
        for r in registrants
        for s in eligible_sessions_for(r, sessions, prefs, today)
        if s.category
    }
    return {"categories": sorted(eligible_categories)}


@app.get("/geocode")
def geocode_suggestions(q: str = ""):
    """Return up to 5 address suggestions for the given partial query."""
    q = q.strip()
    if len(q) < 4:
        return {"suggestions": []}
    query = q if "portland" in q.lower() else f"{q}, Portland, OR"
    try:
        resp = http_requests.get(
            _NOM_URL,
            params={"q": query, "format": "json", "limit": 5, "countrycodes": "us", "addressdetails": 1},
            headers=_NOM_HEADERS,
            timeout=5,
        )
        results = resp.json()
    except Exception:
        return {"suggestions": []}

    suggestions = []
    for r in results:
        addr = r.get("address", {})
        parts = [p for p in [
            addr.get("house_number", "") + " " + addr.get("road", ""),
            addr.get("city") or addr.get("town") or addr.get("village"),
            addr.get("state"),
        ] if p and p.strip()]
        label = ", ".join(p.strip() for p in parts if p.strip()) or r["display_name"].split(",")[0]
        suggestions.append({"label": label, "lat": float(r["lat"]), "lon": float(r["lon"])})

    return {"suggestions": suggestions}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/")
def frontend():
    return FileResponse(Path(__file__).parent.parent / "frontend" / "index.html")
