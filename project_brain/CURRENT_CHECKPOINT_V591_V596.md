# Current Checkpoint v591-v596

Date: 2026-08-30

Package: Top-Level Result Integrity v1

## Verified implementation

The seller-facing upper orchestration chain now preserves failure semantics across
`AssistantOrchestratorBusinessService`, `AssistantMainFlowService`, and
`AssistantResponseBuilderService`.

Verified behavior:

- malformed Business Flow results fail closed instead of becoming success;
- missing/non-boolean top-level `error` cannot be treated optimistically;
- explicit execution `error=True` remains a top-level failure;
- safe execution failure messages remain visible without changing the failure state;
- malformed execution payloads cannot receive “Действие выполнено” wording;
- nested task status/history/details/next failures cannot become successful reads;
- business-plan actions/count consistency is checked at the upper orchestration boundary;
- malformed business-service results no longer raise `KeyError`;
- malformed response-service results fail closed;
- explicit upstream errors are preserved by the response builder;
- cancelled-task execution is represented as failure rather than a false successful state;
- valid existing seller-facing success shapes remain compatible.

## Architecture Review

Architecture Review Required: Yes.

Reason:

- existing seller-facing execution-adjacent service contracts changed;
- the meaningful package exceeded the ~300-line review threshold.

Critical Review Required: No.

Review result:

- constructor dependency injection remains unchanged;
- no new production service/layer or competing architecture was introduced;
- no new action type, executor, route, or business mutation path was added;
- no Product Decision or Product Task Draft execution was enabled;
- no Ozon mutation was wired;
- no persistence owner was added or changed;
- no automatic retry, fake rollback, or hidden side effect was introduced;
- `data/users.json` was not changed.

## SHA-bound verification evidence

### Entering verified main

- exact SHA: `6b857ea34b654efae8b40eb554881d7c87f2dd22`
- push Verify #234
- tests: 1484 passed / 0 failed
- artifact: `verification-6b857ea34b654efae8b40eb554881d7c87f2dd22`
- artifact digest: `sha256:53d05dde9491007645866dc12752c3ce7d789f55ede0d0b96e2549e44c20359f`

### Failed intermediate feature SHA

- exact SHA: `9f90b8055f6e95c9d7037e392dbf6c7629dec044`
- push Verify #239
- tests: 1493 passed / 2 failed
- artifact: `verification-9f90b8055f6e95c9d7037e392dbf6c7629dec044`

This SHA remains failed evidence. The failures were:
1. a stale legacy test expected `error=False` after attempting execution of a
   cancelled task, conflicting with the failure-integrity invariant;
2. the first upper-orchestrator implementation preserved failure state but failed
   to lift the nested execution failure message, causing a seller-facing response
   shape regression.

Both were corrected only on a later commit. The successful later verification is
not transferred back to this failed SHA.

### Exact final feature head

- branch: `fix/top-level-result-integrity-v591-v596`
- exact SHA: `ff41b6b9aec7804e329453a669bd0c2becfe60a4`
- push Verify #241
- tests: 1495 passed / 0 failed
- artifact: `verification-ff41b6b9aec7804e329453a669bd0c2becfe60a4`
- artifact digest: `sha256:03f94bfe3f99722c60d3ade2b2c900571000e802e71939ee8d28efeab3e49c50`

### PR synthetic merge-ref

- PR #248
- exact feature head: `ff41b6b9aec7804e329453a669bd0c2becfe60a4`
- synthetic merge SHA: `432e33d77a02aaaab0ebc499eb05f7a1c6302603`
- pull_request Verify #242
- tests: 1495 passed / 0 failed
- artifact: `verification-432e33d77a02aaaab0ebc499eb05f7a1c6302603`
- artifact digest: `sha256:8fc59e7303a57497c38240975ccab850ff1b73ec718b6df3b032a135bccdfb78`

This is integration evidence for the synthetic merge ref, not exact feature-head
proof and not final squash-main proof.

### Squash-main verification

- exact main SHA: `6555245c816051024040fa81382773a530279f32`
- push Verify #243
- tests: 1495 passed / 0 failed
- artifact: `verification-6555245c816051024040fa81382773a530279f32`
- artifact digest: `sha256:654d11258342ab7f0639229b670c315e550442f68f8e56378d2dac2c04a3ce56`

This exact squash-main SHA is the verified product baseline for this checkpoint.

## Verification semantics

- failed SHA evidence remains failed;
- feature push evidence applies only to the exact feature SHA;
- PR evidence applies only to the synthetic merge SHA;
- squash-main evidence applies only to the exact merged main SHA;
- a generated test manifest is not by itself proof of workflow success;
- no evidence is transferred between SHAs;
- these GitHub workflow runs are not claimed as independent external verification;
- `externally_verified=False`.
