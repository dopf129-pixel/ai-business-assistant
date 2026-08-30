# CI Verification Manifest Bridge V1

Date: 2026-08-30  
Stages: v418-v427  
Architecture Review Required: Yes

## Goal

Bridge the repository-native GitHub Actions verification workflow to the existing exact-SHA `AssistantProjectVerificationService` with a canonical machine-readable JSON artifact.

Before this package CI uploaded:

- `revision.txt`;
- `pytest-junit.xml`.

The project verification service already understood SHA-bound test reports, but CI did not emit that contract directly.

## v418 — JUnit parser

`AssistantCiVerificationManifestService` reads pytest JUnit XML with Python stdlib `xml.etree.ElementTree`.

It supports a `testsuite` root or a `testsuites` aggregate.

Malformed or missing XML fails closed.

## v419 — Count semantics

JUnit fields are normalized as:

- failed = failures + errors;
- total = JUnit tests - skipped;
- passed = total - failed.

Skipped tests are preserved separately and are not silently counted as passed.

The canonical test-report invariant remains:

`passed + failed == total`.

## v420 — Canonical test-report contract

The service delegates test-report construction to the existing `AssistantTestRunnerService`.

Therefore the JSON artifact uses the same deterministic identity:

`pytest:<commit_sha>:<passed>:<failed>:<total>`

already understood by `AssistantProjectVerificationService`.

## v421 — Verification manifest identity

The complete manifest has deterministic:

`verification_manifest_id=ci-verification:<sha256>`.

Validation recomputes:

- SHA binding;
- CI metadata;
- test counts;
- canonical test report;
- manifest identity;
- safety flags.

Tampering fails closed.

## v422 — Failure evidence

Missing or malformed JUnit produces an explicit invalid manifest instead of a false green report.

The CLI writes that invalid JSON before returning non-zero.

This allows the artifact upload step to preserve diagnostic evidence even when verification infrastructure fails.

## v423 — CLI

New module:

`python -m ci_verification_manifest`

Inputs:

- JUnit path;
- output path;
- exact commit SHA;
- workflow;
- GitHub event;
- run ID;
- run number.

No network access is required.

## v424 — Workflow generation

The `Verify` workflow runs manifest generation after pytest with:

`if: always()`.

Therefore both successful and failing pytest runs attempt to emit a canonical JSON report.

The original pytest exit status remains authoritative for the CI job.

## v425 — Exact GitHub metadata

The workflow passes:

- `GITHUB_SHA`;
- `GITHUB_WORKFLOW`;
- `GITHUB_EVENT_NAME`;
- `GITHUB_RUN_ID`;
- `GITHUB_RUN_NUMBER`.

The uploaded artifact now includes:

`verification-artifacts/test-report.json`.

The artifact name remains bound to `github.sha`.

## v426 — Project verification bridge

`AssistantProjectVerificationService.evaluate_manifest()`:

1. validates the CI manifest;
2. extracts the canonical test-report fields;
3. delegates to the existing exact-SHA evaluation.

A current green manifest becomes `CURRENT_VERIFIED`.

A green manifest for another SHA remains `STALE_BASELINE`.

A tampered manifest becomes `CI_VERIFICATION_MANIFEST_INVALID`.

## v427 — Safety boundary

This package is development verification infrastructure only.

It does not:

- execute seller actions;
- execute Product Decisions;
- execute Product Task Drafts;
- mutate Ozon;
- change mapping authorization;
- change financial calculations;
- modify runtime user or task data.

Workflow permissions remain:

`contents: read`.

Ozon credentials remain explicitly empty.

The manifest contains:

- `read_only_evidence=True`;
- `business_execution=False`;
- `ozon_mutation=False`.

## Artifact semantics

A successful artifact contains:

- schema version;
- exact commit SHA;
- passed / failed / total / skipped counts;
- deterministic test-report ID;
- workflow, event and run metadata;
- deterministic verification-manifest ID;
- non-execution safety flags.

No timestamp is invented by the manifest service.

## Relationship to capability provenance

The JSON artifact is a stronger source for future explicit CI metadata import than manually transcribed counts.

However, reading or validating a local artifact still does not by itself mean independently verified external provenance.

Any later capability-provenance integration must preserve that distinction and must not silently set `externally_verified=True`.

## Verification

Focused regressions cover:

1. green JUnit parsing;
2. failures, errors and skips;
3. deterministic manifest identity;
4. tamper rejection;
5. missing or malformed JUnit;
6. CLI success/error behavior;
7. workflow ordering and `always()`;
8. exact GitHub metadata wiring;
9. current/stale project verification;
10. tampered-manifest rejection before project verification;
11. development-only safety invariants.

Full GitHub Actions verification is required before merge.
