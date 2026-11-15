# Decision 067 — FIFO scan continuation side storage

Date: 2026-11-15

## Context

FIFO batch scanning persists encrypted paginated Ozon continuation state. The valid scan contract permits a nested queue of pending supplies and cursor digests that can exceed the v18 scan table's 8 KiB encrypted-token column constraint. Rejecting that valid continuation happens after bounded source requests and prevents progress from being durably resumed.

## Decision

- Preserve the existing v18 scan table and all stored rows/tokens. Tokens up to 8 KiB remain in `fifo_cost_batch_supply_scans.encrypted_resumable_token`.
- Add FIFO schema v19 table `fifo_cost_batch_scan_continuations`, keyed by `(case_id, scan_id)` and linked to the existing scan with a composite foreign key. Store only encrypted continuation bytes there, bounded to 1 MiB per token.
- Enforce a 64 MiB cumulative continuation-storage cap per case transactionally. Replacing a scan's token excludes its current bytes from the quota calculation; terminal checkpoints delete their side-table token.
- Treat the legacy column and side-table row as one logical token on checkpoint reads. Include the side table in normal tenant backup/restore validation and in source-seal fingerprints, so changing continuation state invalidates a stale seal.
- Keep migration additive and within the existing FIFO schema transaction. Do not change Planning `PRAGMA user_version`; do not rewrite or migrate small existing tokens.

## Consequences

- A valid bounded source page can now be resumed after restart even when its encrypted nested queue exceeds 8 KiB.
- The per-token and per-case caps bound memory and database growth. Checkpoint write plus token update is atomic under the existing caller transaction.
- The new table is encrypted-data storage and remains tenant scoped by its parent case/scan relation. Raw continuation identifiers are never included in public diagnostics.
- Migration coverage must prove a v18 small token remains in the original column and readable after upgrade; backup/restore and fingerprint coverage must include large-token side rows.

## Verification

- `tests/test_fifo_cost_batch_scan_checkpoint_service.py::test_checkpoint_round_trips_contract_maximum_nested_supply_queue_under_byte_cap`
- `tests/test_fifo_cost_batch_scan_checkpoint_service.py::test_schema_upgrade_preserves_legacy_checkpoint_token_in_original_column`
- `tests/test_fifo_cost_batch_manifest_read_service.py::test_manifest_reader_seals_one_snapshot_when_new_scan_publishes_mid_read`
- Public backup/restore auto-batch coverage remains in `tests/test_fifo_cost_backup_restore.py::test_public_backup_restore_preserves_fifo_auto_batch_rule_and_manifest`.
