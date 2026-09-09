# Period Profit Return COGS inventory warning

Production basis: `6fb22652abc1eaf4737eb5c3ffe38cb00ebb9c8a`.

## Decision

A customer return becoming a Return COGS candidate must not make the compact Telegram warning disappear while saleable-inventory recovery is still unproven.

The current FBO Returns API status `ReturnedToOzon` (`На складе Ozon`) is candidate evidence only. It does not prove `SALEABLE_RESTORED` and does not authorize a COGS recovery amount.

Compact Period Profit therefore keeps two unresolved groups visible:

1. customer-return units that do not reach the Return COGS candidate gate (`unresolved_units`);
2. candidate records whose inventory recovery is not proven by a ready local evidence row while Period COGS recovery is not yet confirmed.

An inventory state is presentation-authoritative only when `inventory_recovery_evidence_status == RETURN_INVENTORY_RECOVERY_READY`. A bare `NON_SALEABLE` or `SALEABLE_RESTORED` value attached to conflicted, unavailable, malformed, or otherwise non-ready evidence is not trusted to suppress or advance the warning.

A candidate explicitly confirmed as `NON_SALEABLE` by ready inventory evidence is not described as an unconfirmed COGS recovery, because no saleable inventory was restored.

## Seller inventory confirmation

Production exposes a local-only Telegram flow named `↩️ Состояние возврата` for the business fact that Ozon evidence cannot safely infer.

The seller must enter the exact:

- `return_id`;
- `posting_number`;
- technical `sku`;
- returned `quantity`.

The seller then explicitly chooses either `SALEABLE_RESTORED` or `NON_SALEABLE` and must pass a separate final confirmation step before anything is persisted.

The record is appended to local `return_inventory_recovery_history` through `ReturnInventoryRecoveryRepository` with the exact return/posting/SKU/quantity, confirmation date, and source `SELLER_CONFIRMED_BOT`. The flow performs no Ozon mutation.

A manual identity typo cannot silently alter Return COGS for another candidate: downstream recovery evidence still requires exact return/posting/SKU identity and exact candidate quantity. Quantity mismatch and identity conflict remain fail-closed.

Seller inventory confirmation is inventory evidence only. It does not prove recovery-period accounting attribution, compensation treatment, compensation double-count clearance, accounting recognition, profit-application authorization, or exact-once commit.

## Read-only blocker diagnostics

Compact Period Profit exposes the first proven Return COGS blocker instead of only a generic unresolved count.

When the local inventory fact is missing or inconsistent, the warning includes the exact candidate identity available in evidence: `return_id`, `posting_number`, technical `SKU`, and quantity. Missing quantity is rendered as `неизвестно`; it is never rendered or interpreted as zero. At most the first three pending candidate identities are expanded in the compact response, with an additional-count suffix when more remain.

The diagnostic explicitly reminds the seller that an Ozon status does not prove `SALEABLE_RESTORED` and points to the existing local `Состояние возврата` flow. Inventory diagnostics advance past this stage only when the evidence row itself is exactly `RETURN_INVENTORY_RECOVERY_READY` and its state is one of the two allowed local states.

This means a synthetic or malformed row such as `inventory_recovery_state=SALEABLE_RESTORED` plus `RETURN_INVENTORY_RECOVERY_UNAVAILABLE` remains an inventory blocker. Likewise, `inventory_recovery_state=NON_SALEABLE` plus an identity conflict cannot hide an unresolved warning.

Once ready saleable inventory recovery is already proven, the diagnostic advances only to evidence already present in the fail-closed chain. It can identify, in order, that the current blocker is:

1. recovery-period accounting attribution / compensation double-count clearance;
2. separate accounting recognition;
3. profit-application authorization;
4. exact-once commit;
5. final seller-facing application.

For the accounting-attribution stage, production now exposes exact per-candidate diagnostics from the already-read evidence rows. The compact warning binds accounting evidence back to the exact `return_id / posting_number / sku` identity and reuses the candidate quantity only when that identity matches. It distinguishes:

- missing accounting attribution;
- exact-identity conflict in accounting evidence;
- accounting evidence that is unavailable or invalid;
- a recovery accounting date that is not confirmed inside the requested period;
- an unconfirmed compensation accounting mode;
- compensation double-count clearance that is not explicitly true.

