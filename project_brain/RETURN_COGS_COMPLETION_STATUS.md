# Return COGS completion status

Date: 2026-09-09

Production code basis: `2959fa0173d4a69757bd02092f0c765fcc1577ad`.

## Current subsystem status

The Return COGS evidence/application chain is now protected across both read-side and controlled write-side boundaries:

`candidate → exact quantity/identity → inventory recovery → accounting attribution/compensation clearance → accounting recognition → application authorization → exact-once commit → final read-only Period Profit application`.

The chain remains fail-closed. No stage may infer a missing business/accounting fact from another stage's success boolean.

## Completed integrity layers

Completed production controls include:

- exact candidate identity and quantity evidence;
- explicit inventory state with `SALEABLE_RESTORED` / `NON_SALEABLE` and ready-status binding;
- exact accounting attribution, period and compensation/no-double-count evidence;
- canonical accounting readiness status+boolean conjunction;
- accounting-recognition version/state/amount/date/currency proof;
- application authorization with exact recognition binding and monetary-authority/non-overlap proof;
- centralized blocker-stage resolver and exact seller-facing read-only diagnostics;
- exact-once commit readiness and durable commit binding;
- downstream candidate/recognition/authorization/commit set-integrity wrappers;
- final recognition → authorization → commit chain binding before Period Profit recomputation;
- controlled commit transaction that re-reads latest recognition and authorization evidence inside `BEGIN IMMEDIATE`;
- strict semantic retry handling: exact retries idempotent, changed retries rejected;
- append-only durable ledger and read-only ledger-integrity audit;
- SHA-bound feature, PR synthetic and production verification.

## What is intentionally not enabled

The subsystem does not provide a seller-facing accounting commit control. Telegram and seller-facing Period Profit remain analytical/read-only surfaces.

There is no Ozon write path. Return COGS accounting facts are local accounting evidence, and Ozon remains a read-only source.

The controlled commit repository primitive is an internal accounting boundary. Adding an operator/admin consumer would require a separate explicit authorization architecture and should not be inferred from the existence of the repository method.

## Remaining Return COGS work before declaring the domain closed

The highest-value remaining work is operational rather than another financial gate:

1. expose a single read-only Return COGS health/coverage report with counts by blocker stage and exact identities for operator diagnostics;
2. add broad end-to-end scenario fixtures covering complete success, `NON_SALEABLE`, compensation-present, missing quantity, conflicting inventory, stale recognition, stale authorization, duplicate/retry commit and partial candidate coverage;
3. reconcile the remaining large legacy Project Brain state documents without erasing historical checkpoints;
4. decide explicitly whether a controlled accounting/admin consumer of `commit_current_authorization(...)` is required. Do not expose one by default.

After those items, Return COGS can be treated as a mature subsystem and new product work should move to other Period Profit completeness gaps.

## Next financial domain

The next broad financial target should be external/non-Ozon expense completeness, especially recurring/one-off expense coverage and advertising/storage evidence completeness.

The objective should be a unified Period Profit completeness/accounting-readiness surface across all material expense categories, preserving the same rule: missing evidence is unknown, never zero.

## Historical warning distinction

The historical control warning of 8 unresolved returns/units remains distinct from the 785 exact raw Returns API records. Repository documentation does not prove the identities of the historical set of 8, so no identity list is fabricated.

## Permanent invariants

- Ozon READ-ONLY.
- `ReturnedToOzon` is candidate evidence only.
- `unknown != zero`.
- No guessed `quantity × unit cost` Return COGS.
- No accounting/business auto-fill.
- Readiness is not recognition; recognition is not authorization; authorization is not commit; commit is not final application by itself.
- Seller-facing Period Profit remains `read_only=True`, `executed=False`.
- Verification evidence is SHA-bound.
