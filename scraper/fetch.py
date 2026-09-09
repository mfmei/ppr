"""
Fetches activity listings from the Portland Parks & Rec ActiveNet backend.

Endpoint and request shape captured from DevTools (Network > Fetch/XHR) while
browsing https://anc.apm.activecommunities.com/portlandparks/activity/landing,
then confirmed against the site's own JS bundle (app.index.*.js): pagination
is NOT part of the JSON body. The client library (createAPI/httpClient in the
bundle) takes the `page_info` object callers pass and moves it onto the
request as an HTTP header named "page_info", JSON-stringified -- e.g.
    page_info: {"page_number":2,"total_records_per_page":20}
A `pagination_info` (or any other) field inside the JSON body is silently
ignored by the server, which is why earlier attempts that put pagination
there always got page 1 back regardless of what was requested.

With page_info sent correctly as a header, current_page is respected exactly
and requires no authentication at all -- a plain anonymous session (just
GET the search page first to pick up cookies, then POST) pages through the
full catalog deterministically.

Real captured response shape: scraper/fixtures/real_api_sample.json
"""
import requests

_BASE = "https://anc.apm.activecommunities.com/portlandparks"
_PAGE_SIZE = 20

_SEARCH_PATTERN = {
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


def _page_info_header(page: int) -> dict:
    import json
    return {
        "page_info": json.dumps({
            "page_number": page,
            "total_records_per_page": _PAGE_SIZE,
            "order_by": "Name",
            "order_option": "ASC",
        })
    }


def fetch_sessions(min_age_months: int, max_age_months: int) -> dict:
    """Fetch all activity_items by paging through the full catalog.

    min_age_months / max_age_months are passed as-is to narrow the
    server-side result set; client-side filtering in matching.py is the
    authoritative filter.
    """
    session = requests.Session()
    session.headers.update({
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "Referer": f"{_BASE}/activity/search",
    })
    session.get(f"{_BASE}/activity/search", timeout=10)

    search_pattern = {
        **_SEARCH_PATTERN,
        "min_age": min_age_months if min_age_months else None,
        "max_age": max_age_months if max_age_months else None,
    }

    all_items: list[dict] = []
    page = 1
    total_pages = 1
    while page <= total_pages:
        resp = session.post(
            f"{_BASE}/rest/activities/list?locale=en-US",
            headers=_page_info_header(page),
            json={
                "activity_search_pattern": search_pattern,
                "activity_transfer_pattern": {},
            },
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()

        page_info = data.get("headers", {}).get("page_info", {})
        if page == 1:
            total_pages = page_info.get("total_page", 1)
            print(f"  {page_info.get('total_records', '?')} total records across {total_pages} pages")

        items = data.get("body", {}).get("activity_items", [])
        all_items.extend(items)
        print(f"    page {page}/{total_pages}: {len(items)} items")

        page += 1

    return {"body": {"activity_items": all_items}}
