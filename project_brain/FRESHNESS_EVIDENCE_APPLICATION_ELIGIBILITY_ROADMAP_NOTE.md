# Autonomous Assistant v22 — Freshness Evidence Application Eligibility

Status: complete on feature branch pending merge.

This block adds a read-only eligibility boundary after the v21 explicit approval signal.

Completed:

- v20 approval contract and v21 approval signal identity must match exactly;
- `approval_id` and `signal_id` are bound deterministically to the same draft context;
- only `APPROVED` / `APPROVE` signals can become eligible;
- contract and signal safety invariants are re-validated independently;
- approved evidence is re-whitelisted on both sides and must match exactly;
- `application_eligible=True` never implies `application_allowed=True`;
- evidence application is not started;
- Product Decision execution remains disconnected.

Validation: targeted assistant-side pytest `10 passed in 0.05s`.

Next safe boundary: define an evidence application preview that applies eligible evidence only to an in-memory copy of the draft and re-runs freshness/readiness checks. It must not persist evidence or enable Product Decision execution.
