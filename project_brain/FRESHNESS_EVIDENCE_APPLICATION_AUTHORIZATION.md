# Freshness Evidence Application Authorization v1

Date: 2026-08-29

## Goal

Create an authorization-ready boundary from a successful v23 application preview without granting authorization, applying evidence, persisting state, mutating Product Decisions, or enabling business execution.

## Contract

`build_freshness_evidence_application_authorization(application_preview)` consumes the v23 read-only preview.

It returns `APPLICATION_AUTHORIZATION_REQUIRED` only when:

- preview status is `APPLICATION_PREVIEW_READY`;
- `preview_only=True`;
- `application_allowed=False` and `application_started=False`;
- persistence, Product Decision mutation, task-draft mutation, and execution flags remain false;
- preview identity chain is complete and valid;
- applied evidence contains only canonical freshness evidence fields;
- `after_freshness.status=FRESH`;
- `after_readiness.review_ready=True` and `review_status=READY_FOR_REVIEW`;
- nested freshness/readiness results also keep execution disabled.

## Identity bindings

The contract requires:

- `request_id == refresh:<draft_id>`;
- `approval_id == evidence-approval:<draft_id>`;
- `signal_id == evidence-signal:<approval_id>`;
- `eligibility_id == evidence-eligibility:<signal_id>`;
- `preview_id == evidence-application-preview:<eligibility_id>`.

## Authorization semantics

A successful result means only that the evidence may be presented for a separate explicit authorization decision.

It returns:

- `authorization_ready=True`;
- `authorization_required=True`;
- `authorization_granted=False`;
- `application_allowed=False`;
- `application_started=False`.

The evidence payload is named `authorization_evidence`, not `authorized_evidence`, because no authorization has been granted yet.

## Safety invariants

- no persistence;
- no Ozon calls;
- no task-draft mutation;
- no Product Decision recomputation or mutation;
- no legacy Action Executor connection;
- `source_freshness_proven=False` at this boundary;
- `execution_allowed=False`;
- `execution_ready=False`;
- `executed=False`.

## Validation

Focused tests: `tests/test_product_task_freshness_evidence_application_authorization.py`.

Targeted assistant-side pytest after semantic hardening: `10 passed in 0.05s`.

The full repository suite was intentionally not rerun for this isolated additive contract.
