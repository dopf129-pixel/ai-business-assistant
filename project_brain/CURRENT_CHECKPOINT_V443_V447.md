# Current Project Checkpoint v443-v447

Date: 2026-08-30

## Reconciliation base

Exact `main`:

`379352ad66cf90debc2cebdf701dc2e4ef1170ed`

Latest merged batch:

`v433-v442: bind canonical verification manifests to persistence capability provenance`

Exact push verification:

- workflow: `Verify`
- run: **#45**
- conclusion: **success**
- result: **1276 passed**
- failed: **0**

## v443 — Current exact baseline

`CURRENT_STATE.md` now points to the exact v433-v442 main SHA and push run #45.

## v444 — Queue cleanup

The duplicated numbering in `CURRENT_STATE.md` is corrected.

The verification/provenance queue now reflects completed manifest import rather than repeating it as future work.

## v445 — Final workflow-run evidence target

The next hardening layer is explicit final GitHub workflow-run evidence.

It must remain separate from the earlier test-report manifest because that manifest is generated before the GitHub Actions job is fully complete.

## v446 — Verification status

`VERIFICATION_STATUS.md` now distinguishes:

1. implementation contract;
2. runtime diagnostic;
3. SHA-bound test manifest;
4. caller-supplied CI metadata;
5. final workflow-run conclusion;
6. external verification.

Only layers actually evidenced may be claimed.

## v447 — Safety checkpoint

This reconciliation is documentation only.

It does not:

- fetch GitHub from production runtime;
- probe or write the task store;
- execute Product Decisions;
- execute Product Task Drafts;
- call Ozon mutation APIs;
- change mapping authorization;
- change financial calculations;
- modify `data/users.json`.

## Current remaining queue

1. Keep exact-SHA CI green.
2. Add explicit completed workflow-run evidence binding.
3. Require exact head SHA / run ID / run number / workflow / event / status / conclusion.
4. Keep test-manifest evidence separate from final CI-run evidence.
5. Preserve `externally_verified=False` unless an explicit independent verification contract exists.
6. Keep production persistence/operator boundaries default-deny and non-mutating.

## Post-merge rule

The docs-only squash merge creates a new main SHA.

That SHA must receive its own successful push verification before it becomes the next current verified baseline.
