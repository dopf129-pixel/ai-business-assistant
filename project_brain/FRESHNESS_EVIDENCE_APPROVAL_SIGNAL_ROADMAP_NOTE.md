# Autonomous Assistant v21 — Freshness Evidence Approval Signal

Status: complete on feature branch pending merge.

This block adds an explicit evidence-only approval/rejection signal after the v20 approval-ready contract.

Completed:

- explicit `APPROVE` / `REJECT` decision normalization;
- approval context must contain approval/request/draft/SKU identity;
- `approval_id` must be bound to the same draft;
- only v20 approval-ready, freshness-validated contracts are accepted;
- validated evidence is re-whitelisted at the signal boundary;
- forged contracts with prior approval or application permission are blocked;
- `APPROVED` does not enable evidence application;
- Product Decision execution remains disconnected.

Validation: targeted assistant-side pytest `10 passed in 0.05s`.

Next safe boundary: build an evidence-application eligibility contract that consumes only an `APPROVED` signal and still does not mutate state. It should verify signal/approval identity, exact validated evidence continuity, and all safety invariants before any future separate application workflow is considered.
