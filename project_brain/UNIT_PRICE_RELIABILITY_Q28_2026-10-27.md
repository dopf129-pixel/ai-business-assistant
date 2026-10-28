# Unit-price limits and failure recovery — Q28 acceptance

Date: 2026-10-27
Stage: Q28 — limits and failure recovery
Status: VERIFIED

## Behavior verified

- The observation collector reuses the shared operation trace, obeys the tighter parent time/request budget, and includes retry attempts in the bounded HTTP attempt count.
- Cancelled work makes no new source requests. Time-budget expiry stops subsequent days and optional Performance collection. Received finance days remain visible as a partial source; missing days are never zero-filled.
- A synthetic 429 does not cause an automatic retry or a persisted result revision. The owner can explicitly press the existing collect action again; the recovered attempt creates one new result revision.
- Existing repository and serializer checks continue to enforce per-store/result quotas, transactional rollback, row/column/byte limits, allowlisted fields and spreadsheet-safe CSV output.

## Evidence

- Focused new regressions: cancellation, time-budget expiry and explicit retry — **3 passed**.
- Linked Windows/Python 3.12.10 Q16–Q28 profile: **474 passed across 32 targets in 11.15s**.
- Q28 required test changes only; no production implementation change was needed.

## Scope and limitations

Fake sources, fake clocks and temporary local repository files only. No live API, `.env`, owner database or real bot was used. Full repository pytest and exact-head Windows/Linux/Docker CI remain Q33–Q35.
