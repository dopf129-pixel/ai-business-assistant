# Daily-use readiness — independent review handoff

Date: 2026-10-25. Status: `READY_FOR_INDEPENDENT_REVIEW`; R1–R3 and the downstream bounded-soak assertion are fixed, and the latest exact heads have green Windows/Linux CI. Operational owner evidence remains pending.

## Scope and PR order

This is a dependent stack based on the already reviewed, unmerged cross-docking PR #712. Review and integrate only in dependency order. Do not treat the child PR diff against `main` as an independent patch; each child uses the immediately preceding branch as its base.

| Order | PR | Base | Head SHA | Scope | Exact-head Verify |
|---:|---|---|---|---|---|
| 0 | [#712](https://github.com/dopf129-pixel/ai-business-assistant/pull/712) | `main` | `698c9f8bb9c4b8f5acc6b4fdcb475c1062e658ea` | Cross-docking source/evidence prerequisite | `40168559070`, success on Windows/Linux |
| 1 | [#713](https://github.com/dopf129-pixel/ai-business-assistant/pull/713) | `codex/cross-docking-x00-x01` | `e014f2781172d97dc26f9c8d02bb3143e34c738f` | A: offline XLSX/source reconciliation foundation | `40181639324`, success |
| 2 | [#714](https://github.com/dopf129-pixel/ai-business-assistant/pull/714) | `codex/daily-readiness-a-foundation` | `7ec47ef604bf286cb1e5faf0d4fad98f5fcef8fc` | B/C plus exact-head CI regressions | `40182473893`, success (Windows/Linux full tests and compile; Docker build/smoke) |
| 3 | [#715](https://github.com/dopf129-pixel/ai-business-assistant/pull/715) | `codex/daily-readiness-bc` | `509fedba0246b87bbc1d407fdadcf990b2daaee0` | D01/D02 plus fixes R1–R3: backup list formats, startup exclusion, mapping restore | Verify `40185833721`, Windows/Linux success |
| 4 | [#716](https://github.com/dopf129-pixel/ai-business-assistant/pull/716) | `codex/daily-readiness-backup` | `5bd3699cf70a3e459ca0bfd21776799a42c37da1` | D03–D05: update preflight, updater, lifecycle and diagnostics; includes #715 fixes | Verify `40185869091`, Windows/Linux success |
| 5 | [#717](https://github.com/dopf129-pixel/ai-business-assistant/pull/717) | `codex/daily-readiness-operations` | `37d6bb43083c7a078e0ccaf1249e0595af43bef8` | D06/E00 soak and linked acceptance, journals and final docs; includes R1–R3 and the soak lock-file expectation fix | Verify `40186507007`, Windows/Linux success; 3,728 tests per platform; Linux Docker build/smoke success |

The first B/C CI pass exposed two missing identity-projection calls and a stale formatting assertion; the correction is in PR #714 and was propagated to its children. Details: `DAILY_USE_CI_REGRESSION_FIX_2026-10-25.md`. The later backup review found R1–R3 in PR #715; they are fixed in `509fedba0246b87bbc1d407fdadcf990b2daaee0` and merged forward into #716/#717 without rewriting prior commits. PR #717 CI `40186094904` exposed one stale soak assertion (three persistent lifecycle files after adding the startup gate, not two); the regression was corrected at `37d6bb43083c7a078e0ccaf1249e0595af43bef8`. Verify `40186507007` then passed on Windows/Linux with all 3,728 tests and Linux Docker build/smoke. Previous CI for changed heads is superseded; the run IDs in the table apply to the exact current heads.

## Architecture and changed contracts

- **A / reconciliation:** `DailyUseReconciliationService` and `daily_use_reconcile.py` read a single allowlisted XLSX profile in read-only mode; compare the observed accrual total with a saved allowlisted bot JSON snapshot. Currency calculations use `Decimal`; partial, unknown, wrong-period and wrong-scope values fail closed. This is a local verification seam, not a second production finance engine.
- **B / completeness:** the existing Period Profit snapshot projects amount, source, date basis, exact period, status, coverage and reason. Exports preserve the same allowlisted completeness semantics. Future/current SKU cost no longer falls back into an earlier historical period without date-scoped evidence. Existing Return COGS evidence → authorization → explicit commit boundaries remain intact.
- **C / Telegram UX:** the existing result view exposes a short report, scoped details from the same snapshot, clear next actions and cached exports; long responses use bounded transport behavior and avoid duplicate source work. Existing canonical calculations remain the source of financial totals.
- **D / backup and restore:** a new archive/manifest verification and restore service is introduced. Restore stages and verifies a backup before publishing into a new empty target; it must not overwrite the live root. The service and PowerShell commands are fake-only in tests.
- **D / updater and lifecycle:** a new update preflight/runtime service coordinates the existing process lease, exact revision checks, verified backup, fast-forward update, dependency check, compile, offline runtime health, and readiness. Checkout fingerprint and failure enum extend lifecycle metadata. It intentionally does not claim an automatic rollback after a post-stop failure.
- **Persistence/privacy:** backups and diagnostics are allowlisted. Secret material, raw seller responses, full database dumps and user identifiers must not enter PRs, artifacts or support JSON. The runbook makes commands explicit and copyable.

## Independent review map

Review especially:

1. **Finance/source semantics:** `app/services/daily_use_reconciliation_service.py`, completeness projection, event evidence and category breakdown. Confirm net accrual remains authoritative; return operations, ad reconciliation and SKU-level metrics are never double-counted or silently converted to zero.
2. **Period and tenant boundaries:** snapshot scopes, date-effective COGS, saved plan v1/v2, CAS and stale Telegram callbacks. Confirm old period evidence cannot borrow a current cost or a different store's state.
3. **Backup consistency/security:** `app/services/bot_backup_service.py` and `BotStartupMaintenanceGuard`; archive path traversal, symlink behavior, manifest/checksum validation, startup exclusion during snapshots, custom mapping-registry round-trip, interrupted publication, source stability and restore only to a verified empty root.
4. **Update/lifecycle safety:** `app/services/bot_update_preflight_service.py`, `bot_update_runtime_service.py`, `bot_instance_lifecycle_service.py` and PowerShell wrappers. Confirm exact SHA/branch/remote checks, checkout-bound stop, update lock, no restart when already current, failure visibility, secret-safe output and the documented no-auto-rollback boundary.
5. **Resource bounds:** cache/TTL, Telegram message splitting, pagination/request budgets, bounded soak, lock wait and subprocess lifecycle.
6. **Compatibility:** old lifecycle records and saved plans; production entrypoints and existing canonical finance contracts.

## Follow-up review after R1–R3 and soak correction

- R1: list-based JSON writers are included in both source and archive root-type validation; regressions exercise the production storage classes and the full backup/verify/dry-run/restore path.
- R2: backup and canonical startup acquire the same token-scoped kernel guard in a consistent order. The guard remains held through archive publication and is released in `finally`; interleaving regressions cover startup-during-backup and backup-during-startup. Its lock file is intentionally persistent to preserve one kernel-lock inode per token namespace.
- R3: the configured mapping override is represented by an exact approved-root-relative descriptor, validated against a JSON manifest entry before restore, and passed through the same allowlist for dry-run and actual restore. Project, nested storage, separate storage, and external-path cases are covered.
- The downstream soak now asserts exactly two `instance-*` lifecycle artifacts and one persistent `startup-*` lock after eight cycles, while retaining the per-file size bound. Corrected code passed the full exact-head Windows/Linux suite and Linux Docker smoke.
- Repeat review of the confirmed fixes and the new assertion found no additional actionable defect. This remains **Architecture Review Required** because backup/restore and lifecycle locking cross security and process boundaries.

Threat coverage in tests includes double counting, mismatched date/source basis, unknown vs observed zero, tenant isolation, stale callbacks, cache eviction during concurrent reads, backup corruption/path traversal, interrupted backup/restore, update revision races, lock contention, failed readiness and secret redaction.

## Evidence and limits

- August accrual XLSX was read-only reconciled at **38,864 rows**, full period coverage, net accrual **177,282.17 ₽**, matching the historical report. It is not evidence that the currently deployed revision returned the same result.
- August realization detail has **1,293 data rows**, **2 SKUs**, **5,356 sold units** and **2 returned units**. A row count is not a unit count. Analytics ordered units (**6,117**) use a different grain and are not compared as one cohort.
- A second matched period, current exact-revision bot JSON, and a complete 56-day cross-docking signed-accrual / accepted-unit snapshot are still missing. A single acceptance act does not prove the 56-day denominator. No source limitation is represented as zero.
- Local bounded soak: 64 repeated calculations and exports, 12 plan revisions, two tenant storage scopes, and eight synthetic lifecycle cycles; maximum cycle **0.297 s**, thread delta **0**, handle delta **+2**, plan DB **61,440 bytes**, tenant storage **114,688 bytes**. After R2, the lifecycle assertion is updated to the fixed three-file set and passed in exact-head CI. These measurements are short synthetic checks, not multi-day production evidence.
- End-to-end isolated profile: **350 passed in 22.70 s**, covering offline reconciliation, completeness, report and expense flow, planning/export, cross-docking, backup/restore, updater and lifecycle. The initial run had 1 stale fixture expectation; after the intended metadata expectation was updated, the full profile passed.
- CI regression correction: seller cost rows are projected to identity fields only for historical SKU identity; the removed current-cost-to-historical-COGS fallback remains removed. Compact-money tests now expect two decimals. A local focused pytest attempt stalled without output and was interrupted; it is explicitly not counted. Fresh GitHub CI is required for these corrected heads.
- The exact-head full CI is the release verification. Do not treat earlier/base SHA checks as checks for a changed head.

## Owner validation after separate merge/update

`DAILY_USE_A05_OWNER_EVIDENCE_REQUEST_2026-10-25.md` contains the concise owner steps: record bot version; export a redacted JSON snapshot for 01–31 Aug 2026; run the read-only 56-day cross-docking diagnostic and provide only aggregate counts/coverage/sums; later fill the 24–72h observation log. Do not send credentials, `.env`, raw API responses or full databases. Status is `USER_VALIDATION_PENDING` until the owner returns this evidence. This pending external evidence does not prevent review of the code, but it does prevent claiming full real-world operational acceptance.

## Review / release decision boundary

Classification: **Architecture Review Required**. Backup/restore and updater introduce new security and lifecycle boundaries. No PR in this stack has been merged; no deployment, production bot start/stop, live Ozon request, user backup or user-data restore was performed. Independent review should record findings against exact PR heads and require a fresh exact-head CI after every correction.
