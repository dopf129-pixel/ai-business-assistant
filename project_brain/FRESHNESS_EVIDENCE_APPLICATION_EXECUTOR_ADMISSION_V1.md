# Freshness Evidence Application Executor Admission v1 — v179–v183

Date: 2026-08-30

Architecture Review Required: **Yes** — safety-critical boundary immediately before any future mutation adapter.

## Goal

Continue the canonical freshness-evidence application lifecycle after v174–v178 without inventing persistence. This batch introduces an explicit versioned target snapshot, exact deterministic diff, explicit executor authorization, and a handoff that requires a future stale-lineage-protected write adapter.

Workflow:

`v177 execution handoff + v178 preparation audit → v179 executor admission eligibility → v180 versioned target binding → v181 exact diff → v182 AUTHORIZE/REJECT → v183 write-adapter handoff + audit`

No function in this batch writes data.

## v179 — executor admission eligibility

`build_executor_admission_eligibility(execution_handoff, preparation_audit)` accepts only a canonical approved v177/v178 pair.

It validates exact identity lineage, canonical handoff/audit IDs, exact whitelisted evidence equality/counts, and all safety flags. Success only means that a versioned target snapshot may be bound.

## v180 — versioned target binding

`bind_executor_target_snapshot(eligibility, target_snapshot)` requires:

- exact `draft_id` and `sku`;
- non-empty `target_revision_id`;
- integer `target_version >= 1`;
- `target_values` containing only the six whitelisted freshness timestamp fields.

This is an immutable input snapshot contract. It is not a write and it does not claim the snapshot is current at later execution time.

## v181 — exact application diff

`build_executor_application_diff(target_binding)` compares exact bound current values against authorized freshness evidence.

The diff contains sorted `{field, before, after}` records and a deterministic `no_op` flag. Missing target fields are represented as `before=None`; no fallback/source timestamp is fabricated.

The diff is recomputable from the target binding and does not persist anything.

## v182 — explicit executor authorization

`build_executor_authorization_decision(diff, decision)` accepts only `AUTHORIZE` or `REJECT`.

`AUTHORIZE` means only that the exact diff may be handed to a separate future write adapter. It does not set `application_allowed`, start application, mutate a draft, recompute a Product Decision, enable business execution, or call Ozon.

`APPLY` is intentionally not accepted.

## v183 — write-adapter handoff and admission audit

`build_executor_write_handoff(authorization_decision)` is available only for an authorized non-no-op diff. It carries the exact target revision/version and proposed changes and explicitly requires:

- a stale-lineage check immediately before any future write;
- read-back verification after any future write.

The handoff itself still has all persistence/application/execution flags false.

`build_executor_admission_audit(...)` validates the complete v179–v183 chain. It recomputes the expected diff from the bound target snapshot rather than trusting the supplied diff. An authorized non-no-op chain requires an exact matching write handoff. Rejected and no-op chains must not have one.

## Safety invariants

- only the six existing freshness timestamp fields are admitted;
- no source timestamp is fabricated;
- observation timestamps do not prove source freshness;
- target identity must match exact draft/SKU;
- target revision and version are mandatory;
- diff is deterministic and recomputed during audit;
- authorization is not persistence;
- no evidence is persisted;
- no task draft is mutated;
- no Product Decision is recomputed or mutated;
- no Ozon call is made;
- no legacy Action Executor is connected;
- business execution remains disabled;
- future mutation must perform stale-lineage verification and read-back verification.

## Why mutation still stops here

The repository inspection still found no confirmed freshness-specific compare-and-set/versioned write primitive. v180–v183 define the minimum contract such a primitive must consume, but they deliberately do not implement an ad-hoc file/JSON write.

A future mutation-capable stage must re-read the target immediately before writing and prove the current revision/version still equals the bound values. If that proof fails or a write adapter is unavailable, it must fail closed.

## Validation

Focused regression coverage:

`tests/test_product_task_freshness_evidence_application_executor_admission_v179_v183.py`

Latest known full-suite baseline before v174–v183 remains **982 passed** on `main` `11883f901d3bb344816735b834392a59185c0c81`; connector-only work does not claim a later full-suite run.
