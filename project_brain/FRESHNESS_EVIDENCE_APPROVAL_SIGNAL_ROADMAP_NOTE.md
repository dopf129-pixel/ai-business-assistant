# Autonomous Assistant v21 — Freshness Evidence Approval Signal

Status: complete on feature branch pending merge.

This block adds an explicit evidence-only approval/rejection signal after the v20 approval-ready contract.

Completed:

- explicit `APPROVE` / `REJECT` decision normalization;
- approval context must contain approval/request/draft/SKU identity;
- only v20 approval-ready, freshness-validated contracts are accepted;
- forged contracts that already allow application are blocked;
- `APPROVED` does not enable evidence application;
- Product Decision execution remains disconnected.

Validation: targeted assistant-side pytest `7 passed in 0.04s`.

Next safe boundary: build an evidence-application eligibility contract that consumes only an `APPROVED` signal and still does not mutate state. It should verify signal/approval identity and re-check safety invariants before any future separate application workflow is considered.
