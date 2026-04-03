# TODOS

Tracked deferred items from CEO and engineering reviews.

---

## P2 — After Phase 2 auth/accounts

### Thesis Outcome Tracking ("Did this play out?")
**What:** When a saved memo is >90 days old, show a "3-month review" button. User answers: (1) did the thesis play out? (2) is the position still open? Memo is marked reviewed.
**Why:** The feedback loop the entire market is missing. Transforms a one-shot research tool into a learning system. Evidence of actual prediction accuracy builds trust and retention.
**Pros:** Unique feature, no competitor does this. First-party outcome data is extremely valuable for Phase 3 paywall.
**Cons:** Requires auth/email for reminders to be useful. Without email, user must remember to return. Low engagement without prompts.
**Context:** Button version can be built without auth — captures data if users return organically. Email reminders require Phase 2 accounts. Start with the button in Phase 2, add email in Phase 3.
**Effort:** ~1 day CC (human: ~1 week)
**Priority:** P2
**Depends on:** Phase 2 accounts (email signup + `user_id` in `analyses` table)

### Replace In-Memory Rate Limit Counter with Redis/DB
**What:** Phase 1 `/memo/stream` rate limiting uses an in-memory global daily counter. This resets on server restart and breaks on multi-worker deployments.
**Why:** Moving to multi-worker Uvicorn (Phase 2 for reliability) silently breaks the global cap. An unchecked endpoint can burn $35+ in API costs from a single bad actor.
**Pros:** Production-grade rate limiting, survives restarts and horizontal scale.
**Cons:** Requires Redis or a `rate_limit_events` DB table. Adds a dependency.
**Context:** Redis `INCR` + TTL is 20 lines. The DB table approach reuses existing SQLite/Postgres. Do this before any public URL sharing beyond Phase 1.
**Effort:** ~1 hr CC (human: ~2 hrs)
**Priority:** P2 (before Phase 2 public launch)
**Depends on:** Phase 2 deployment architecture decision (single server vs. multi-worker)

---

## P3 — Code quality (non-blocking)

### Split InvestmentMemoPage.tsx into Components
**What:** `frontend/src/pages/InvestmentMemoPage.tsx` is 930 lines with `AgentCardRow`, `MemoSection`, `ProgressBar`, `Unavailable`, and `VerdictBanner` defined inline.
**Why:** Single large file is harder to navigate and test. Component splitting enables independent testing of each sub-component.
**Pros:** Cleaner file structure, testable sub-components.
**Cons:** Minor refactor risk (no logic changes, just file moves).
**Context:** Split into `frontend/src/components/memo/AgentCardRow.tsx`, `MemoSection.tsx`, `VerdictBanner.tsx`. The page file becomes pure layout + state (~300 lines).
**Effort:** ~30 min CC (human: ~1 hr)
**Priority:** P3
**Depends on:** Nothing — safe to do anytime
