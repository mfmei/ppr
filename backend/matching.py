"""
Core filtering + tiered multi-child matching logic.

Tiers for a multi-child search, in priority order:
  1. SIMULTANEOUS — one session per child, same facility, overlapping time,
     on a shared date.
  2. BACK_TO_BACK — one session per child, same facility, sequential in
     time with a gap small enough to be realistic (default: <= 30 min).
  3. PARTIAL — no combination covers every child; fall back to each
     child's individually eligible sessions, labeled with which child(ren)
     they're for.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, date
from itertools import product
from typing import Optional

from scraper.normalize import Session

BACK_TO_BACK_MAX_GAP_MINUTES = 30

WEEKDAY_DAYS = {"Mon", "Tue", "Wed", "Thu", "Fri"}
WEEKEND_DAYS = {"Sat", "Sun"}


@dataclass
class Registrant:
    label: str          # e.g. "Kid 1" or a parent-supplied name
    birth_date: date


@dataclass
class SearchPreferences:
    day_pref: Optional[str] = None   # "weekday" | "weekend" | None
    time_pref: Optional[str] = None  # "morning" | "afternoon" | "evening" | None
    categories: Optional[list[str]] = None  # e.g. ["Aquatics", "Art"]; None/empty = any


def age_in_months(birth_date: date, as_of: date) -> int:
    """Whole months elapsed between birth_date and as_of."""
    months = (as_of.year - birth_date.year) * 12 + (as_of.month - birth_date.month)
    if as_of.day < birth_date.day:
        months -= 1
    return max(0, months)


def _time_to_minutes(hhmm: str) -> int:
    h, m = map(int, hhmm.split(":"))
    return h * 60 + m


def _time_of_day_bucket(hhmm: str) -> str:
    minutes = _time_to_minutes(hhmm)
    if minutes < 12 * 60:
        return "morning"
    if minutes < 17 * 60:
        return "afternoon"
    return "evening"


def is_future(session: Session, today: date) -> bool:
    session_start = datetime.strptime(session.session_start_date, "%Y-%m-%d").date()
    return session_start >= today


def matches_day_pref(session: Session, day_pref: Optional[str]) -> bool:
    if day_pref is None:
        return True
    days = set(session.days_of_week)
    if day_pref == "weekday":
        return bool(days & WEEKDAY_DAYS)
    if day_pref == "weekend":
        return bool(days & WEEKEND_DAYS)
    return True


def matches_time_pref(session: Session, time_pref: Optional[str]) -> bool:
    if time_pref is None:
        return True
    return _time_of_day_bucket(session.start_time) == time_pref


def matches_category_pref(session: Session, categories: Optional[list[str]]) -> bool:
    if not categories:
        return True
    return session.category in categories


def _age_and_pref_match(
    registrant: Registrant,
    session: Session,
    prefs: SearchPreferences,
    today: date,
) -> bool:
    """True if session is future, fits registrant's age at session start, and matches prefs."""
    if not is_future(session, today):
        return False
    session_start = datetime.strptime(session.session_start_date, "%Y-%m-%d").date()
    age = age_in_months(registrant.birth_date, session_start)
    # A missing bound means ActiveNet lists no restriction on that side
    # (e.g. "11+" has a min but no max) -- treat as unbounded, not invalid.
    min_age = session.min_age_months if session.min_age_months is not None else 0
    max_age = session.max_age_months if session.max_age_months is not None else float("inf")
    if not (min_age <= age <= max_age):
        return False
    if not matches_day_pref(session, prefs.day_pref):
        return False
    if not matches_time_pref(session, prefs.time_pref):
        return False
    if not matches_category_pref(session, prefs.categories):
        return False
    return True


def eligible_sessions_for(
    registrant: Registrant,
    sessions: list[Session],
    prefs: SearchPreferences,
    today: date,
) -> list[Session]:
    """Open sessions matching age + prefs. Age evaluated at session start date."""
    return [
        s for s in sessions
        if s.status == "open" and _age_and_pref_match(registrant, s, prefs, today)
    ]


