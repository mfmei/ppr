# Parks & Rec Finder

A better front end for filtering Portland Parks & Recreation classes by
kids' ages, schedule preferences, and (eventually) location — instead of
manually paging through the ActiveNet registration site.

## Status

Scaffolding only. Data model and matching logic are built against
**placeholder fixtures** — no live scraping wired up yet, and no
registration flow (out of MVP scope by design).

## Project layout

```
scraper/            Pulls and normalizes ActiveNet session data
  fetch.py            Replicates the real ActiveNet request (TODO: fill in
                       once the actual request is captured from DevTools)
  normalize.py         Raw ActiveNet JSON -> our normalized schema
  fixtures/            Saved sample responses used for testing, so the
                       rest of the app can be built/tested without
                       hitting the live site
data/
  schema.sql           SQLite schema (facilities, sessions)
backend/
  api.py               Thin FastAPI app exposing /search
  matching.py           Core filtering + tiered multi-child matching logic
frontend/
  index.html            Single-page registrant form + results view
tests/
  test_matching.py      Tests for the tiered matching logic against
                         fixture data
```

## MVP scope (confirmed)

- Stateless — no accounts, no saved profiles. A parent fills in the form
  each visit.
- Filters: registrant age(s), weekday/weekend preference, time-of-day
  preference. Address/distance is modeled in the schema but not wired
  into filtering yet.
- Only shows sessions that are in the future and not full.
- Multi-child search returns three ranked tiers:
  1. All selected kids in class at the same time (same facility, overlapping time)
  2. Kids in back-to-back classes (same facility, small gap between sessions)
  3. Partial matches — results per child where no combined slot exists,
     labeled with which child(ren) they fit
- No registration flow — results link out to the real ActiveNet
  registration page for the parent to complete signup themselves.

## Next steps

1. Capture the real ActiveNet request (DevTools Network tab while
   searching/filtering on the live site) and replace the fixture data
   in `scraper/fixtures/` with real captured responses.
2. Fill in `scraper/fetch.py` with the real request shape.
3. Validate `normalize.py` and `matching.py` still behave correctly
   against real data shapes (some fields may differ from the
   placeholder assumptions below — check nulls, date formats, and
   age units carefully).
4. Wire `backend/api.py`'s `/search` endpoint to real scraped +
   refreshed data (e.g., a nightly cron job populating `data/sessions.db`).
5. Build out `frontend/index.html` into the real UI.

## Running locally (once dependencies are set up)

```bash
pip install fastapi uvicorn pytest --break-system-packages
python -m pytest tests/
uvicorn backend.api:app --reload
```
