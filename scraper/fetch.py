"""
Fetches activity listings from the Portland Parks & Rec ActiveNet backend.

Endpoint and request shape captured from DevTools (Network > Fetch/XHR) while
browsing https://anc.apm.activecommunities.com/portlandparks/activity/landing.

WITHOUT auth cookies the API ignores current_page entirely and always returns
the same first ~20 activities. WITH cookies (copied from a logged-in browser
session), current_page is respected in principle, but in practice the
server's pagination is still erratic -- confirmed via logging that ~90% of
page requests return the same first page's content regardless of which page
was requested, cycling through a handful of "lucky" pages seemingly at
random. fetch_sessions() compensates by re-sweeping all declared pages
several times (see _SWEEP_ATTEMPTS) and merging newly-seen items across
attempts, which in practice surfaces more of the catalog than any single
sweep -- but there's no guarantee of ever seeing 100% of it.

To enable cookie-authenticated fetching:
  1. Open https://anc.apm.activecommunities.com/portlandparks/activity/search
     in Chrome (no login required — just visiting the page sets the session).
  2. DevTools → Network tab → filter to Fetch/XHR → trigger any search.
  3. Click the POST request to .../rest/activities/list → Headers tab.
  4. Copy the full value of the "cookie:" request header.
  5. Set it as an environment variable before running the ingest:
       export ACTIVENET_COOKIE='<paste here>'
       python3 -m scraper.ingest

The server-side age filter (min_age/max_age) is in months but returns loose
overlapping matches rather than strict containment; client-side filtering in
matching.py is the authoritative filter.

Real captured response shape: scraper/fixtures/real_api_sample.json
"""
import os
import requests

_BASE = "https://anc.apm.activecommunities.com/portlandparks"
# The server ignores total_records_per_page (confirmed: requesting 100 still
# returns 20-item pages), so this can't be used to reduce the page count.
_PAGE_SIZE = 20

# Full search pattern the real browser sends. activity_select_param=2 is
# required — without it the server ignores current_page and always returns
# the same first batch.
_BASE_SEARCH_PATTERN = {
    "skills": [], "time_after_str": "", "days_of_week": None,
    "activity_select_param": 2, "center_ids": [], "time_before_str": "",
    "open_spots": None, "activity_id": None, "activity_category_ids": [],
    "date_before": "", "min_age": None, "date_after": "",
    "activity_type_ids": [], "site_ids": [], "for_map": False,
    "geographic_area_ids": [], "season_ids": [], "activity_department_ids": [],
    "activity_other_category_ids": [], "child_season_ids": [],
    "activity_keyword": "", "instructor_ids": [], "max_age": None,
    "custom_price_from": "", "custom_price_to": "",
}


_STABLE_COOKIE_KEYS = {"NEED_VERIFY_RECAPTCHA", "portlandparks_FullPageView", "portlandparks_locale"}


def _stable_cookies(raw: str) -> str:
    """Strip session/load-balancer cookies from a browser cookie string.

    Keeping only stable preference cookies lets the server start a fresh
    pagination session rather than restoring stale state from the browser.
    The requests.Session will collect the new session cookies automatically
    as they arrive in response headers.
    """
    parts = []
    for chunk in raw.split(";"):
        chunk = chunk.strip()
        key = chunk.split("=", 1)[0].strip()
        if key in _STABLE_COOKIE_KEYS:
            parts.append(chunk)
    return "; ".join(parts)


def _request_headers() -> dict:
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "Referer": f"{_BASE}/activity/search",
    }
    raw_cookie = os.environ.get("ACTIVENET_COOKIE", "").strip()
    if raw_cookie:
        stable = _stable_cookies(raw_cookie)
        print(
            f"  ACTIVENET_COOKIE present ({len(raw_cookie)} chars raw); "
            f"stable subset kept: {stable!r}"
        )
        if stable:
            headers["Cookie"] = stable
    return headers


# How many times to re-sweep all declared pages. The server's pagination is
# erratic -- confirmed via logging that ~90% of page requests just return
# the same first page's content regardless of which page was requested.
# Repeating the full sweep with a fresh session each time lands on different
# "lucky" pages, so merging dedup'd results across attempts improves
# coverage where a single sweep only surfaces a small, effectively random
# subset of the catalog.
_SWEEP_ATTEMPTS = 5


def _sweep_once(headers: dict, search_pattern: dict, seen_ids: set, all_items: list[dict]) -> None:
    """One pass through all declared pages, merging newly-seen items into all_items."""
    session = requests.Session()
    session.headers.update(headers)

    page = 1
    total_pages = 1
    while True:
        resp = session.post(
            f"{_BASE}/rest/activities/list",
            json={
                "activity_search_pattern": search_pattern,
                "activity_transfer_pattern": {},
                "pagination_info": {
                    "current_page": page,
                    "total_records_per_page": _PAGE_SIZE,
                },
            },
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()

        page_info = data.get("headers", {}).get("page_info", {})
        if page == 1:
            total_pages = page_info.get("total_page", 1)

        items = data.get("body", {}).get("activity_items", [])
        new_items = [i for i in items if i["id"] not in seen_ids]
        for i in new_items:
            seen_ids.add(i["id"])
        all_items.extend(new_items)

        if new_items:
            print(f"    page {page}/{total_pages}: {len(new_items)} new items")

        if page >= total_pages:
            break
        page += 1


def fetch_sessions(min_age_months: int, max_age_months: int) -> dict:
    """Fetch activity_items by sweeping all server pages, several times over.

    The ActiveNet API requires activity_select_param=2 to respect current_page
    at all. min_age_months / max_age_months are passed as-is to narrow the
    server-side result set; client-side filtering in matching.py is the
    authoritative filter.
    """
    headers = _request_headers()
    search_pattern = {
        **_BASE_SEARCH_PATTERN,
        "min_age": min_age_months if min_age_months else None,
        "max_age": max_age_months if max_age_months else None,
    }

    all_items: list[dict] = []
    seen_ids: set = set()

    for attempt in range(1, _SWEEP_ATTEMPTS + 1):
        before = len(all_items)
        _sweep_once(headers, search_pattern, seen_ids, all_items)
        print(f"  sweep {attempt}/{_SWEEP_ATTEMPTS}: {len(all_items) - before} new (total {len(all_items)})")

    return {"body": {"activity_items": all_items}}
