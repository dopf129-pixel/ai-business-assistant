# Freshness Evidence Application Permission v1 — v169–v173

Date: 2026-08-29

Architecture Review Required: **Yes** — safety-critical authorization/permission boundary.

## Goal

Continue the explicit freshness-evidence application lifecycle after the existing authorization signal without applying evidence, persisting state, mutating a task draft or Product Decision, enabling execution, or calling Ozon.

Workflow:

`v25 authorization signal → v169 permission eligibility → v170 permission review → v171 PERMIT/REJECT → v172 start handoff → v173 audit`

## v169 — permission eligibility

Consumes only a canonical `APPLICATION_AUTHORIZATION_GRANTED` signal with exact identity chain and whitelisted freshness evidence. A successful result means only that a separate application-permission review may occur.

`permission_eligible=True` does not mean application has started or that business execution is allowed.

## v170 — permission review

Creates a deterministic read-only review artifact. It preserves exact draft/SKU/request/approval/signal/preview/authorization identity and exact evidence.

No permission is granted at this stage.

## v171 — explicit permission decision

Only `PERMIT` or `REJECT` is accepted.

`PERMIT` grants permission for a future evidence-application stage to be considered. It still keeps:

- `application_allowed=False`;
- `application_started=False`;
- `persistent=False`;
- `task_draft_mutated=False`;
- `product_decision_mutated=False`;
- `execution_allowed=False`;
- `execution_ready=False`;
- `executed=False`.

`REJECT` creates no handoff.

## v172 — application start handoff

A handoff can be built only from a canonical `PERMIT` decision. It carries exact whitelisted evidence to a future stage but does not apply or persist it.

The handoff is not application execution and is not business-action execution.

## v173 — permission audit

Creates a deterministic audit receipt over eligibility, review, decision, and—when permission is granted—the exact matching handoff.

Granted permission without a matching handoff fails closed. Rejected permission with a handoff also fails closed.

## Safety invariants

- no source timestamp is fabricated;
- observation timestamps do not prove source freshness;
- no evidence is persisted;
- no task draft is mutated;
- no Product Decision is recomputed or mutated;
- no Ozon call is made;
- no legacy Action Executor is connected;
- no business execution permission is granted;
- all application-start and execution flags remain false.

## Validation

Focused regression coverage: `tests/test_product_task_freshness_evidence_application_permission_v169_v173.py`.

Full repository pytest is not claimed in the current connector-only environment.
