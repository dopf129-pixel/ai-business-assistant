# Current Checkpoint v582-v590

Date: 2026-08-30

Package: Business Flow Result Integrity v1

## Verified implementation

The seller-facing `AssistantBusinessFlowService` now preserves downstream
failure semantics and fails closed on malformed intent, planner, task, and
execution result payloads.

Verified behavior:

- malformed intent payloads do not raise or become valid commands;
- explicit planner failures remain top-level failures;
- malformed planner actions/count cannot become successful empty plans;
- execution failure cannot receive optimistic “Действие выполнено” wording;
- malformed execution result cannot default to success;
- cancel/pause/resume failures do not receive success messages;
- malformed task reads fail closed;
- skip validates the selected action before mutation;
- committed skip plus later next-action read failure reports the actually skipped
  action and does not claim rollback;
- continue validates both next-action lookup and pending-action persistence;
- valid seller-facing result shapes remain compatible.

## Architecture Review

Architecture Review Required: Yes.

Reason:

- existing seller-facing, execution-adjacent orchestration contract changed;
- package exceeded the ~300-line review threshold.

Review result:

- constructor DI unchanged;
- no new service, executor, route, action type, or mutation path;
- no Product Decision/Product Task Draft execution enabled;
- no Ozon mutation introduced;
- no automatic retry or rollback;
- partial committed state is reported explicitly instead of hidden;
- `data/users.json` untouched.

## SHA-bound verification evidence

### Entering verified main

- exact SHA: `27b5ce3cb2904d98df1d75368876ad8e63866c0d`
- push Verify #213
- tests: 1462 passed / 0 failed

### Failed intermediate feature SHA

- exact SHA: `bac382c3c419e171d6b20c87c54fe4d41ffd8377`
- push Verify #223
- tests: 1483 passed / 1 failed
- artifact: `verification-bac382c3c419e171d6b20c87c54fe4d41ffd8377`
- artifact id: 9737428653
- artifact digest: `sha256:5c0cd46ffcd8cd560026cd2122ae509b20c071878a8ac003fd05b02e40ee37ba`

The failure was caused by a new test helper using `execution=None` both as a
malformed downstream payload and as “execution service absent”. Production code
was not the failing cause. This SHA remains failed evidence and is not promoted.

### Exact final feature head

- branch: `fix/business-flow-result-integrity-v582-v590`
- exact SHA: `5a2f25747ee73e4500c782b63d4c1ae042e0d27d`
- push Verify #224
- tests: 1484 passed / 0 failed
- artifact: `verification-5a2f25747ee73e4500c782b63d4c1ae042e0d27d`
- artifact id: 9737441027
- artifact digest: `sha256:2e8973b2eac8c4b02dd820530f2e33b874a7f747078aa9f63058cfdcd84155bd`

### PR synthetic merge-ref

- PR #246
- exact feature head: `5a2f25747ee73e4500c782b63d4c1ae042e0d27d`
- synthetic merge SHA: `4ec4deb23c0594949d55ed20d703abcb49c60d0d`
- pull_request Verify #225
- tests: 1484 passed / 0 failed
- artifact: `verification-4ec4deb23c0594949d55ed20d703abcb49c60d0d`
- artifact id: 9737451876
- artifact digest: `sha256:acd54235a87f8b7a9e815f99021d45ed5fb8e62468ff59c16720c24b213ed8c8`

This is synthetic merge-ref integration evidence, not exact-head proof.

### Squash-main verification

- exact main SHA: `b9fa039f626e230ac695162528f22b3ded5c093d`
- push Verify #226
- tests: 1484 passed / 0 failed
- artifact: `verification-b9fa039f626e230ac695162528f22b3ded5c093d`
- artifact id: 9737466539
- artifact digest: `sha256:af31c0c3b8926d05c096bd821c8cbe57068fc3eed559fa83667f82f0c2450508`

This exact squash-main SHA is the verified product baseline for this checkpoint.

## Verification semantics

- failed SHA evidence remains failed;
- feature push evidence applies only to the exact feature SHA;
- PR evidence applies only to the synthetic merge SHA;
- squash-main evidence applies only to the exact merged main SHA;
- no evidence is transferred between SHAs;
- none of these workflow runs is described as independent external verification.