The accounting rows are sorted by exact identity before presentation, at most three are expanded, and an additional-count suffix is used for larger sets. Missing quantity remains `неизвестно`, not zero. A `None`/unknown double-count clearance remains unconfirmed and cannot advance the diagnostic to recognition, authorization, or commit.

This accounting diagnostic is not an input surface. It does not let the seller write accounting attribution, compensation treatment, recognition, authorization, or commit facts. It only explains the existing fail-closed state already returned by the pipeline.

This is presentation-only observability. The diagnostic does not write accounting evidence, authorize anything, commit anything, or change Period Profit arithmetic. A commit-ready result is still described as read-only and not applied until commit/final-application evidence proves that state.

## Financial invariants

This inventory confirmation and blocker observability do not weaken the Period Profit contract.

- Ozon remains READ-ONLY.
- `ReturnedToOzon` is not mapped to `SALEABLE_RESTORED`.
- `unknown != zero`.
- Non-ready inventory evidence never becomes presentation-authoritative merely because it contains a recognized state string.
- Missing/unknown accounting facts are not auto-filled, coerced to false-as-proof, or treated as zero amounts.
- Exact accounting diagnostics consume repository evidence only; they do not create accounting facts or promote readiness gates.
- No candidate amount is included until the full no-double-counting -> recognition -> authorization -> commit chain succeeds.
- Seller-facing Period Profit remains `read_only=True` and `executed=False`.
- The local inventory confirmation response itself is marked `read_only_ozon=True` and does not execute a Period Profit adjustment.
- Blocker diagnostics consume existing evidence only and do not create or promote any financial gate.

## Warning semantics

The Telegram warning number is not the raw Returns API record count. It is the sum of:

1. `unresolved_units` from customer returns that do not reach the candidate gate; and
2. quantities of candidate records that are not proven `NON_SALEABLE` by `RETURN_INVENTORY_RECOVERY_READY` evidence while Period COGS recovery remains unconfirmed.

Therefore the historical control warning of 8 must not be confused with the 785 exact raw Returns API records for the control period. The warning is unit-based observability for unresolved/unproven customer-return recovery, not a raw-record counter and not a financial `Возврат выручки` counter.

The repository evidence available for this package still does not prove the exact identities of that historical set of 8. No identity list is inferred from the raw-record count or fabricated from incomplete evidence.

## Root cause and classification

The remaining Return COGS pipeline was audited before these production changes.

Automatically provable evidence already present in the pipeline includes return-sample completeness, sale lineage, originating-sale effective cost, originating-sale quantity evidence, and exact identity/amount reconciliation where source evidence exists.

The missing saleable-inventory fact was not an Ozon-derived semantic defect: `ReturnedToOzon` proves only that Ozon has the return, not that sellable inventory was restored. The repository already supported append-only local evidence but Telegram had no seller-facing way to provide it. That missing local input path was fixed by the seller inventory confirmation package.

The blocker-diagnostics package then closed a presentation gap by exposing the first fail-closed stage. The inventory-presentation proof hardening package closed a narrower integrity gap by requiring evidence readiness, not just a state string, before suppressing or advancing the inventory blocker.

The exact accounting-diagnostics package closes the next presentation gap. Accounting evidence and readiness gates already existed and remained correctly fail-closed, but the seller-facing warning collapsed all accounting failures into one generic sentence. Production now reports the exact candidate identity and the specific accounting blocker when that detail is already present in read-only evidence. No new accounting write path was introduced.

Downstream recovery-period attribution, compensation accounting treatment, compensation double-count clearance, accounting recognition, profit-application authorization, and commit evidence remain explicit accounting/business facts and stay fail-closed until independently confirmed.

## Regression coverage

Regression tests prove that:

