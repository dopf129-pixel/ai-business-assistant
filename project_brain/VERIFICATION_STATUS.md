# Verification Status

Date: 2026-09-04

## Latest verified product baseline

`d2695fe7863b8c27c66e3ba14055bc5e3d8bb35b`

Package: `v1391-v1400: Period Profit Product Catalog Pagination`

### Exact clean feature head

- SHA `829e9eaa6538771d370f6beaa7ba55f609ac2e4d`;
- Verify #1250 succeeded.

### PR integration checkout

- PR #415;
- synthetic merge SHA `9513770de2ef9375eab7ee7a41ea2b37cc12a970`;
- Verify #1253 succeeded;
- artifact `9941759808`;
- digest `sha256:1d9f3f1eca2453ab945c363602fd1debca210942ee4de0b19c995f61bd819836`;
- artifact name is SHA-bound to the synthetic merge revision.

### Exact production main

- squash SHA `d2695fe7863b8c27c66e3ba14055bc5e3d8bb35b`;
- Verify #1254 succeeded;
- artifact `9941790704`;
- digest `sha256:4f7eaf157be726f96bdc6e24794f29036f6a00374c79d98d7b23160cdb9c4717`;
- artifact name is SHA-bound to exact main.

## Runtime defect closed

Telegram production validation reported `Выручка товаров не совпадает с итоговой выручкой Ozon за период`.

The mismatch was caused by incomplete product identity coverage: the local catalog refresh consumed only the first `/v3/product/list` page. Period Profit now performs complete read-only cursor pagination before loading the local product cache.

The product/account revenue reconciliation guard remains mandatory. The fix corrects catalog coverage rather than relaxing the guard. Account-level Ozon finance remains the monetary authority.

Incomplete, malformed or ambiguous catalog pagination fails closed and stale local subsets are not silently used.

## Verification policy

Exact branch verification proves only that branch head. PR verification proves only the synthetic integration checkout. Every squash-main SHA requires its own exact verification. Failed SHAs remain failed permanently. Missing evidence is unknown, not zero. Ozon mutation remains prohibited. `externally_verified=False` until Telegram production validation confirms the repaired path.
