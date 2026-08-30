# Task Persistence Capability Provenance V1

Date: 2026-08-30  
Stages: v408-v417  
Architecture Review Required: Yes

## Goal

Separate task persistence capability claims into distinct evidence classes without active probing of the production task store and without pretending caller-supplied CI metadata is external verification.

The package is read-only.

## v408 — Canonical capability catalog

The provenance service defines exactly six persistence capabilities:

1. `optimistic_concurrency_guard`;
2. `kernel_lock_guard`;
3. `atomic_replace_required`;
4. `file_fsync_required`;
5. `directory_fsync_required`;
6. `coordination_file_ownership_neutral`.

Each capability is bound to:

- implementation source symbol;
- focused regression test file;
- Project Brain design document.

Malformed explicit revision IDs fail fast.

## v409 — Evidence modes

Capabilities are not presented as one homogeneous truth source.

Current evidence modes:

- `IMPLEMENTATION_CONTRACT`;
- `RUNTIME_DIAGNOSTIC`.

`kernel_lock_guard` is runtime diagnostic evidence because the current release snapshot observes whether the kernel-lock primitive is available.

The other capabilities are implementation-contract claims backed by the current code/test contract.

## v410 — No active probing

The provenance service never:

- writes the task store;
- creates a probe task;
- acquires the production write lock merely to test it;
- invokes Ozon;
- invokes business execution.

Every report contains:

`active_probe_performed=False`

by design.

## v411 — Caller-supplied CI metadata contract

The service may structurally validate explicit CI metadata containing:

- exact 40-character SHA;
- workflow `Verify`;
- event `push` or `pull_request`;
- positive run number;
- passed count;
- failed count;
- successful conclusion;
- `exact_sha_bound=True`.

This produces:

`TASK_PERSISTENCE_CI_VERIFICATION_EVIDENCE_READY`

with a deterministic `evidence_id` derived from the exact supplied CI metadata.

The evidence ID is recomputed during downstream validation; changing the metadata or ID breaks the contract.

The artifact retains:

`externally_verified=False`.

Why: the service did not fetch or independently verify GitHub. It validated caller-supplied metadata only.

## v412 — Exact SHA binding

CI metadata can be bound to capability provenance only when:

1. the provenance manifest has an explicitly declared revision;
2. the CI metadata has exact-SHA evidence;
3. the CI target SHA exactly equals the declared revision.

Missing revision fails with:

`TASK_PERSISTENCE_CAPABILITY_REVISION_UNBOUND`

SHA mismatch fails with:

`TASK_PERSISTENCE_CAPABILITY_CI_SHA_MISMATCH`.

No fuzzy, prefix or latest-main matching is used.

## v413 — Snapshot lineage recomputation

A syntactically valid provenance manifest is not trusted by itself.

CI binding receives the original release snapshot and canonically rebuilds the expected manifest.

A manifest built from a different release snapshot fails with:

`TASK_PERSISTENCE_CAPABILITY_MANIFEST_LINEAGE_MISMATCH`.

## v414 — Deterministic audit receipt

Capability audit receives:

- release snapshot;
- canonical manifest;
- optional exact-SHA CI binding.

It rechecks snapshot-to-manifest lineage, the original CI evidence identity, and CI binding consistency.

A binding without its canonical source CI evidence is not sufficient for a bound audit receipt.

The receipt is deterministic SHA-256 local evidence.

It contains no generated timestamp and no path/user/PID evidence.

## v415 — Operator presentation

Authorized operators receive a human-readable provenance summary.

The wording explicitly distinguishes:

- unbound revision/CI state;
- declared revision without CI binding;
- caller-supplied exact-SHA CI binding.

Even a bound CI report says that this is **not external verification**.

## v416 — Operator-only route

New route:

`/task-persistence-provenance`

Additional phrases include:

- `provenance persistence`;
- `источники capability persistence`;
- `task persistence provenance`.

The existing default-deny operator policy is checked before the provenance service is called.

## v417 — Production composition and safety

`create_telegram_core()` accepts optional explicit DI:

- `task_persistence_revision_id=None`;
- `task_persistence_ci_evidence=None`.

Defaults remain unbound.

The factory does not read environment variables, Git metadata or GitHub automatically.

Every provenance artifact keeps:

- `active_probe_performed=False`;
- `externally_verified=False`;
- `automatic_retry_allowed=False`;
- `automatic_lock_recovery_allowed=False`;
- `manual_lock_removal_allowed=False`;
- `business_execution_ready=False`;
- `mutation_ready=False`;
- `read_only=True`;
- `executed=False`.

This package never:

- changes persistence state;
- retries writes;
- deletes coordination files;
- executes Product Decisions;
- executes Product Task Drafts;
- calls Ozon mutation APIs;
- changes mapping authorization;
- changes finance calculations;
- writes `data/users.json`.

## Evidence interpretation

### Implementation contract

Means the current code contract states the behavior and a focused regression file exists.

It is not a runtime measurement.

### Runtime diagnostic

Means the current diagnostic path observed a capability state without active mutation/probing.

It is not external verification.

### CI-bound metadata

Means structurally valid caller-supplied CI metadata matches the explicitly declared exact SHA.

It is still not independently fetched external evidence.

### External verification

Not provided by this package.

`externally_verified=False` remains invariant.

## Verification

Focused regressions cover:

1. exact capability catalog;
2. evidence-mode separation;
3. unbound default state;
4. CI metadata validation;
5. exact SHA binding;
6. cross-snapshot manifest forgery rejection;
7. deterministic lineage-bound audit receipt;
8. operator wording;
9. default-deny route;
10. production default-unbound and explicit-bound DI.

Full GitHub Actions verification is required before merge.
