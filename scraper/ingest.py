"""
Populates data/sessions.db with fresh data from ActiveNet.
Run on a schedule (e.g., nightly cron) to keep the DB current.

Usage:
    python -m scraper.ingest
"""
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from scraper.fetch import fetch_sessions
from scraper.normalize import normalize_response

DB_PATH = Path(__file__).parent.parent / "data" / "sessions.db"
SCHEMA_PATH = Path(__file__).parent.parent / "data" / "schema.sql"

# Fetch with no server-side age filter to maximize catalog coverage.
# matching.py does the authoritative client-side age filtering.
_FETCH_MIN_AGE_MONTHS = 0
_FETCH_MAX_AGE_MONTHS = 0


def _init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA_PATH.read_text())
    conn.commit()


def ingest() -> None:
    import os
    if not os.environ.get("ACTIVENET_COOKIE"):
        print("⚠  ACTIVENET_COOKIE not set — will only retrieve ~20 activities.")
        print("   See scraper/fetch.py for instructions to get the full catalog.")
    print("Fetching sessions from ActiveNet...")
    raw = fetch_sessions(_FETCH_MIN_AGE_MONTHS, _FETCH_MAX_AGE_MONTHS)
    facilities, sessions = normalize_response(raw)
    print(f"  {len(sessions)} sessions across {len(facilities)} facilities")

    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    _init_db(conn)

    now = datetime.now(timezone.utc).isoformat()

    for fac in facilities:
        conn.execute(
            """
            INSERT INTO facilities (facility_id, name, address, lat, lon)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(facility_id) DO UPDATE SET
                name=excluded.name,
                address=excluded.address
            """,
            (fac.facility_id, fac.name, fac.address, fac.lat, fac.lon),
        )

    for s in sessions:
        conn.execute(
            """
            INSERT INTO sessions (
                session_id, activity_name, category, facility_id,
                min_age_months, max_age_months,
                days_of_week, start_time, end_time,
                session_start_date, session_end_date,
                status, spots_available, price, registration_url, last_scraped_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(session_id) DO UPDATE SET
                activity_name=excluded.activity_name,
                category=excluded.category,
                facility_id=excluded.facility_id,
                min_age_months=excluded.min_age_months,
                max_age_months=excluded.max_age_months,
                days_of_week=excluded.days_of_week,
                start_time=excluded.start_time,
                end_time=excluded.end_time,
                session_start_date=excluded.session_start_date,
                session_end_date=excluded.session_end_date,
                status=excluded.status,
                spots_available=excluded.spots_available,
                price=excluded.price,
                registration_url=excluded.registration_url,
                last_scraped_at=excluded.last_scraped_at
            """,
            (
                s.session_id, s.activity_name, s.category, s.facility_id,
                s.min_age_months, s.max_age_months,
                json.dumps(s.days_of_week), s.start_time, s.end_time,
                s.session_start_date, s.session_end_date,
                s.status, s.spots_available, s.price, s.registration_url, now,
            ),
        )

    conn.commit()
    conn.close()
    print(f"Done. DB written to {DB_PATH}")


if __name__ == "__main__":
    ingest()
