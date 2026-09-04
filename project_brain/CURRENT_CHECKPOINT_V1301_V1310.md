# Current Checkpoint v1301-v1310

Date: 2026-09-04

Package: `Originating Sale Quantity Evidence`

## Status

Production lifecycle complete and exact-main verified.

Docs reconciliation is based on exact production main:

`e9b56773bd1dea7c4ac6b97f0c948d49f319bb51`

GitHub Actions push Verify #1150: 2218 passed / 0 failed.

## Entering baseline

Exact docs-reconciled predecessor:

`9bceb0a9cedd5db2a42eef653f5822af21dd4cee`

No verification evidence is transferred from the predecessor or any other SHA to this package.

## Objective

Strengthen Return COGS evidence with an explicit originating-sale quantity source while keeping quantity evidence separate from accounting authorization.

The package answers one narrow question:

> For an FBO return candidate identified by `posting_number + SKU`, does explicit Ozon posting detail show enough originating sale quantity to cover the cumulative candidate return quantity?

It does not decide in which accounting period a COGS recovery belongs, whether Ozon compensation has already economically covered the loss, or whether Period Profit may be adjusted.

## Evidence contract

Source:

`OZON_FBO_POSTING_DETAIL`

Matching basis:

`OZON_FBO_POSTING_NUMBER_AND_SKU_PRODUCT_QUANTITY`

Rules:

1. Only explicit read-only FBO posting detail is accepted in this package.
2. Candidate identity requires non-empty `return_id`, `posting_number`, `SKU` and positive integer return quantity.
3. Sale quantity comes from explicit posting `products[].quantity` and is never inferred from money, current stock, stock delta, historical cost, or return status.
4. All Return COGS candidates sharing the same `posting_number + SKU` share one originating sale quantity budget.
5. Aggregate candidate return quantity must not exceed the explicit originating sale quantity.
6. Exactly one matching SKU row is required. Duplicate matching SKU rows are ambiguous and are not silently summed.
7. Missing SKU, malformed/non-positive quantity, posting failure, or unavailable response remains unconfirmed/unknown.
8. FBS is unsupported in v1301-v1310 and fails closed rather than reusing FBO assumptions.
9. Read-only evidence may be complete without granting any accounting mutation or profit adjustment.

## Source evidence versus accounting gate

The package intentionally introduces a separate source-evidence marker:

`originating_sale_quantity_evidence_confirmed=True`

when every candidate group is supported by explicit, quantity-consistent FBO posting evidence.

That marker does **not** promote the existing Return COGS accounting gate.

The accounting state remains:

- `originating_sale_quantity_confirmed=False`
- `originating_sale_quantity_gate_promoted=False`
- `recovery_period_attribution_confirmed=False`
- `compensation_accounting_treatment_confirmed=False`
- `period_cogs_recovery_confirmed=False`
- `accounting_cogs_recovery_confirmed=False`
- `confirmed_cogs_recovery_amount=0.0`
- `profit_adjustment_allowed=False`
- `automatic_recovery_allowed=False`

This separation prevents a new source fact from silently becoming an accounting rule.

## Production changes

Added:

- `app/services/period_profit_return_sale_quantity_evidence_service.py`
- `app/services/period_profit_return_cogs_quantity_evidence_service.py`
- `tests/test_originating_sale_quantity_evidence_v1301_v1310.py`

Updated:

- `app/period_profit_factory.py`
- `tests/test_period_profit_factory.py`

Production composition shares the existing read-only Ozon client between return evidence and FBO posting-detail quantity evidence.

## Verification evidence

No failed production SHA occurred in v1301-v1310.

### Exact feature head

- SHA: `44b9cf3f0e794d7b17527fad8de5dc7ec3ae1e3b`
- Verify #1148
- 2218 passed / 0 failed
- artifact: 9929146444
- digest: `sha256:f104a0d1a0676b2252185dd52bb4ce47c591461ce1f5fde7e0be0571b2968ce2`
- SHA-bound report: `read_only_evidence=true`, `ozon_mutation=false`

### Pull-request synthetic integration

- PR #397
- synthetic SHA: `3299575f706866dc214d88f65ba18d6663f2743d`
- Verify #1149
- 2218 passed / 0 failed
- artifact: 9929197649
- digest: `sha256:4271c9cba87a6310c1e0cd1175aeaec6769f1f2837beb9b7e9698a92bb555dd7`

### Exact squash-main

- SHA: `e9b56773bd1dea7c4ac6b97f0c948d49f319bb51`
- Verify #1150
- 2218 passed / 0 failed
- artifact: 9929225518
- digest: `sha256:77b4c9c9e1a25cfb4a9bcc31ffec4076c542aa6f0204c30cdbd3a9221e5a6747`

## Preserved architecture and accounting boundaries

- Decision 036: permanent read-only Ozon analyst/advisor boundary.
- Decision 037: account-level Ozon finance remains the monetary authority.
- Decision 038: external operating expense evidence/coverage remains separate.
- Decision 039: historical product cost remains explicit and effective-dated.
- Decision 040: return inventory recovery remains explicit and never inferred from stock movement.
- No new architecture decision was required in v1301-v1310 because no accounting semantics or persistence ownership changed.
- Base Period Profit formula is unchanged.
- No Ozon mutation was added.
- No Product Decision/Product Task Draft execution was added.
- `data/users.json` is unchanged.
- `externally_verified=False`.

## Next accounting gap

The next package should bind two independent facts:

1. explicit recovery accounting-period attribution for confirmed saleable-restored return evidence;
2. explicit compensation accounting treatment/double-count prevention.

Only after those facts are evidence-bound should a later architecture decision consider promoting originating-sale quantity evidence into the accounting Return COGS recovery gate or determining a non-zero confirmed COGS recovery amount.
