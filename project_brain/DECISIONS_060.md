# Decision 060 — updater maintenance gate and bounded SQLite snapshot

Date: 2026-10-25

## Context

The checked updater previously released the startup/snapshot guard after the backup completed. A second local bot process could then claim the checkout while Git or dependency files were changing. SQLite's Python online-backup call could also retry a busy database without observing the updater's per-step timeout.

## Decision

- The updater owns the existing token-scoped startup/maintenance guard for the full update operation, including backup, fast-forward, dependency checks and offline health checks.
- Backup accepts reuse of that exact already-held guard and does not release a guard owned by the updater.
- The updater releases the guard at the normal startup handoff or on every return/failure path.
- SQLite online backup runs in a standard-library subprocess. The parent enforces a bounded wall-clock deadline and terminates the worker on timeout; the worker receives only the paths it needs and a minimal environment.

## Status

Implemented with synthetic regressions. Exact-head Verify `40222900262` passed on Windows and Linux at code head `39d1a12bcb699ef504abbbb1c484a5a7745f23a7` (3,736 tests per platform, compile, Linux Docker build/runtime smoke). Repeat technical review found no additional actionable defect. No real bot, credentials or user database was used.
