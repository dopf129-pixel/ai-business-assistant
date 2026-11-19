# FIFO supply-list sort direction fix — review packet

## Scope

- Both FIFO reads of /v3/supply-order/list use ORDER_CREATION / DESC.
- The existing 11-state filter is unchanged.
- Ordinary checkpoint fingerprints and durable scan continuations use source contract OZON_SUPPLY_BUNDLE_V1_ORDER_LIST_DESC_V2.
- Restoring a card with a saved continuation from the old ASC contract removes only the active resumable token. The old scan row remains stored. Refresh starts a fresh request with no cursor.

## Evidence and limits

The owner supplied the real-shop comparison: ASC returned HTTP 400 with “Ascending sort direction is not supported for archive order states.”; the same list request with DESC returned 10 orders. No live Ozon/Telegram call was made for this change.

A successful first page confirms that the list request can be read for that shop/request. It does not establish full historical coverage, dispatch or physical acceptance, or FIFO readiness.

## Verification

- Targeted ordinary/durable list, DESC continuation, and current/legacy durable restore profile: 5 passed.
- tests/test_fifo_cost_batch_supply_source.py: 42 passed.
- Linked source/checkpoint/rule profile: 57 passed.
- compileall -q app tests, git diff --check, and git diff --exit-code -- data passed.
- Exact-head CI is checked on the PR head commit; the final status is linked from the PR.

## Review classification

Normal change; no new layer, dependency, or persistence schema. Existing checkpoint contract versioning is reused.