- a `ReturnedToOzon` candidate with no inventory proof remains visible in compact Telegram output;
- a candidate confirmed `NON_SALEABLE` by ready evidence does not produce a false unconfirmed-recovery warning;
- pre-candidate unresolved units and unproven candidate units are both counted without treating financial return operations as return-count authority;
- seller inventory evidence is not recorded until an exact identity and explicit state are followed by final confirmation;
- `ReturnedToOzon` cannot be submitted as an inventory recovery state;
- cancellation and invalid identity/state input record nothing;
- both `SALEABLE_RESTORED` and `NON_SALEABLE` are local explicit seller facts and never Ozon writes;
- missing inventory evidence exposes exact return/posting/SKU identity when available;
- unknown quantity is rendered as unknown rather than zero;
- ready `NON_SALEABLE` candidates are not surfaced as needing saleable-restoration confirmation;
- conflicted `NON_SALEABLE` evidence remains unresolved and visible;
- unavailable `SALEABLE_RESTORED` evidence remains at the inventory blocker and does not advance to accounting;
- after ready inventory proof, diagnostics stop at the first unproven accounting/recognition/authorization/commit gate;
- missing accounting attribution exposes exact return/posting/SKU identity and preserves unknown quantity;
- accounting evidence outside the requested period exposes the period-attribution reason for the exact candidate;
- unknown compensation double-count clearance remains explicitly unconfirmed and does not advance to later gates;
- exact accounting blocker rows are rendered deterministically, with at most three expanded identities and an additional-count suffix;
- commit-ready evidence is still presented as read-only and not as applied profit.

## SHA-bound verification evidence

Previous warning observability package:

- feature head `77042b8aa2ecccdac965858e4a20b5541178b6ef` — Verify #1622 passed on exact push SHA;
- actual PR #471 synthetic merge `b21dabbbdc3e674412a2787953d007c8c72be62b` — Verify #1623 passed; artifact `verification-b21dabbbdc3e674412a2787953d007c8c72be62b`;
- squash production main `612778b0be89f15cd70d193d1caaf94ebf422cc8` — Verify #1624 passed.

Seller inventory confirmation package:

- feature head `f91bd6f847405859aaba643d37b4f03fc6529ef9` — Verify #1634 passed on exact push SHA; full suite passed;
- actual PR #473 synthetic merge `75fe63f6ef6ac1f6a868215ae053054aa0afa9ad` — Verify #1635 passed with 2,384 tests, 0 failures; artifact `verification-75fe63f6ef6ac1f6a868215ae053054aa0afa9ad` recorded `ref=refs/pull/473/merge`, `business_execution=false`, and `ozon_mutation=false`;
- squash production main `c9efce6c51cf8f890a8e584f64da6c4d6bac3f9` — Verify #1636 passed on exact `main` push SHA with the full test suite.

Read-only blocker diagnostics package:

- feature head `f30454e7ea7cc36ba26187544aa06ccff333c5cd` — Verify #1643 passed on the exact push SHA;
- actual PR #475 synthetic merge `df656b1bd514d2683415d8f131bebac4c7eea153` — Verify #1644 passed with 2,384 tests, 0 failures; artifact `verification-df656b1bd514d2683415d8f131bebac4c7eea153` recorded `ref=refs/pull/475/merge`, `sha_bound=true`, `business_execution=false`, `ozon_mutation=false`, and `read_only_evidence=true`;
- squash production main `a686869ee6660214ef812650a5b90c70eda13bf3` — Verify #1645 passed on the exact `main` push SHA with compile, deterministic schema, full test suite, SHA-bound report, and artifact upload successful.

Inventory presentation proof hardening package:

- feature head `12e8c7b2237133703aecd4ab8cb46ed9e4089891` — Verify #1653 passed on the exact push SHA;
- actual PR #477 synthetic merge `b25a52758d3998a6a4de10f74e5e714367ff12cb` — Verify #1654 passed; SHA-bound artifact `verification-b25a52758d3998a6a4de10f74e5e714367ff12cb` identifies the PR merge revision;
- squash production main `ae2e64eec92726a51c28f0d7978645b5ac1ba319` — Verify #1655 passed on the exact `main` push SHA with compile, deterministic schema, full test suite, SHA-bound report, and artifact upload successful.

Exact accounting blocker diagnostics package:

- feature head `b3a83bbc92f561b6945f2e387088d270deb906af` — Verify #1663 passed on the exact push SHA with compile, deterministic schema, full test suite, SHA-bound report, and artifact upload successful;
- actual PR #479 synthetic merge `865a1cda86824fe935521c6001cf36d4f0611f44` — Verify #1664 passed; SHA-bound artifact `verification-865a1cda86824fe935521c6001cf36d4f0611f44` identifies the PR merge revision;
- squash production main `6fb22652abc1eaf4737eb5c3ffe38cb00ebb9c8a` — Verify #1665 passed on the exact `main` push SHA with compile, deterministic schema, full test suite, SHA-bound report, and artifact upload successful.

Verification evidence is SHA-bound and is never transferred between revisions.
