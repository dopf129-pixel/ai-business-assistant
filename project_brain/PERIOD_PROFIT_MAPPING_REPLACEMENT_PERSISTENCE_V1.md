# Period Profit Mapping Replacement Persistence v1 — v139–v143

Date: 2026-08-29

Architecture Review Required: **Yes** (new safety-critical persistence workflow; batch also spans contract, tests, and Project Brain documentation).

## Scope

This batch continues the mapping re-review chain from v134–v138 without changing profit accounting or Ozon business semantics.

Workflow:

`v138 AUTHORIZE → v139 canonical artifact → v140 persistence preview → v141 SAVE/REJECT → v142 inactive revision → v143 existing activation preview`

The steps remain intentionally separate.

## v139 — Authorized replacement mapping builder

`build_authorized_replacement_mapping()` accepts only the explicit v138 `AUTHORIZE` artifact with:

- `mapping_build_allowed=True`;
- `registry_save_allowed=False`;
- `activation_allowed=False`.

It reuses the existing production mapping builders:

- `build_return_financial_operation_authorized_mapping()` for `RETURN`;
- `build_period_profit_expense_operation_authorized_mapping()` for `ADVERTISING` / `STORAGE`.

Therefore canonical hashing and immutable artifact format are unchanged. The artifact is verified again through `verify_period_profit_mapping_integrity()`.

## v140 — Persistence preview

`build_replacement_persistence_preview()` is read-only and shows:

- current active revision / mapping;
- current revision count;
- new mapping ID;
- expected next revision ID / number;
- exact added / removed / changed operation diff.

The preview requires the current active registry mapping to match the mapping that was re-reviewed. Artifact operations, diff replacement operations, and v138 authorized replacement operations must match exactly after deterministic normalization.

No registry write happens in preview.

## v141 — Explicit SAVE / REJECT

`build_replacement_save_decision()` accepts only `SAVE` or `REJECT`.

`SAVE` sets only `registry_save_allowed=True`.

It always keeps:

- `activation_allowed=False`;
- `automatic_activation_allowed=False`;
- `profit_adjustment_allowed=False`;
- `ozon_mutation=False`.

`SAVE != ACTIVATE`.

## v142 — Persist inactive revision

`persist_replacement_as_inactive()` calls the existing registry with `activate=False` only after explicit SAVE.

Before write it re-checks the preview lineage:

- active revision is unchanged;
- revision count is unchanged;
- target mapping ID is unchanged;
- mapping integrity is valid.

A stale preview fails closed.

After save, the active revision must remain unchanged. The new revision is history-only / inactive.

## v143 — Activation handoff

`build_replacement_activation_handoff()` calls only the existing admin `preview(scope, "ACTIVATE", revision_id)` path.

It does **not** call admin `apply()` and does not activate the revision.

Actual activation still requires the pre-existing separate chain:

`activation preview → explicit APPLY/REJECT → registry activation`

## Safety invariants

Unchanged:

- no automatic remap;
- no automatic activation;
- no fuzzy or substring classification;
- no invented Ozon type IDs;
- no Ozon mutation;
- mapping evidence does not alter profit;
- fee evidence is not double-counted;
- return evidence still does not make `returns_included=True`;
- Product Decisions execution invariants are untouched.

## Tests

Targeted file:

`tests/test_period_profit_mapping_replacement_persistence_batch_v139_v143.py`

Coverage includes:

- RETURN canonical hash reuse;
- STORAGE canonical hash reuse;
- read-only preview / expected revision;
- valid-but-unauthorized artifact rejection;
- REJECT blocks persistence;
- SAVE creates inactive revision only;
- stale preview rejection;
- activation handoff produces preview only;
- rejected v138 authorization cannot build a mapping.
