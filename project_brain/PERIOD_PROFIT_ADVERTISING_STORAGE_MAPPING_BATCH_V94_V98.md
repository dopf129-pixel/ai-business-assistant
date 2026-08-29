# Period Profit Advertising and Storage Mapping Batch v94-v98

This batch extends the period-profit evidence architecture for `ADVERTISING` and `STORAGE` without changing the profit formula.

## v94 — Operation review

Builds an unclassified human-review view from the real Ozon finance operation catalog. Every operation has `expense_related=None`; automatic classification and mapping activation are prohibited.

## v95 — Human selection

Only exact `type_id` values visible in the review artifact may be selected. Empty or unknown selections block.

## v96 — Authorization and immutable mapping

`AUTHORIZE` permits exact financial-evidence mapping only. A deterministic SHA-256-derived mapping artifact is non-persistent, immutable, cannot self-activate, and has `profit_adjustment_allowed=False`.

## v97 — Period-profit query wiring

`PeriodProfitQueryService` accepts separate authorized advertising/storage mapping artifacts. Only artifacts with matching scope and all safety flags are used. Exact operation names are matched against the existing period `fee_breakdown`.

## v98 — User-facing evidence

The response may show matched advertising/storage operation count, amount and mapping ID. These amounts are explicitly described as already represented inside `net_accrual`; they are never subtracted a second time.

Coverage distinguishes evidence availability from full component accounting. `advertising_included=False` and `storage_included=False` remain unchanged until those components are proven fully covered.

No Ozon mutation, Product Decision execution, automatic classification, or profit-formula change is introduced.
