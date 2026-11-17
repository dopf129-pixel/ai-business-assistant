# FIFO supply-list filter fix — independent review packet

Date: 2026-11-17

PR: [#737](https://github.com/dopf129-pixel/ai-business-assistant/pull/737)

Implementation commit: `003ca113669a1e7fe50cc115e7d830bef727ce28`

## Confirmed problem

The owner supplied output from a single read-only call to Ozon `/v3/supply-order/list`. Ozon returned HTTP 400 and rejected `UNSPECIFIED` at `filter.states[11]` as a prohibited zero/unknown enum value. The response establishes rejection of that one value only. It does not establish acceptance of the other filter values, full historical coverage, or any supply quantity/receipt facts.

## Change

- Removed only `UNSPECIFIED` from the shared FIFO list-filter tuple. The other 11 values and their order are unchanged.
- The direct `OzonClient.get_supply_orders_list` wrapper now returns its existing local invalid-request result before HTTP if the status list contains `UNSPECIFIED`, including in a mixed list.
- Ordinary and durable FIFO list reads retain `FIFO_BATCH_SUPPLY_LIST_UNAVAILABLE` and add `FIFO_BATCH_SUPPLY_LIST_REQUEST_REJECTED` only when `error is True`, code is exactly `OZON_HTTP_ERROR`, and `status_code` has exact type `int` with value 400.
- The fixed Telegram message explains that Ozon rejected the request and that the result does not mean no supplies exist. The issue code is persisted through the existing scan storage and remains visible after card restoration.
- No schema, dependency, service/layer, FIFO readiness rule, quantity, cost rule, event, layer, allocation, profit formula, request budget, cursor, sorting, or retry policy changed.

## Regression evidence

- Before implementation, the baseline code failed six targeted cases in a disposable source-only copy: the 11-state allowlist, ordinary and durable list scans against a synthetic Ozon rejection, both HTTP 400 diagnostic cases, and local wrapper validation.
- After implementation, focused profile: **12 passed**.
- Related FIFO/list/cross-docking profile: **108 passed in 8.27s**.
- Full suite in disposable source copy without `.git`, real `data/`, `.env`, runtime files or databases; only a synthetic USN_INCOME 6% tax configuration was added: **5,469 passed in 111.21s**.
- `compileall -q app tests`, `git diff --check`, and `git diff --exit-code -- data` passed. Compile emitted one pre-existing float-identity `SyntaxWarning` in an unrelated test.

## Hosted CI

Verify run [44062802652](https://github.com/dopf129-pixel/ai-business-assistant/actions/runs/44062802652) completed successfully for the implementation commit above:

- Windows: **5,469 passed in 279.45s**, compile passed.
- Linux: **5,469 passed in 49.42s**, compile passed.
- Production Docker image build and runtime smoke passed.
- Successful SHA-bound artifact: [verification report](https://api.github.com/repos/dopf129-pixel/ai-business-assistant/actions/artifacts/14319726631/zip), digest `sha256:2751dd2595f65379115a6f39f1b455f628c74ec8ba3d5a65e75e176da2ef50a7`.

The first Linux attempt had one unrelated nondeterministic failure in `test_comparison_applies_only_the_selected_saved_row`: a random callback token happened to contain the test's hard-coded substring `549`. No code changed between attempts; the failed job was rerun and passed.

## Data safety and limits

- No live Ozon/Telegram request was made for this change.
- The scan correction remains read-only. It does not update the FIFO case/rule, stock movement evidence, layers, allocations, or profit.
- The other 11 list-filter values remain a request profile, not a seller-verified contract. Historical supply coverage and dispatch/receipt timestamps remain unproven.
- The owner's local data, `.env`, runtime database, desktop working copy, running bot and pre-existing worktree were not changed.

## Review classification

Normal, targeted bug fix. No architecture or public service contract change beyond rejecting the already-invalid filter input with the wrapper's existing local error code.
