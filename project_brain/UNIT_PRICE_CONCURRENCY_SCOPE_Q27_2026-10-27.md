# Unit-price concurrency and scope — Q27 acceptance

Date: 2026-10-27
Stage: Q27 — concurrency and scope
Status: VERIFIED

## Confirmed race and fix

An observation collector can take long enough for another user action to open a new input form. Previously, collection cleanup removed pending state by tenant/store key alone, which could delete the newer form. Pending actions now receive an internal token. Completion/error cleanup removes the pending entry only when its token still matches; observation-start completion similarly replaces only the action it began from. The token is process-local and is not persisted or exported.

The same conditional cleanup guards note saves and observation-start failures/completions. A duplicate tariff-confirm callback is claimed by changing its draft state to `confirming`; a concurrent replay is rejected before a second repository write.

## Evidence

- `test_late_collection_completion_preserves_newer_pending_note` blocks a synthetic source call, opens a note form while collection is running, completes the source call, then confirms that the note form survives and its value is saved.
- `test_parallel_tariff_save_callback_has_one_writer_and_keeps_retry_safe` blocks the first repository create call, replays the confirmation, and verifies a stale response plus exactly one row.
- Existing tests cover wrong-store callbacks, old revisions/tickets, late batch results, scenario identity/version checks, one-winner repository CAS, scoped durable reads and bounded-cache behavior.
- Linked Windows/Python 3.12.10 Q16–Q27 profile: **460 passed across 31 targets in 11.03s**.

## Scope and limitations

All sources were fake or local SQLite under temporary test paths. No live API, owner data, real bot or production store was accessed. Q27 does not alter DB schema or saved payload contracts. Full repository pytest and exact-head Windows/Linux/Docker CI remain Q33–Q35.
