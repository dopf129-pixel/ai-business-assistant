# Decision 047 — Return COGS Profit Application Requires Exact-Once Commit Evidence

Status: Accepted

Date: 2026-09-04

## Decision

Return COGS profit-application eligibility is not itself application and is not sufficient to change Period Profit.

Before any future application may occur, the exact accounting-recognition history version must have at most one durable application commit. The commit must be append-only, first-writer-wins, and bind the exact Return COGS identity, accounting date, RUB amount and exact application-authorization history version.

A later attempt for the same recognition version must resolve to the already-existing commit rather than create another monetary event.

## Required invariants

- unique exact `recognition_history_id` commitment;
- append-only storage: no UPDATE or DELETE;
- exact `return_id + posting_number + sku` binding;
- exact accounting-date binding;
- exact committed RUB amount;
- exact `authorization_history_id` binding;
- malformed, missing or conflicting evidence fails closed;
- commitment does not itself set `return_cogs_profit_applied=True`;
- commitment does not itself set `profit_adjustment_allowed=True`.

## Rationale

Without a durable first-writer-wins boundary, parallel or repeated application attempts could produce ambiguous or duplicated accounting events. The commit ledger removes that ambiguity while preserving the existing account-level Ozon monetary-authority and no-double-count contracts.

## Deferred

Actual one-time Period Profit consumption remains deferred. A later decision/package must define active-recognition revalidation, selected-period ownership, atomic consumption semantics, and explicit tax treatment before seller-facing arithmetic can change.
