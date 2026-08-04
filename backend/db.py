import json
import sqlite3
from pathlib import Path

from scraper.normalize import Session

DB_PATH = Path(__file__).parent.parent / "data" / "sessions.db"


def load_sessions() -> list[Session]:
    if not DB_PATH.exists():
        return []
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("""
        SELECT s.*, f.name AS facility_name
        FROM sessions s
        LEFT JOIN facilities f ON s.facility_id = f.facility_id
    """).fetchall()
    conn.close()
    return [
        Session(
            session_id=row["session_id"],
            activity_name=row["activity_name"],
            category=row["category"],
            facility_id=row["facility_id"],
            facility_name=row["facility_name"],
            min_age_months=row["min_age_months"],
            max_age_months=row["max_age_months"],
            days_of_week=json.loads(row["days_of_week"]) if row["days_of_week"] else [],
            start_time=row["start_time"],
            end_time=row["end_time"],
            session_start_date=row["session_start_date"],
            session_end_date=row["session_end_date"],
            status=row["status"],
            spots_available=row["spots_available"],
            price=row["price"],
            registration_url=row["registration_url"],
        )
        for row in rows
    ]
