# Verification Status

Date: 2026-09-04

## Latest verified product baseline

`e9b56773bd1dea7c4ac6b97f0c948d49f319bb51`

Latest merged production batch:

`v1301-v1310: Originating Sale Quantity Evidence`

### Entering exact docs-reconciled main
- exact main: `9bceb0a9cedd5db2a42eef653f5822af21dd4cee`
- this SHA is the docs-reconciled predecessor used as the exact feature branch base
- no verification evidence is transferred from this SHA to later revisions

### Failed intermediate evidence

No failed production SHA occurred in v1301-v1310.

Failed SHAs from earlier packages remain failed evidence permanently and are not reclassified by this package.

### Exact final feature-head verification
- exact SHA: `44b9cf3f0e794d7b17527fad8de5dc7ec3ae1e3b`
- Verify #1148
- 2218 passed / 0 failed
- artifact id: 9929146444
- digest: `sha256:f104a0d1a0676b2252185dd52bb4ce47c591461ce1f5fde7e0be0571b2968ce2`
- SHA-bound report: `read_only_evidence=true`, `ozon_mutation=false`

### PR merge-ref integration verification
- PR #397
- synthetic SHA: `3299575f706866dc214d88f65ba18d6663f2743d`
- Verify #1149
- 2218 passed / 0 failed
- artifact id: 9929197649
- digest: `sha256:4271c9cba87a6310c1e0cd1175aeaec6769f1f2837beb9b7e9698a92bb555dd7`

This proves only the PR synthetic integration revision.

### Post-merge exact-main verification
- exact main: `e9b56773bd1dea7c4ac6b97f0c948d49f319bb51`
- Verify #1150
- 2218 passed / 0 failed
- artifact id: 9929225518
- digest: `sha256:77b4c9c9e1a25cfb4a9bcc31ffec4076c542aa6f0204c30cdbd3a9221e5a6747`

## Current quantity evidence boundary

v1301-v1310 adds explicit originating-sale quantity source evidence for FBO Return COGS candidates.

Evidence contract:

- source is read-only FBO posting detail;
- matching identity is exact `posting_number + SKU`;
- quantity is explicit `products[].quantity`;
- all return candidates for the same posting+SKU share one originating sale quantity budget;
- cumulative candidate return quantity must not exceed that sale quantity;
- duplicate matching SKU rows are ambiguous rather than summed;
- missing/malformed/non-positive quantity remains unconfirmed;
- FBS quantity evidence is unsupported in this package and fails closed;
- quantity is never inferred from money, current stock or stock deltas.

`originating_sale_quantity_evidence_confirmed=True` is source evidence only.

The accounting gate remains intentionally unpromoted:

- `originating_sale_quantity_confirmed=False`
- `originating_sale_quantity_gate_promoted=False`
- `recovery_period_attribution_confirmed=False`
- `compensation_accounting_treatment_confirmed=False`
- `period_cogs_recovery_confirmed=False`
- `accounting_cogs_recovery_confirmed=False`
- `confirmed_cogs_recovery_amount=0.0`
- `profit_adjustment_allowed=False`
- `automatic_recovery_allowed=False`

Period Profit formula is unchanged.
No Ozon mutation is authorized or performed.

## Next accounting gap

Bind explicit recovery accounting-period attribution and compensation accounting treatment/double-count prevention as independent fail-closed evidence.

Only after those facts are explicit may a later architecture decision consider promoting quantity evidence into an accounting COGS-recovery gate.

## Verification policy

Exact branch push verification proves only that exact branch head.
Pull-request runs prove only their synthetic merge refs.
Every squash-main SHA requires its own exact push verification.
Failed SHAs remain failed evidence permanently.
Cancelled/pending SHAs carry no transferable success claim.
Missing evidence remains unknown and is never interpreted as zero/clean.
Workflow evidence is project CI evidence only;
`externally_verified=False`.
