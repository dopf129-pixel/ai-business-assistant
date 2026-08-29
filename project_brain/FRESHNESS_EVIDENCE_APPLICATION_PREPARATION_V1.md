# Freshness Evidence Application Preparation v1 — v174–v178

Date: 2026-08-30

Architecture Review Required: **Yes** — safety-critical boundary immediately before any future evidence application/persistence stage.

## Goal

Continue the canonical freshness-evidence lifecycle after v172/v173 without inventing a write primitive. The repository currently has an explicit application-start handoff and permission audit, but no confirmed safe compare-and-set persistence contract for mutating a task draft. This batch therefore advances only to a deterministic application-preparation and execution-handoff boundary.

Workflow:

`v172 start handoff + v173 permission audit → v174 preparation eligibility → v175 preparation plan → v176 PREPARE/REJECT → v177 execution handoff → v178 audit`

No stage in this batch applies freshness evidence.

## v174 — preparation eligibility

`build_application_preparation_eligibility(handoff, permission_audit)` requires both canonical granted artifacts from the previous lifecycle.

It verifies:

- exact draft/SKU/request/approval/signal/eligibility/preview/authorization/permission lineage;
- canonical start-handoff and permission-audit IDs;
- exact equality of whitelisted handoff evidence and audited evidence;
- exact evidence counts;
- all persistence, mutation, application and execution flags remain false.

A successful result means only that preparation may be planned.

## v175 — deterministic preparation plan

`build_application_preparation_plan(eligibility)` converts the exact whitelisted evidence into a deterministic sorted `planned_fields` payload.

The plan is not a diff against persisted state and does not claim that any field has been written. It does not fabricate missing source timestamps and does not infer source freshness from observation timestamps.

## v176 — explicit PREPARE / REJECT

`build_application_preparation_decision(plan, decision)` accepts only `PREPARE` or `REJECT`.

`PREPARE` means that an exact preparation plan may cross into a separate future application-executor boundary. It does **not** mean APPLY, persist, mutate, recompute, or execute.

`APPLY` is deliberately rejected at this stage.

## v177 — application execution handoff

`build_application_execution_handoff(preparation_decision)` can be created only from a canonical `PREPARE` decision.

The artifact explicitly states `application_executor_required=True`, while preserving:

- `application_allowed=False`;
- `application_started=False`;
- `persistent=False`;
- `task_draft_mutated=False`;
- `product_decision_recomputed=False`;
- `product_decision_mutated=False`;
- `execution_allowed=False`;
- `execution_ready=False`;
- `executed=False`.

This is a handoff, not execution.

## v178 — preparation audit

`build_application_preparation_audit(...)` verifies the canonical v174–v177 lineage and evidence chain.

For an approved preparation, an exact matching execution handoff is required. For a rejected preparation, an execution handoff is forbidden.

The audit does not certify persistence or application success.

## Safety invariants

- only the six existing whitelisted freshness timestamp fields can cross the boundary;
- no source timestamp is fabricated;
- observation timestamps never prove source freshness;
- no evidence is persisted;
- no task draft is mutated;
- no Product Decision is recomputed or mutated;
- no Ozon call is made;
- no Action Executor is connected;
- no business execution permission is granted;
- no fallback invents missing identity/evidence;
- contradictory decisions, forged lineage and malformed evidence fail closed.

## Why actual application is not introduced here

A safe application stage needs an explicit target object plus stale-lineage/version protection (for example a compare-and-set write contract) and read-back verification. No such freshness-specific write primitive was confirmed in the current repository inspection. Introducing an ad-hoc JSON/data write would violate the architecture and safety boundary.

The next mutation-capable stage, if added later, must first define or reuse a versioned target/write contract and must remain separate from Product Decision/business execution authorization.

## Validation

Focused regression coverage:

`tests/test_product_task_freshness_evidence_application_preparation_v174_v178.py`

Latest pre-batch full-suite baseline supplied by the user: **982 passed** on `main` `11883f901d3bb344816735b834392a59185c0c81`.
