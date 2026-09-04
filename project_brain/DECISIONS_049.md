# Decision 049 — Period Profit Requires Complete Product Catalog Coverage

Status: Accepted

Date: 2026-09-04

## Decision

Period Profit must refresh the complete read-only Ozon product catalog before using local product identities for SKU-level cost coverage.

A single `/v3/product/list` page is not sufficient evidence of catalog completeness. Cursor pagination must continue until the API indicates completion.

If catalog pagination is incomplete, malformed, repeated, unavailable or cannot be persisted locally, Period Profit fails closed and must not silently use the stale local subset.

## Accounting invariants

- account-level Ozon finance remains the monetary authority;
- product-attributed revenue must still reconcile to account-level revenue;
- the reconciliation guard is not relaxed to compensate for missing products;
- missing product coverage is unknown/incomplete, not zero;
- local catalog refresh does not create a new monetary source;
- Ozon remains read-only.

## Rationale

Telegram production validation showed that the previous first-page-only catalog refresh could omit products while account-level finance remained complete. That produced a false revenue-coverage mismatch and blocked an otherwise valid Period Profit request. The correct fix is complete product identity coverage, not weakening the accounting reconciliation.
