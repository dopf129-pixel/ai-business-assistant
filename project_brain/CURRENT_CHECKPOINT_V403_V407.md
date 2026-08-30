# Current Project Checkpoint v403-v407

Date: 2026-08-30

## Reconciliation base

Exact `main` at the start of this docs-only batch:

`1a31258db514e18842f61d240b9040bbf7eeac46`

Latest merged runtime batch:

`v393-v402: add task persistence release observability`

Exact push verification:

- workflow: `Verify`
- run: **#35**
- conclusion: **success**
- result: **1244 passed**
- failed: **0**

## v403 — Verification baseline

`CURRENT_STATE.md` now points to the exact release-observability runtime SHA and push run #35.

## v404 — Current persistence capability state

The current task persistence stack includes:

1. fail-closed recovery/load validation;
2. exact persisted-byte optimistic concurrency;
3. POSIX kernel-backed exclusive write locking;
4. inert persistent coordination-file semantics;
5. file fsync;
6. atomic replace;
7. parent-directory fsync;
8. operator-only persistence diagnostics;
9. default-deny operator authorization;
10. release readiness projection;
11. explicit incident classification;
12. deterministic local audit receipt.

## v405 — Roadmap advancement

Release observability itself is now completed.

The next hardening target is capability provenance/verification without active probing of the production task store.

This means future release evidence should distinguish:

- implementation-required capability;
- verification evidence;
- runtime observation;
- external verification.

These must not be collapsed into one boolean claim.

## v406 — Verification status

`VERIFICATION_STATUS.md` records:

- exact SHA `1a31258db514e18842f61d240b9040bbf7eeac46`;
- push run #35;
- **1244 passed**;
- zero failures.

Historical baselines remain valid only for their exact SHAs.

## v407 — Safety checkpoint

This batch is documentation only.

It does not:

- probe the production task store;
- write task state;
- retry persistence;
- delete coordination files;
- modify `data/users.json`;
- execute Product Decisions;
- execute Product Task Drafts;
- call Ozon mutation APIs;
- change mapping authorization;
- change financial calculations.

## Current remaining queue

1. Keep exact-SHA CI green.
2. Add explicit capability provenance/verification semantics.
3. Do not active-probe production persistence merely to prove readiness.
4. Keep persistence routes operator-only/default-deny.
5. Keep coordination-file presence ownership-neutral.
6. Preserve separate explicit architecture before any Product Decision/Product Task Draft mutation.

## Verification semantics after this docs merge

This checkpoint binds the batch-start baseline exactly.

The docs-only squash merge creates another `main` SHA. That later SHA requires its own successful push verification before it becomes the new exact current baseline.