def full_sessions_for(
    registrant: Registrant,
    sessions: list[Session],
    prefs: SearchPreferences,
    today: date,
) -> list[Session]:
    """Full sessions matching age + prefs — shown separately so parents can waitlist."""
    return [
        s for s in sessions
        if s.status == "full" and _age_and_pref_match(registrant, s, prefs, today)
    ]


def _overlaps(a: Session, b: Session) -> bool:
    if a.facility_id != b.facility_id:
        return False
    if not (set(a.days_of_week) & set(b.days_of_week)):
        return False
    a_start, a_end = _time_to_minutes(a.start_time), _time_to_minutes(a.end_time)
    b_start, b_end = _time_to_minutes(b.start_time), _time_to_minutes(b.end_time)
    return a_start < b_end and b_start < a_end


def _back_to_back_gap_minutes(a: Session, b: Session) -> Optional[int]:
    """Returns the gap in minutes if a ends before b starts (or vice versa)
    at the same facility on a shared day, else None."""
    if a.facility_id != b.facility_id:
        return None
    if not (set(a.days_of_week) & set(b.days_of_week)):
        return None
    a_start, a_end = _time_to_minutes(a.start_time), _time_to_minutes(a.end_time)
    b_start, b_end = _time_to_minutes(b.start_time), _time_to_minutes(b.end_time)
    if a_end <= b_start:
        return b_start - a_end
    if b_end <= a_start:
        return a_start - b_end
    return None


@dataclass
class MatchResult:
    tier: str  # "simultaneous" | "back_to_back" | "partial"
    sessions_by_registrant: dict  # {registrant_label: Session}


def find_matches(
    registrants: list[Registrant],
    sessions: list[Session],
    prefs: SearchPreferences,
    today: Optional[date] = None,
) -> list[MatchResult]:
    if today is None:
        today = date.today()

    per_registrant_eligible = {
        r.label: eligible_sessions_for(r, sessions, prefs, today) for r in registrants
    }

    if len(registrants) == 1:
        r = registrants[0]
        return [
            MatchResult(tier="partial", sessions_by_registrant={r.label: s})
            for s in per_registrant_eligible[r.label]
        ]

    # Try every combination of one eligible session per registrant.
    labels = [r.label for r in registrants]
    combos = list(product(*[per_registrant_eligible[label] for label in labels]))

    simultaneous: list[MatchResult] = []
    back_to_back: list[MatchResult] = []

    for combo in combos:
        pairs_ok_simultaneous = all(
            _overlaps(combo[i], combo[j])
            for i in range(len(combo))
            for j in range(i + 1, len(combo))
        )
        if pairs_ok_simultaneous:
            simultaneous.append(
                MatchResult(
                    tier="simultaneous",
                    sessions_by_registrant=dict(zip(labels, combo)),
                )
            )
            continue

        pairs_ok_b2b = all(
            (
                _overlaps(combo[i], combo[j])
                or (
                    (gap := _back_to_back_gap_minutes(combo[i], combo[j])) is not None
                    and gap <= BACK_TO_BACK_MAX_GAP_MINUTES
                )
            )
            for i in range(len(combo))
            for j in range(i + 1, len(combo))
        )
        if pairs_ok_b2b:
            back_to_back.append(
                MatchResult(
                    tier="back_to_back",
                    sessions_by_registrant=dict(zip(labels, combo)),
                )
            )

    if simultaneous:
        return simultaneous
    if back_to_back:
        return back_to_back

    # Tier 3: partial — per-child eligible sessions, labeled individually.
    partial = []
    for label, sessions_for_reg in per_registrant_eligible.items():
        for s in sessions_for_reg:
            partial.append(MatchResult(tier="partial", sessions_by_registrant={label: s}))
    return partial
