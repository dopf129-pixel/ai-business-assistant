# Current Project Checkpoint v388-v392

Date: 2026-08-30

## Reconciliation base

Exact `main` at the start of this docs-only batch:

`3a5bbe9332492073555ef258038e4a4db9e7bf85`

Latest merged runtime batch:

`v378-v387: replace orphan-prone task lockfile ownership with kernel flock`

Exact push verification:

- workflow: `Verify`
- run: **#31**
- conclusion: **success**
- result: **1234 passed**
- failed: **0**

## v388 — Current verification baseline

`CURRENT_STATE.md` now points to the exact kernel-lock main SHA and run #31 instead of the earlier v343-v352 baseline.

## v389 — Capability drift cleanup

The remaining unchecked Phase 3 entries for long-running tasks and self-improvement are reconciled with the already completed repository state.

The active product-development notes now point at release readiness and observability rather than already completed recovery work.

## v390 — Roadmap kernel-lock reconciliation

The previous queue still described a stale/unowned lock-file recovery problem.

Current runtime semantics are different:

- lock ownership is kernel-backed through POSIX `flock`;
- the empty coordination file is persistent and ownership-neutral;
- process/fd termination releases kernel ownership;
- file presence is not owner, age or stale evidence;
- no automatic deletion is required or authorized.

The queue now tracks kernel-backed persistence release readiness, operator-only diagnostics and verification.

## v391 — Verification status

`VERIFICATION_STATUS.md` records the exact batch-start main:

`3a5bbe9332492073555ef258038e4a4db9e7bf85`

with:

- push run #31;
- 1234 passed;
- zero failures.

Historical 982/1197 baselines remain evidence only for their own SHAs.

## v392 — Safety checkpoint

This reconciliation is documentation only.

It does not:

- change task persistence runtime;
- change lock acquisition/release;
- write runtime task state;
- modify `data/users.json`;
- execute Product Decisions;
- execute Product Task Drafts;
- call Ozon mutation APIs;
- change mapping authorization;
- change financial calculations.

## Current persistence stack

The task owner now combines:

1. fail-closed load/recovery validation;
2. terminal lifecycle cleanup;
3. atomic temp-file persistence;
4. rollback after failed save;
5. exact persisted-byte optimistic concurrency;
6. POSIX kernel-backed exclusive write locking;
7. file fsync;
8. atomic replace;
9. parent-directory fsync;
10. operator-only default-deny persistence diagnostics.

## Current remaining queue

1. Keep exact-SHA CI green.
2. Improve release observability without adding autonomous recovery.
3. Keep operator persistence access explicit/default-deny.
4. Keep coordination-file presence ownership-neutral.
5. Revisit Product Decision/Product Task Draft mutation only through a separate explicitly authorized architecture.

## Verification semantics after this docs merge

This checkpoint binds the batch-start baseline exactly.

The docs-only squash merge will create another main SHA. That SHA must receive its own successful push verification before being described as exact current-verified.
