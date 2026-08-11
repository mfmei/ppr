"""
Fetches activity listings from the Portland Parks & Rec ActiveNet backend.

Endpoint and request shape captured from DevTools (Network > Fetch/XHR) while
browsing https://anc.apm.activecommunities.com/portlandparks/activity/landing.

WITHOUT auth cookies the API ignores current_page and always returns the same
first ~20 activities. WITH cookies (copied from a logged-in browser session)
full pagination works and you get the complete catalog.

To enable full pagination:
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


def fetch_sessions(min_age_months: int, max_age_months: int) -> dict:
    """Fetch activity_items by sweeping all server pages.

    The ActiveNet API requires activity_select_param=2 to respect current_page.
    Even so, the server's internal pagination is stateful and erratic — it
    cycles through different internal pages across successive requests in the
    same session, so sweeping all declared pages surfaces most unique buckets.
    Dedup by ID ensures no duplicates in the output.

    min_age_months / max_age_months are passed as-is to narrow the server-side
    result set; client-side filtering in matching.py is the authoritative filter.
    """
    headers = _request_headers()
    search_pattern = {
        **_BASE_SEARCH_PATTERN,
        "min_age": min_age_months if min_age_months else None,
        "max_age": max_age_months if max_age_months else None,
    }

    all_items: list[dict] = []
    seen_ids: set = set()
    total_pages: int | None = None
    session = requests.Session()
    session.headers.update(headers)

    page = 1
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
        if total_pages is None:
            total_pages = page_info.get("total_page", 1)

        items = data.get("body", {}).get("activity_items", [])
        new_items = [i for i in items if i["id"] not in seen_ids]
        for i in new_items:
            seen_ids.add(i["id"])
        all_items.extend(new_items)

        print(
            f"  page {page}/{total_pages}: {len(items)} items "
            f"({len(new_items)} new), total_records={page_info.get('total_records')}"
        )

        if page >= total_pages:
            break
        page += 1

    return {"body": {"activity_items": all_items}}
