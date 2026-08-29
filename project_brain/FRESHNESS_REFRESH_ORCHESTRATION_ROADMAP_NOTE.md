# Autonomous Assistant v17 — Roadmap Note

Date: 2026-08-29

Completed:

- [x] Safe refresh request draft (v15)
- [x] Read-only refresh capability contract (v16)
- [x] Read-only refresh orchestration (v17)

The system can now turn freshness guidance into a non-persistent refresh request, validate that every target maps to an allowed read-only provider path, and execute those reads through injected providers.

Important boundary:

- refresh reads do not recompute Product Decisions;
- refresh reads do not mutate task drafts;
- successful reads do not prove source freshness without real `*_source_recorded_at` evidence;
- Product Decision execution remains disconnected.

Next:

Normalize read-only refresh results into an explicit evidence-update candidate contract. The candidate may carry newly observed values and any real upstream source timestamps if present, but must not overwrite a Product Decision or task draft automatically.
