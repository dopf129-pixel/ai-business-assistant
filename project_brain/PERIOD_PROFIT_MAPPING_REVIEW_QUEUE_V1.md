# Period Profit Mapping Review Queue v1 — v164–v168

Date: 2026-08-29

Architecture Review Required: **Yes** — this batch adds a safety-critical operational queue/readiness layer over mapping review incidents.

## Goal

After v159–v163, reopened mapping reviews have deterministic audit receipts and human-only incident handoffs. This batch turns those validated incidents into a read-only operational queue so humans can see what requires attention first without granting any mapping mutation permission.

Workflow:

`v163 audit + v162 handoff → v164 incident intake → v165 deterministic priority → v166 queue item → v167 queue snapshot → v168 readiness summary`

## v164 — incident intake

An intake requires both:

- `PERIOD_PROFIT_MAPPING_REVIEW_MONITORING_AUDIT_READY` with an incident detected and handoff ready;
- `PERIOD_PROFIT_MAPPING_REVIEW_MONITORING_INCIDENT_HANDOFF_READY`.

Scope, revision ID, mapping ID, and normalized incident categories must match exactly. Lineage identifiers must be non-empty strings. Any mutation permission in the handoff fails closed.

## v165 — deterministic operational priority

Priority is derived only from already-validated explicit incident categories:

- `CATALOG_EVIDENCE_UNAVAILABLE` → `P0`;
- `CATALOG_DRIFT` → `P1`;
- `FRESHNESS` → `P2`;
- other allowed explicit review categories → `P3`.

This is operational ordering only. It is not a mapping decision, financial severity estimate, or authorization.

No operation names, fuzzy matching, substring matching, semantic similarity, money values, or inferred business impact participate in priority.

## v166 — canonical queue item

A queue item binds one exact `(scope, revision_id, mapping_id)` lineage to one pending human re-review item.

The queue key is deterministic:

`scope|revision_id|mapping_id`

The function recomputes the expected priority from intake categories and rejects a forged or inconsistent priority artifact.

The only queue state introduced here is `PENDING_HUMAN_REREVIEW`.

## v167 — queue snapshot

A snapshot accepts only canonical pending queue items. It validates:

- exact string lineage;
- deterministic queue key;
- allowed incident categories;
- priority recomputed from categories;
- all mapping/Ozon/profit mutation permissions remain disabled;
- no duplicate queue key.

Items are sorted by priority and then exact lineage. The snapshot is read-only and is not persisted by this module.

## v168 — readiness summary

The readiness summary recomputes counts from the snapshot instead of trusting supplied aggregate values.

It exposes only:

- whether the queue is empty;
- pending human re-review count;
- highest pending priority;
- per-priority counts;
- whether human action is required.

`operationally_clear=True` means only that this queue currently contains no pending mapping re-review incidents. It does not authorize any action and does not make a statement about overall business or financial readiness.

## Safety invariants

Unchanged:

- exact mapping evidence only;
- no automatic mapping classification;
- no fuzzy/substring mapping;
- no automatic remap;
- no mapping build authorization;
- no registry save;
- no automatic activation;
- no Ozon mutation;
- no profit adjustment or fee double counting;
- return mapping evidence still does not imply full returns economics;
- Product Decisions execution remains manual;
- every queue artifact has `executed=False`.

## Tests

- `tests/test_period_profit_mapping_review_queue_batch_v164_v168.py`
- `tests/test_period_profit_mapping_review_queue_fail_closed.py`

Coverage includes exact audit/handoff binding, mutation-permission rejection, deterministic priority, stable queue keys, queue ordering, duplicate detection, readiness recomputation, forged priority rejection, unknown categories, strict string lineage, and tampered aggregate counts.