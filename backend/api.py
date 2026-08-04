from __future__ import annotations

from dataclasses import asdict
from datetime import date
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from backend.db import load_sessions
from backend.matching import Registrant, SearchPreferences, find_matches

app = FastAPI(title="Parks & Rec Finder API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten before any real deployment
    allow_methods=["*"],
    allow_headers=["*"],
)


class RegistrantIn(BaseModel):
    label: str
    birth_date: str  # ISO date "YYYY-MM-DD"


class SearchRequest(BaseModel):
    registrants: list[RegistrantIn]
    day_pref: Optional[str] = None   # "weekday" | "weekend"
    time_pref: Optional[str] = None  # "morning" | "afternoon" | "evening"


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
    prefs = SearchPreferences(day_pref=req.day_pref, time_pref=req.time_pref)

    results = find_matches(registrants, sessions, prefs)

    return {
        "tier": results[0].tier if results else None,
        "results": [
            {
                "tier": r.tier,
                "sessions": {
                    label: asdict(session) for label, session in r.sessions_by_registrant.items()
                },
            }
            for r in results
        ],
    }


@app.get("/health")
def health():
    return {"status": "ok"}
