from datetime import date

from scraper.normalize import load_fixture
from backend.matching import (
    Registrant, SearchPreferences, find_matches, eligible_sessions_for,
    age_in_months, matches_category_pref,
)

FIXTURE_PATH = "scraper/fixtures/sample_raw_response.json"
TODAY = date(2026, 8, 1)

# Birth dates chosen so each registrant has the same effective age as the
# original age_months values when evaluated as of TODAY.
#   Toddler: 24 mo today  → born 2024-08-01; 25 mo at session start 2026-09-08
#   Preschooler: 48 mo today → born 2022-08-01; 49 mo at 2026-09-08
#   Older Kid: 72 mo today → born 2020-08-01; 73 mo at 2026-09-05
TODDLER      = Registrant(label="Toddler",      birth_date=date(2024, 8, 1))
PRESCHOOLER  = Registrant(label="Preschooler",  birth_date=date(2022, 8, 1))
OLDER_KID    = Registrant(label="Older Kid",    birth_date=date(2020, 8, 1))


# ── age_in_months unit tests ────────────────────────────────────────────────

def test_age_in_months_whole_years():
    assert age_in_months(date(2024, 6, 1), date(2026, 6, 1)) == 24

def test_age_in_months_partial_month_not_yet_birthday():
    # Birthday is the 15th; as_of is the 10th → birthday hasn't happened yet
    assert age_in_months(date(2025, 3, 15), date(2026, 4, 10)) == 12

def test_age_in_months_partial_month_birthday_passed():
    assert age_in_months(date(2025, 3, 15), date(2026, 4, 20)) == 13


# ── eligibility tests ───────────────────────────────────────────────────────

def test_eligible_sessions_excludes_full_and_past():
    _facilities, sessions = load_fixture(FIXTURE_PATH)
    prefs = SearchPreferences()

    eligible = eligible_sessions_for(TODDLER, sessions, prefs, TODAY)
    ids = {s.session_id for s in eligible}

    # 1001 fits (age 12-35mo, open, future)
    assert "1001" in ids
    # 1003 fits age range but is FULL -> excluded
    assert "1003" not in ids


def test_age_computed_at_session_start_not_today():
    """A child who is currently below the minimum age should match if they
    will reach it before the session begins."""
    _facilities, sessions = load_fixture(FIXTURE_PATH)
    prefs = SearchPreferences()

    # born 2025-09-01 → 11 months old on TODAY (2026-08-01)
    #                  → turns 12 months on 2026-09-01
    # Session 1001 requires min 12 months and starts 2026-09-08 → eligible
    almost_one = Registrant(label="Almost One", birth_date=date(2025, 9, 1))
    eligible_ids = {s.session_id for s in eligible_sessions_for(almost_one, sessions, prefs, TODAY)}
    assert "1001" in eligible_ids


def test_age_at_session_start_excludes_child_still_too_young():
    """A child who won't reach the minimum age until after the session starts
    should not be included."""
    _facilities, sessions = load_fixture(FIXTURE_PATH)
    prefs = SearchPreferences()

    # born 2025-09-10 → 11 months old on TODAY (2026-08-01)
    #                  → still 11 months on session start 2026-09-08 (birthday is 2026-09-10)
    just_under = Registrant(label="Just Under", birth_date=date(2025, 9, 10))
    eligible_ids = {s.session_id for s in eligible_sessions_for(just_under, sessions, prefs, TODAY)}
    assert "1001" not in eligible_ids


# ── matching tier tests ─────────────────────────────────────────────────────

def test_single_registrant_returns_partial_tier():
    _facilities, sessions = load_fixture(FIXTURE_PATH)
    results = find_matches([TODDLER], sessions, SearchPreferences(), today=TODAY)
    assert all(r.tier == "partial" for r in results)
    assert len(results) >= 1


def test_two_kids_simultaneous_match_found():
    """1001 (12-35mo, 09:00-09:30, FAC-01) and 1002 (36-60mo,
    09:30-10:15, FAC-01) are back-to-back, not overlapping — so this
    should surface as back_to_back, not simultaneous."""
    _facilities, sessions = load_fixture(FIXTURE_PATH)
    results = find_matches([TODDLER, PRESCHOOLER], sessions, SearchPreferences(), today=TODAY)
    assert len(results) >= 1
    assert results[0].tier == "back_to_back"
    assert results[0].sessions_by_registrant["Toddler"].session_id == "1001"
    assert results[0].sessions_by_registrant["Preschooler"].session_id == "1002"


def test_no_shared_slot_falls_back_to_partial():
    """A toddler and a school-age kid have no combined facility/time overlap."""
    _facilities, sessions = load_fixture(FIXTURE_PATH)
    results = find_matches([TODDLER, OLDER_KID], sessions, SearchPreferences(), today=TODAY)
    assert all(r.tier == "partial" for r in results)
    assert all(len(r.sessions_by_registrant) == 1 for r in results)


def test_day_and_time_preferences_filter_correctly():
    _facilities, sessions = load_fixture(FIXTURE_PATH)
    weekend_only = SearchPreferences(day_pref="weekend")
    eligible = eligible_sessions_for(TODDLER, sessions, weekend_only, TODAY)
    # 1001 is Tue/Thu (weekday) so should be excluded under weekend_only
    assert all("Sat" in s.days_of_week or "Sun" in s.days_of_week for s in eligible)


# ── category preference ─────────────────────────────────────────────────────

def test_category_pref_filters_to_selected_categories():
    _facilities, sessions = load_fixture(FIXTURE_PATH)
    aquatics_only = SearchPreferences(categories=["Aquatics"])
    eligible = eligible_sessions_for(TODDLER, sessions, aquatics_only, TODAY)
    # 1001 "Aquatics - Little Swimmers Level 1" fits; 1003 "Art - ..." should be excluded
    ids = {s.session_id for s in eligible}
    assert "1001" in ids
    assert all(s.category == "Aquatics" for s in eligible)


def test_no_category_pref_matches_any_category():
    _facilities, sessions = load_fixture(FIXTURE_PATH)
    assert all(matches_category_pref(s, None) for s in sessions)
    assert all(matches_category_pref(s, []) for s in sessions)


def test_category_pref_matches_any_of_multiple_selected():
    _facilities, sessions = load_fixture(FIXTURE_PATH)
    by_id = {s.session_id: s for s in sessions}
    assert matches_category_pref(by_id["1001"], ["Aquatics", "Fitness"])  # Aquatics
    assert matches_category_pref(by_id["1005"], ["Aquatics", "Dance"])  # Dance
    assert not matches_category_pref(by_id["1002"], ["Aquatics", "Dance"])  # Sports
