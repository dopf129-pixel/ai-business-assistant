# Period Profit Return COGS canonical status chain

Production basis: `93ee4633295f483d04d445693c29bdf0c0139f40`.

## Decision

Return COGS cannot advance because a downstream confirmation boolean happens to be `True`. Every material downstream gate now requires the canonical status emitted by its own evidence service together with its confirmation boolean. Missing, partial, blocked, unavailable, malformed, or unknown status remains fail-closed.

This protects seller-facing Period Profit from inconsistent synthetic evidence and from future adapters that accidentally copy a boolean without the status contract that gives the boolean its meaning.

## Canonical gate order

The read-only first-blocker chain is:

1. inventory recovery evidence;
2. accounting attribution / compensation treatment and double-count clearance;
3. accounting recognition;
4. profit-application authorization;
5. exact-once application commit;
6. final seller-facing application.

Inventory remains authoritative only when `inventory_recovery_evidence_status == RETURN_INVENTORY_RECOVERY_READY` and the local state is exactly `SALEABLE_RESTORED` or `NON_SALEABLE`.

After inventory, production now requires these exact status contracts:

- accounting: `PERIOD_PROFIT_RETURN_COGS_ACCOUNTING_EVIDENCE_READY` plus `accounting_attribution_evidence_confirmed is True`;
- recognition: `PERIOD_PROFIT_RETURN_COGS_ACCOUNTING_RECOGNITION_READY` plus `return_cogs_accounting_recognition_evidence_confirmed is True`;
- authorization: `PERIOD_PROFIT_RETURN_COGS_APPLICATION_ELIGIBILITY_READY` plus `return_cogs_profit_application_eligibility_confirmed is True`;
- commit: `PERIOD_PROFIT_RETURN_COGS_APPLICATION_COMMIT_CONFIRMED` plus `return_cogs_profit_application_commit_confirmed is True`;
- final application: `return_cogs_profit_applied is True` only after the committed canonical chain has passed the final application service.

A status/boolean disagreement is not normalized. The earlier unresolved stage wins.

## Accounting readiness hardening

`PeriodProfitReturnCogsAccountingReadinessService` now explicitly records `return_cogs_accounting_evidence_status_confirmed` and requires the canonical accounting evidence READY status before `return_cogs_accounting_readiness_confirmed` can become true.

A true `accounting_attribution_evidence_confirmed` boolean cannot override:

- a missing accounting evidence status;
- `PERIOD_PROFIT_RETURN_COGS_ACCOUNTING_EVIDENCE_PARTIAL`;
- `PERIOD_PROFIT_RETURN_COGS_ACCOUNTING_EVIDENCE_UNAVAILABLE`;
- an unknown status string.

The explicit blocker `ACCOUNTING_ATTRIBUTION_EVIDENCE_READY_STATUS_REQUIRED` is emitted when the canonical top-level status is not ready.

Even when accounting readiness succeeds, this service still does not apply money. It keeps `period_cogs_recovery_confirmed=False`, `accounting_cogs_recovery_confirmed=False`, `confirmed_cogs_recovery_amount=0.0`, `profit_adjustment_allowed=False`, and `automatic_recovery_allowed=False` because monetary recovery remains a later controlled contract.

## Centralized first-blocker resolver

`PeriodProfitReturnCogsBlockerStageService` is now the single ordering authority for seller-facing Return COGS blocker stages.

The resolver requires both the canonical status and the corresponding confirmation boolean at accounting, recognition, authorization, and commit. It also treats malformed candidate rows as inventory-blocked rather than silently skipping them.

A true commit boolean with only `PERIOD_PROFIT_RETURN_COGS_APPLICATION_COMMIT_READY` remains at the commit stage. Commit readiness is not durable commit evidence.

A fully committed canonical chain with `return_cogs_profit_applied is not True` produces the separate `RETURN_COGS_BLOCKER_FINAL_APPLICATION` stage. That stage is observability only and does not authorize a second commit.

## Compact Telegram integration

`period_profit_compact_response.py` no longer maintains a separate copy of the financial gate ordering. It asks `PeriodProfitReturnCogsBlockerStageService` for the first blocker and then renders the existing exact diagnostic for that stage.

