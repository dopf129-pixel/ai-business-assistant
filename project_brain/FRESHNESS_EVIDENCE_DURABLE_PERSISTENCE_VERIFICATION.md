# Freshness Evidence Durable Persistence Verification v1

## Goal

Independently verify that v30 durable draft persistence actually stored the exact allowlisted freshness evidence expected by the v28 readiness contract.

## Design

`ProductTaskFreshnessEvidenceDraftPersistenceVerificationService` receives the existing draft storage through constructor injection. It accepts readiness evidence plus the v30 persistence result, requires confirmed persistence and exact `draft_id + sku` identity, reloads storage, requires exactly one matching draft, and compares persisted freshness evidence field-by-field.

## Safety

- verification is read-only;
- no storage save is called;
- only the six allowlisted freshness evidence fields are compared;
- missing or ambiguous drafts are blocked;
- unsafe or count-mismatched evidence is blocked;
- persisted evidence mismatch is reported explicitly;
- Product Decision recomputation/mutation remains disabled;
- Ozon mutation and legacy Action Executor are not invoked;
- `execution_allowed`, `execution_ready`, and `executed` remain false.

Targeted exact minimal-checkout pytest: `9 passed in 0.04s`.
