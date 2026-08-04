"""
Converts raw ActiveNet JSON (from /rest/activities/list) into our normalized schema.
Field mappings verified against a real captured response — see fixtures/real_api_sample.json.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Optional
import json


@dataclass
class Facility:
    facility_id: str
    name: str
    address: Optional[str] = None
    lat: Optional[float] = None
    lon: Optional[float] = None


@dataclass
class Session:
    session_id: str
    activity_name: str
    category: Optional[str]
    facility_id: str
    min_age_months: Optional[int]
    max_age_months: Optional[int]
    days_of_week: list  # e.g. ["Tue", "Thu"]
    start_time: str      # "HH:MM" 24-hour
    end_time: str        # "HH:MM" 24-hour
    session_start_date: str  # "YYYY-MM-DD"
    session_end_date: str
    status: str            # "open" | "full"
    spots_available: Optional[int]
    price: Optional[float]
    registration_url: Optional[str]
    facility_name: Optional[str] = None


def _age_to_months(years: int, months: int, weeks: int) -> int:
    return years * 12 + months + round(weeks / 4.33)


def _normalize_time_token(token: str) -> str:
    """Map special ActiveNet time words to parseable strings."""
    return {"Noon": "12:00 PM", "Midnight": "12:00 AM"}.get(token.strip(), token.strip())


def _parse_time_range(time_range: str) -> tuple[str, str]:
    """Parse "9:00 AM - 9:30 AM" or "Noon - 12:45 PM" -> ("09:00", "09:30")."""
    start_raw, end_raw = time_range.split(" - ", 1)
    start = datetime.strptime(_normalize_time_token(start_raw), "%I:%M %p")
    end = datetime.strptime(_normalize_time_token(end_raw), "%I:%M %p")
    return start.strftime("%H:%M"), end.strftime("%H:%M")


def _parse_days(days_of_week: str) -> list[str]:
    """Parse "Tue, Thu" or "Sat" -> ["Tue", "Thu"] or ["Sat"]."""
    return [d.strip() for d in days_of_week.split(",") if d.strip()]


def _derive_status(openings: str) -> str:
    try:
        return "open" if int(openings) > 0 else "full"
    except (ValueError, TypeError):
        return "full"


def _facility_id(location_label: str) -> str:
    return location_label.lower().replace(" ", "_").replace("&", "and")


def normalize_response(raw: dict) -> tuple[list[Facility], list[Session]]:
    facilities: dict[str, Facility] = {}
    sessions: list[Session] = []

    items = raw.get("body", {}).get("activity_items", [])
    for item in items:
        loc_label = item["location"]["label"]
        fid = _facility_id(loc_label)
        if fid not in facilities:
            facilities[fid] = Facility(facility_id=fid, name=loc_label)

        start_time, end_time = _parse_time_range(item["time_range"])

        min_months = _age_to_months(
            item.get("age_min_year", 0),
            item.get("age_min_month", 0),
            item.get("age_min_week", 0),
        )
        max_months = _age_to_months(
            item.get("age_max_year", 0),
            item.get("age_max_month", 0),
            item.get("age_max_week", 0),
        ) or None  # 0 means no upper bound

        end_date = item.get("date_range_end") or item.get("date_range_start", "")

        sessions.append(
            Session(
                session_id=str(item["id"]),
                activity_name=item["name"],
                category=None,
                facility_id=fid,
                facility_name=loc_label,
                min_age_months=min_months if min_months else None,
                max_age_months=max_months,
                days_of_week=_parse_days(item.get("days_of_week", "")),
                start_time=start_time,
                end_time=end_time,
                session_start_date=item.get("date_range_start", ""),
                session_end_date=end_date,
                status=_derive_status(item.get("openings", "0")),
                spots_available=int(item["openings"]) if str(item.get("openings", "")).isdigit() else None,
                price=item.get("search_from_price"),
                registration_url=item.get("detail_url"),
            )
        )

    return list(facilities.values()), sessions


def load_fixture(path: str) -> tuple[list[Facility], list[Session]]:
    with open(path) as f:
        raw = json.load(f)
    return normalize_response(raw)


if __name__ == "__main__":
    facilities, sessions = load_fixture("fixtures/sample_raw_response.json")
    print(f"Loaded {len(facilities)} facilities, {len(sessions)} sessions")
    for s in sessions:
        print(asdict(s))
