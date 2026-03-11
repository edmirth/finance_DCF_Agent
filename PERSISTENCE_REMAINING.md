# Persistence Layer — Remaining Work
**Date:** 2026-02-26 | **Commit:** `4f2029a`

What was shipped in this session is working end-to-end (DB init, REST endpoints, chat persistence, library UI, watchlist chips, session restore). The items below are either polish, edge cases, or future phases called out in the PRD.

---

## 1. Testing

| Item | Detail |
|---|---|
| Backend integration tests | Write `pytest` tests for all new endpoints (`/sessions`, `/analyses`, `/watchlists`). Fixture: in-memory SQLite DB via `AsyncSessionLocal`. |
| Session restore end-to-end | Manual test: send a chat → restart backend → refresh browser with `?session=<id>` → messages should appear. |
| Watchlist persistence | Manual test: add ticker → restart backend → chip still shows. |
| Library search | Test LIKE query with 1000+ rows stays < 200ms. |
| Export download | Confirm `.md` file downloads with correct `Content-Disposition` header across browsers. |

---

## 2. UI Polish

### 2.1 Watchlist chip bar — remove ticker
Currently you can add tickers but not remove them from the chip bar. Need:
- Long-press or right-click on a chip → remove option, **or**
- An ✕ icon on hover (like the tag editor in LibraryPage already does)
- Call `removeTickerFromWatchlist(watchlistId, ticker)` from `api.ts`

### 2.2 Library page — loading skeleton
When `loading === true`, show skeleton cards instead of just "Loading…" text.

### 2.3 Library page — tag filter pills refresh after tag add
After adding a tag to a card, the filter pill bar at the top doesn't update until the next full page load. Fix: re-derive `allTags` from the live `analyses` state (already done) — but the filter bar only renders tags from the initial fetch. Should work already; confirm in browser.

### 2.4 Toast position with sidebar
The `ToastNotification` is fixed at `bottom-6 right-6`. Looks good when sidebar is collapsed (80px). If sidebar is expanded (320px), the toast doesn't overlap — fine. No change needed unless the layout changes.

### 2.5 Sidebar session title truncation
Long session titles (> ~20 chars) truncate with CSS `truncate`. Works but the `title` attribute on the `<p>` should show the full title on hover — already implemented via `title={session.title}`. Verify in browser.

### 2.6 Library page — pagination
Currently fetches all analyses (`GET /analyses` with no `limit`). For large libraries (100+ records), add cursor pagination or infinite scroll.

---

## 3. Backend Gaps

### 3.1 `utcnow()` deprecation
`datetime.utcnow()` is deprecated in Python 3.12+. Replace with `datetime.now(timezone.utc)` throughout `api_server.py` and `models.py`. Non-blocking for Python 3.9 (current runtime).

```python
# Before
from datetime import datetime
datetime.utcnow()

# After
from datetime import datetime, timezone
datetime.now(timezone.utc)
```

### 3.2 `@app.on_event("startup")` deprecation
FastAPI recommends the `lifespan` context manager over `@app.on_event`. Non-breaking for current FastAPI 0.104.1.

```python
# Replace on_event with lifespan
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield

app = FastAPI(lifespan=lifespan, ...)
```

### 3.3 Analysis dedup
If a user sends the same ticker twice in a session, two analysis rows are inserted. Consider upserting on `(session_id, ticker, agent_type)` within the same day, or just let duplicates accumulate (library search handles it fine).

### 3.4 Session title update
The session title is set from the **first** user message and never updated. For follow-up sessions restored from the sidebar, the title stays accurate. No change needed unless you want auto-titling via an LLM call (future feature).

### 3.5 `GET /analyses` — server-side pagination
```
GET /analyses?limit=20&offset=0
```
Add `limit` + `offset` query params and return `total_count` in response header for frontend pagination.

---

## 4. Phase 2 — PostgreSQL Upgrade (future)

When ready to move to Postgres:

```bash
# 1. Set env var
export DATABASE_URL="postgresql+asyncpg://user:pass@host/dbname"

# 2. Install asyncpg
pip install asyncpg

# 3. Add FTS migration (optional — better search)
ALTER TABLE analyses ADD COLUMN search_vector tsvector;
UPDATE analyses SET search_vector = to_tsvector('english', title || ' ' || content);
CREATE INDEX analyses_search_idx ON analyses USING GIN (search_vector);

# 4. Update list_analyses endpoint to use tsvector when on Postgres
```

No code changes needed for the basic swap — the SQLAlchemy layer handles dialect differences automatically.

---

## 5. Phase 3 — User Authentication (future)

The schema is auth-ready: every table has a nullable `user_id FK → users`. Steps when adding auth:

1. Create `users` table (already defined in PRD data model — not yet created in `models.py`)
2. Add Supabase Auth or JWT middleware
3. Make `user_id` NOT NULL via migration
4. Filter all queries: `WHERE user_id = current_user_id`

---

## 6. Known Limitations (ship as-is)

| Limitation | Impact | Mitigation |
|---|---|---|
| No analysis dedup | Library accumulates duplicates for repeated queries | Low — search still works; user can delete |
| Watchlist limited to 1 list ("My Watchlist") | Multi-list UI not built | API supports multiple lists; UI is single-list for now |
| Session restore loses thinking steps | Thinking steps are stored as JSON but not re-rendered on restore | Low — conversation text is fully restored |
| `finance_agent.db` in project root | Could be committed accidentally | Add `finance_agent.db` to `.gitignore` |

> **Action:** Add `finance_agent.db` to `.gitignore` to prevent committing the local DB.

---

## Quick Wins (< 30 min each)

1. **Add `finance_agent.db` to `.gitignore`** — 2 min
2. **Watchlist chip hover ✕ to remove** — 20 min (update `Chat.tsx` WatchlistBar + add `removeTickerFromWatchlist` call)
3. **Library loading skeleton** — 15 min (add 3 skeleton `<div>` placeholders)
4. **Replace `utcnow()` with timezone-aware equivalent** — 10 min (find & replace in 2 files)
