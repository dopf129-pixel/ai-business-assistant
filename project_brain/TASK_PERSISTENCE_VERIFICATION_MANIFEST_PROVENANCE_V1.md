# Task Persistence Verification Manifest Provenance V1

Date: 2026-08-30  
Stages: v433-v442  
Architecture Review Required: Yes

## Goal

Import the canonical SHA-bound CI verification manifest into task-persistence capability provenance without network access, active probing, or false claims about final GitHub Actions run success.

The bridge operates only on an explicitly supplied manifest object.

It does not download GitHub artifacts itself.

## v433 — Canonical manifest import

`TaskPersistenceVerificationManifestProvenanceService.import_manifest()` accepts:

- a canonical task-persistence release snapshot;
- a canonical verification manifest;
- an explicit revision ID.

The verification manifest is validated by `AssistantCiVerificationManifestService.validate()`.

The revision must exactly equal the manifest commit SHA.

## v434 — Failed test evidence is preserved

A canonical manifest with test failures is still valid evidence.

It imports with:

- `test_suite_passed=False`;
- exact passed / failed / total / skipped counts;
- no conversion to green;
- no rejection merely because the suite failed.

This keeps failure evidence auditable.

## v435 — Exact revision binding

The bridge uses exact SHA equality only.

A manifest for another revision fails with:

`TASK_PERSISTENCE_VERIFICATION_MANIFEST_SHA_MISMATCH`.

No branch name, prefix, latest-main inference or fuzzy match is accepted.

## v436 — Tamper rejection

A manifest whose deterministic identity or canonical counts are modified fails validation before capability provenance is built.

The bridge does not trust caller-supplied manifest fields without canonical validation.

## v437 — Capability binding

After import, the bridge binds the verification manifest to the exact canonical capability provenance manifest.

Each capability receives explicit local evidence fields:

- `verification_manifest_bound=True`;
- `test_suite_manifest_passed=<bool>`;
- `externally_verified=False`.

The original capability evidence mode remains unchanged.

## v438 — Snapshot lineage

A capability provenance manifest from another release snapshot is rejected even when its revision is syntactically valid.

The bridge reuses the canonical snapshot-to-manifest recomputation from `TaskPersistenceCapabilityProvenanceService`.

## v439 — Deterministic audit receipt

The final audit receipt binds:

- release snapshot lineage;
- capability manifest;
- verification manifest ID;
- canonical test-report ID;
- imported evidence;
- capability binding.

The receipt is deterministic SHA-256 local evidence.

No timestamp is invented.

## v440 — Test manifest vs final CI run

The JSON test manifest is created before the GitHub Actions job is fully complete.

Therefore this package deliberately distinguishes:

- `test_suite_passed`: evidence from the canonical test manifest;
- `final_ci_run_success_confirmed=False`: the bridge does not prove the final GitHub job conclusion;
- `ci_evidence_bound=False`: the existing full CI-evidence contract is not silently reused.

A later component may bind final workflow-run evidence separately.

## v441 — Safety boundary

Every bridge artifact keeps:

- `active_probe_performed=False`;
- `network_fetch_performed=False`;
- `externally_verified=False`;
- `automatic_retry_allowed=False`;
- `automatic_lock_recovery_allowed=False`;
- `manual_lock_removal_allowed=False`;
- `business_execution_ready=False`;
- `mutation_ready=False`;
- `read_only=True`;
- `executed=False`.

The bridge never:

- writes task persistence;
- reads GitHub over the network;
- executes Product Decisions;
- executes Product Task Drafts;
- calls Ozon mutation APIs;
- changes mapping authorization;
- changes financial calculations;
- modifies `data/users.json`.

## v442 — No automatic production wiring

The bridge is intentionally not wired into `create_telegram_core()`.

Production Telegram does not:

- scan local verification artifacts;
- download GitHub artifacts;
- discover repository revisions;
- infer CI state automatically.

Use requires explicit development-side composition.

## Evidence hierarchy

### Capability implementation evidence

Describes current code/runtime capability contracts.

### Verification manifest evidence

Describes canonical SHA-bound pytest output from the repository workflow.

### Final CI run conclusion

Not proven by this bridge.

### External verification

Not provided by this bridge.

`externally_verified=False` is invariant.

## Verification

Focused regressions cover:

1. green manifest import;
2. failed-suite evidence preservation;
3. exact revision mismatch;
4. tampered manifest rejection;
5. canonical capability binding;
6. cross-snapshot lineage rejection;
7. deterministic audit receipt;
8. test-manifest vs final-CI distinction;
9. no execution/external-verification claims;
10. no automatic production wiring.

Full GitHub Actions verification is required before merge.
