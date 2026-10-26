# D06 — bounded resilience checks and recovery runbook

Status: `VERIFIED_OFFLINE`. Scope: synthetic data, isolated temporary directories and fake polling processes only. No live Telegram/Ozon requests, real bot launch, owner backup or production data were used.

## Bounded soak

`tests/test_daily_use_bounded_soak.py` performs:

- 64 repeated canonical unit-price calculations and 64 identical period-profit exports; results remain stable and each export stays below 64 KiB.
- Twelve saved-plan revisions, followed by construction of a fresh repository instance and a read of the latest revision/history.
- Persistence/reopen checks for saved costs and expenses in two isolated tenant scopes.
- Eight subprocess polling lifecycles: start, authenticated status read, graceful stop and final stopped-state read. The test measures cycle duration, process handles, threads and state-file size/count.
- SQLite plan size and tenant-storage file/byte bounds.

Measured on Windows/Python 3.12:

| Measurement | Result |
|---|---:|
| Repeated calculations / exports | 64 / 64 |
| Persisted plan revisions | 12 |
| Plan database | 61,440 bytes |
| Tenant storage | 2 files, 114,688 bytes |
| Isolated lifecycle cycles | 8 |
| Maximum start/status/stop cycle | 0.297 s |
| Lifecycle state files after all cycles | Three-file structure and ≤16 KiB/file assertions passed in exact-head CI; byte total was not emitted by the CI log |
| Thread-count change | 0 |
| Process-handle change | +2 |

The D06 targeted profile also covers analytics snapshot TTL and atomic bounded cache eviction, saved-plan invalid-clock failure, graceful-stop timeout, interrupted backup publication, failed staged restore, cross-docking finance checkpoint resume and supply checkpoint resume. Result: **11 passed in 3.74s**.

## Runbook and owner observation

- `docs/daily-use-recovery-runbook.md` gives separate copyable PowerShell commands for status, local healthcheck, stop, backup, archive verification, restore dry-run, update, and safe diagnostics. It includes recovery boundaries for a missing master key, local Git conflict and an interrupted update.
- `project_brain/DAILY_USE_OWNER_OBSERVATION_LOG_2026-10-25.md` is a 24–72 hour owner observation template. It remains `USER_VALIDATION_PENDING` until completed after a separate merge/update.
- `docs/windows-local-handoff.md` and README link to the runbook.

## Limits and result

The measured cycles are short synthetic checks, not evidence of multi-day production stability or Ozon source availability. No new architecture or persistent runtime contract was introduced. D06 is complete; E00 linked regression and integrated exact-head CI are verified. Owner operational observation remains pending in E03.
