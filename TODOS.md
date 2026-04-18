# TODOS

Tracked deferred items from CEO and engineering reviews.

---

## P1 — Before public sharing / mobile users

### Mobile Bottom Nav Bar
**What:** Below 768px, hide the fixed sidebar entirely and render a bottom nav bar with 4 icon-only items (Investment Memo, Earnings, Arena, Library). The memo output grid collapses to single column. Sidebar toggle is hidden on mobile.
**Why:** The sidebar at 60px–240px on a 375px screen leaves unusable content area. Any user accessing via mobile link (e.g., a shared `/m/:slug` memo) hits a broken layout.
**Pros:** Correct mobile experience, unblocks shared memo URLs working on phone.
**Cons:** New component, ~2hr implementation. Touch targets need 44px minimum (current sidebar toggle is 22px).
**Context:** Pass 6 of design review identified this as the weakest area (3/10 → 7/10 after spec). Bottom nav is the right pattern for a 4-item tool app. Also need: memo grid `gridTemplateColumns: '1fr'` at ≤768px.
**Effort:** ~2 hr CC (human: ~4 hrs)
**Priority:** P1 (before sharing `/m/:slug` links publicly)
**Depends on:** Nothing — standalone CSS + new component

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

### Partial Memo Warning Banner
**What:** When the memo results contain `Unavailable` sections (some agents timed out), show a yellow info banner at the top of the memo: "Analysis incomplete — one or more agents timed out. Results may be partial."
**Why:** A user who sees blank sections has no signal whether the product failed or intentionally returned nothing. Ambiguity erodes trust.
**Pros:** 10-line change. Restores trust for edge cases.
**Cons:** Adds conditional rendering logic. Need to define "incomplete" threshold (e.g., ≥1 section null).
**Context:** Add `isPartial` computed from `memo.thesis == null || memo.bear_case == null || memo.what_would_make_this_wrong == null`. Render banner above the verdict strip.
**Effort:** ~15 min CC (human: ~30 min)
**Priority:** P2
**Depends on:** Nothing

### Save Success Toast / Confirmation
**What:** After a memo is saved, the button label changes to "Saved" — but there's no visual confirmation that the action completed. Add a `ToastNotification` (component already exists in `frontend/src/components/ToastNotification.tsx`) with "Saved to Library" message.
**Why:** Button label change alone is too subtle. Users may re-click the save button unsure if it worked.
**Pros:** Reuses existing `ToastNotification` component. 5-line change.
**Cons:** None significant.
**Context:** Trigger `ToastNotification` in `handleSave()` after `setShareSlug(share_slug)`.
**Effort:** ~10 min CC
**Priority:** P2
**Depends on:** Nothing

### Arena + Earnings Mobile Layout
**What:** ArenaPage has multi-agent debate cards and streaming signal rows that assume wide viewport. EarningsPage has horizontal charts, peer comparison tables, and quarterly trend grids. Both break at 375px.
**Why:** With Earnings and Arena now in the nav (Pass 1 fix), users can navigate there from mobile and hit broken layouts.
**Context:** Arena: stack agent cards vertically, reduce gap from 16px to 8px at ≤768px. Earnings: make chart containers `overflow-x: auto`, stack peer comparison columns. Implement after mobile nav bar (P1 above) is done so the bottom nav is in place first.
**Effort:** ~1.5 hr CC (human: ~3 hrs)
**Priority:** P2
**Depends on:** Mobile Bottom Nav Bar (P1 above) — the bottom nav must exist before mobile layout polish makes sense.

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

## P3 — Design system cleanup (non-blocking)

### Color Token Rollout — Non-Memo Pages
**What:** The Phronesis design tokens in `index.css` (`--teal-500`, `--ink-900`, etc.) are defined but not yet used in the Earnings, Chat, Arena, or Library pages. Those pages still use hardcoded hex values (`#10B981`, `#1A1A1A`, `#6B7280`).
**Why:** Once tokens are in use everywhere, a brand change or dark mode theme becomes a 1-line edit in `index.css` instead of a grep-and-replace across 15+ files.
**Context:** The InvestmentMemoPage is already using inline styles with the canonical values — these should be migrated to CSS variables. A token migration script would grep for the hex values and replace them with `var(--token)`.
**Effort:** ~2 hr CC (human: ~4 hrs)
**Priority:** P3 (before dark mode / Phase 3 theming)
**Depends on:** Nothing

### Inter Font Removal — Earnings + Chat CSS
**What:** The Earnings page, Chat page, and supporting CSS in `index.css` use `Inter` font family throughout (`.earnings-page`, `.home-page`, `.prose-gray`, `.ft-table`, etc.). The font decision from design review (April 2026) is to use IBM Plex Sans as the sole body font.
**Why:** Four fonts (`IBM Plex Sans`, `IBM Plex Mono`, `Instrument Serif`, `Inter`) with no documented separation creates visual inconsistency and unnecessary bundle weight.
**Context:** InvestmentMemoPage already migrated. Earnings and Chat pages need the same. The font import for Inter is still in `index.css` line 2. Migration is mechanical: replace `font-family: 'Inter'` with `font-family: 'IBM Plex Sans'` and remove the Google Fonts import.
**Effort:** ~1 hr CC (human: ~2 hrs)
**Priority:** P3
**Depends on:** Nothing — safe to do anytime

## P3 — Code quality (non-blocking)

### Frontend Test Framework (Vitest + React Testing Library)
**What:** The frontend has 0 tests. Add Vitest + React Testing Library. First tests to write: (1) post-save nudge resets all 8 state fields, (2) NEW ANALYSIS button resets all 8 state fields, (3) ghost memo shows when idle + no result, hides when analyzing.
**Why:** No frontend tests means every design refactor is unverified. The state reset paths are the most likely to regress silently.
**Context:** `package.json` has no test dependencies. Add: `vitest`, `@testing-library/react`, `@testing-library/user-event`, `@vitejs/plugin-react`, `jsdom`. Write `vite.config.ts` test config. First test file: `src/pages/InvestmentMemoPage.test.tsx`.
**Effort:** ~1 hr CC to set up framework + first 3 tests (human: ~4 hrs)
**Priority:** P3
**Depends on:** Nothing

### Split InvestmentMemoPage.tsx into Components
**What:** `frontend/src/pages/InvestmentMemoPage.tsx` is 930 lines with `AgentCardRow`, `MemoSection`, `ProgressBar`, `Unavailable`, and `VerdictBanner` defined inline.
**Why:** Single large file is harder to navigate and test. Component splitting enables independent testing of each sub-component.
**Pros:** Cleaner file structure, testable sub-components.
**Cons:** Minor refactor risk (no logic changes, just file moves).
**Context:** Split into `frontend/src/components/memo/AgentCardRow.tsx`, `MemoSection.tsx`, `VerdictBanner.tsx`. The page file becomes pure layout + state (~300 lines).
**Effort:** ~30 min CC (human: ~1 hr)
**Priority:** P3
**Depends on:** Nothing — safe to do anytime
