# Current Checkpoint v629-v637

Date: 2026-08-30

Package: User Storage Atomic Write Integrity v1

## Verified implementation

The existing user-storage owner now commits writes through a same-directory temporary file, flushes and fsyncs temporary content before commit, and atomically replaces the target with `os.replace`.

Verified behavior:

- serialization completes before the target file is touched;
- temporary writes occur in the target directory;
- temporary content is flushed and fsynced before replace;
- pre-commit write/fsync/replace failures preserve the existing target;
- temporary files are cleaned after pre-commit failures;
- an already-committed replace is not represented as rolled back when directory fsync fails;
- post-replace directory fsync failure returns a durability warning with `error=False`;
- `save_memory` and `add_history` roll back only uncommitted in-memory changes on pre-commit persistence failure;
- repository `data/users.json` remains untouched by the package.

## Architecture Review

Architecture Review Required: Yes.

Reason:

- persistence commit semantics changed inside the existing storage owner;
- the package crosses a meaningful integrity boundary and requires explicit review.

Critical Review Required: No.

Review result:

- existing persistence owner hardened in place;
- no additional persistence layer;
- no false rollback after an atomic replace already committed;
- no Product Decision/Product Task Draft execution;
- no Ozon mutation;
- no business execution capability added;
- no path/PID/secret exposure;
- `data/users.json` untouched.

## SHA-bound verification evidence

### Entering verified main

- exact SHA: `574c7199c1a08e889452b0f604ef470d98bf7de3`
- push Verify #314
- tests: 1528 passed / 0 failed
- artifact: `verification-574c7199c1a08e889452b0f604ef470d98bf7de3`
- artifact digest: `sha256:0abe8889938b0a2190b75e03dbe872443db94ca3c4caa937c3a678622dcbddc9`

### Exact final feature head

- branch: `fix/user-storage-atomic-write-integrity-v629-v637`
- exact SHA: `0b7ac4145d8ea0772debd41b30d644fbaa2f8150`
- push Verify #317
- tests: 1537 passed / 0 failed
- artifact: `verification-0b7ac4145d8ea0772debd41b30d644fbaa2f8150`
- artifact digest: `sha256:604cd811466e39fb1880c1f3d7c5cbf03f163f33017e0432de9dc5cab78c0d9c`

### PR synthetic merge-ref

- PR #258
- exact feature head: `0b7ac4145d8ea0772debd41b30d644fbaa2f8150`
- synthetic merge SHA: `926cb40e84d27041c25121901fd7bb59e7ec89e0`
- pull_request Verify #318
- tests: 1537 passed / 0 failed
- artifact: `verification-926cb40e84d27041c25121901fd7bb59e7ec89e0`
- artifact digest: `sha256:277bddf0e5b6ae885378222ade110531c4a94e9800fbd291da42ea7c1ea3cd7f`

### Squash-main verification

- exact main SHA: `05f6546cf4110ff5a507f4fb145599e4f842dd7a`
- push Verify #319
- tests: 1537 passed / 0 failed
- artifact: `verification-05f6546cf4110ff5a507f4fb145599e4f842dd7a`
- artifact digest: `sha256:c064fb52968d03d0d94151c6b272a96929d89d714f798b11c0f7271cff521ba0`

## Verification semantics

- feature push, synthetic merge-ref, and squash-main evidence remain distinct;
- no evidence is transferred between SHAs;
- workflow/test-manifest evidence is not independent external verification;
- `externally_verified=False`.
