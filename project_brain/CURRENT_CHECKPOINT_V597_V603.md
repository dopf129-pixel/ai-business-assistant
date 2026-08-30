# Current Checkpoint v597-v603

Date: 2026-08-30

Package: Entry/Core Result Integrity v1

## Verified implementation

The application entry and core boundaries now reject malformed direct-runtime and orchestrator results instead of forwarding, mutating, or raising on them.

Verified behavior:

- non-None direct-runtime results must be dictionaries with an explicit boolean `error`;
- malformed task-persistence, freshness, mapping-recovery, mapping-admin, return-review, and period-profit runtime payloads fail closed with deterministic non-secret codes;
- valid explicit runtime failures remain failures and are preserved;
- AssistantCoreService validates the orchestrator result before context attachment;
- malformed orchestrator results become `INVALID_ORCHESTRATOR_RESULT` instead of raising or being mutated;
- legacy success fixtures now represent the real production contract with `error=False`;
- no new mutation/execution path is introduced.

## Architecture Review

Architecture Review Required: Yes.

Reason:

- existing application-entry and core orchestration contracts changed;
- package is execution-adjacent and exceeds the normal review threshold.

Critical Review Required: No.

Review result:

- constructor DI preserved;
- no new service/layer or competing architecture;
- no Product Decision/Product Task Draft execution;
- no Ozon mutation;
- no persistence owner change;
- no hidden network calls or runtime state;
- `data/users.json` untouched.

## SHA-bound verification evidence

### Entering verified main

- exact SHA: `de084ad62b251b1d308ece4fa36f7f70e585b4c9`
- push Verify #252
- tests: 1495 passed / 0 failed

### Failed intermediate feature SHA

- exact SHA: `3fd85c7eb6052ed4047e81b0a2571eca98702c02`
- push Verify #256
- tests: 1499 passed / 4 failed

The failures were legacy test fixtures that returned direct-runtime success payloads
without the explicit boolean `error` marker required by the hardened boundary.
The fixtures were corrected on later SHAs. This SHA remains failed evidence.

### Exact final feature head

- branch: `fix/entry-core-result-integrity-v597-v603`
- exact SHA: `4808e27661f869aeef59baca4d07035132f012c7`
- push Verify #260
- tests: 1503 passed / 0 failed
- artifact: `verification-4808e27661f869aeef59baca4d07035132f012c7`
- artifact digest: `sha256:22836898eee87f26725f6fb8b4b2ed9cd5c3ca7920dc1a0c302d82bdc3fb08da`

### PR synthetic merge-ref

- PR #250
- exact feature head: `4808e27661f869aeef59baca4d07035132f012c7`
- synthetic merge SHA: `6ea107c8c27def9a7531c19d725ee7e8fea25330`
- pull_request Verify #261
- tests: 1503 passed / 0 failed
- artifact: `verification-6ea107c8c27def9a7531c19d725ee7e8fea25330`
- artifact digest: `sha256:d14789f4f3d04fbfe2c262e20698326ad9edba3dd733b1289c73042df06ee2e2`

### Squash-main verification

- exact main SHA: `5131832339239f87886f9172f71cc1c0ec3553b4`
- push Verify #262
- tests: 1503 passed / 0 failed
- artifact: `verification-5131832339239f87886f9172f71cc1c0ec3553b4`
- artifact digest: `sha256:bfe98cd795f9b22933c7cdf3a510787d135356e31533f3a47383dff511d7849d`

## Verification semantics

- failed SHA evidence remains failed;
- feature push, PR merge-ref, and squash-main evidence remain distinct;
- no evidence is transferred between SHAs;
- workflow/test-manifest evidence is not claimed as independent external verification;
- `externally_verified=False`.