Exact diagnostic behavior is preserved:

- candidate identity remains `return_id / posting_number / SKU`;
- missing quantity is shown as `неизвестно`, never zero;
- inventory rows are deterministic and limited to three expanded identities;
- exact accounting, recognition, authorization, and commit reasons reuse existing read-only evidence rows;
- final application has an explicit message that confirmed commit without seller-facing application is not permission to repeat commit.

This removes financial stage-order duplication from Telegram presentation while keeping the presentation read-only.

## Final application hardening

`PeriodProfitReturnCogsFinalApplicationService` now rejects inconsistent downstream evidence before recomputing seller-facing Period Profit.

When the commit confirmation boolean is true, final application additionally requires:

- canonical committed commit status;
- canonical ready authorization status and confirmed authorization;
- canonical ready recognition status and confirmed recognition;
- canonical ready accounting status and confirmed accounting attribution.

Only after those gates pass does the service validate durable commit records: recognition version, authorization version, exact return identity, accounting date, RUB currency, committed amount, unique recognition version, and equality between the sum of committed records and the eligible amount.

No repository write was added. The final service only recomputes a read-only result from already durable committed evidence. It remains `read_only=True` and `executed=False`.

## Failure semantics

The following states remain blockers and are never treated as successful evidence merely because a boolean is true:

- missing status;
- partial status;
- blocked status;
- unavailable status;
- unknown status;
- malformed candidate record;
- commit-ready without committed status;
- committed status chain without final seller-facing application.

Unknown data is not converted to zero. Failure at a status gate does not trigger monetary inference or application.

## Financial invariants

- Ozon remains READ-ONLY.
- `ReturnedToOzon` remains candidate evidence only and is not `SALEABLE_RESTORED`.
- `unknown != zero`.
- Return COGS is never derived from returned quantity multiplied by a guessed unit cost.
- Missing accounting/business facts are never auto-filled.
- Accounting readiness is evidence readiness, not monetary execution.
- Recognition does not imply authorization.
- Authorization does not imply commit.
- Commit readiness does not imply commit.
- Final-application observability does not authorize a repeated commit.
- Seller-facing Period Profit remains `read_only=True` and `executed=False`.

## Regression coverage

The package adds or updates regression coverage proving that:

- canonical accounting READY plus all independent facts can promote accounting readiness;
- PARTIAL, missing, UNAVAILABLE, and unknown accounting status block readiness even when all confirmation booleans are true;
- the centralized stage resolver refuses to advance on accounting, recognition, authorization, or commit status/boolean conflicts;
- malformed candidate rows remain inventory-blocked;
- ready and non-ready `NON_SALEABLE` inventory evidence retain their existing distinct behavior;
- final application rejects commit, authorization, recognition, and accounting status conflicts;
- a complete canonical chain with valid durable commit records can still recompute seller-facing Period Profit;
- legacy test fixtures now model the same canonical evidence contract as production instead of relying on boolean-only shortcuts;
- compact diagnostics continue to stop at exactly one first blocker and remain non-executing.

## SHA-bound verification evidence

Code package:

- feature head `d6352a58314e5b178e94c270af44a13210c1d21d` — Verify #1709 passed after compile, deterministic schema initialization, full test suite, SHA-bound report generation, and artifact upload;
- PR #487 synthetic merge `113c70f2134d2f00dd750dac673bc32e9b6571ad` — Verify #1710 passed; artifact `verification-113c70f2134d2f00dd750dac673bc32e9b6571ad` binds verification to the synthetic merge revision;
- squash production main `93ee4633295f483d04d445693c29bdf0c0139f40` — Verify #1711 passed on the exact main revision; artifact `verification-93ee4633295f483d04d445693c29bdf0c0139f40` is SHA-bound to production.

An earlier feature run deliberately failed after the first hardening change because six legacy fixtures still omitted the newly required canonical status fields. Those fixtures were reconciled to the production evidence contract; the status checks themselves were not weakened. The final feature, PR synthetic, and production main verification runs all passed.

Verification evidence is revision-specific and must not be transferred between SHAs.
