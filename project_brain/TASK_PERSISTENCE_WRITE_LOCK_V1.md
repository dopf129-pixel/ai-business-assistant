# Task Persistence Write Lock V1

Date: 2026-08-30  
Stages: v333-v342  
Architecture Review Required: Yes

## Goal

Close the remaining time-of-check/time-of-use window in whole-file optimistic task persistence.

The v323-v332 fingerprint comparison prevents ordinary stale writers, but without serialization two processes could theoretically compare the same old fingerprint before either performs `os.replace`. This package adds an exclusive local write lock and performs the fingerprint comparison only while that lock is held.

## v333 — Exclusive write lock

Every production task save first creates `<task-file>.lock` with:

- `O_CREAT`;
- `O_EXCL`;
- `O_WRONLY`;
- mode `0600`.

An already-existing lock fails closed as `TASK_FILE_WRITE_LOCKED`.

The lock file is empty. It contains no PID, user ID, task contents, credentials, timestamps, or business evidence.

## v334 — One writer at a time

Only the service instance that successfully created the lock may enter the persistence critical section.

Contention does not wait, retry, steal, replace, or merge. The caller receives a stable failure and the in-memory mutation is rolled back from durable state.

## v335 — Private lock artifact

The lock is an internal persistence coordination artifact. It is not part of task state and is not included in public diagnostics.

No lock path is exposed.

## v336 — Check inside lock

The exact persisted-byte fingerprint comparison from v323-v332 occurs after lock acquisition.

The critical ordering is:

1. acquire exclusive lock;
2. read current durable fingerprint;
3. compare with the instance source fingerprint;
4. serialize the intended state;
5. execute the existing atomic temp/fsync/`os.replace` save;
6. update the expected source fingerprint;
7. release the lock.

This removes the previous check/write TOCTOU window for writers that honor this production owner contract.

## v337 — Serialization failure

Canonical JSON serialization is attempted inside the lock before the atomic write.

If task state is not serializable:

- no durable task write occurs;
- the in-memory mutation is discarded by reloading the durable store;
- the stable code is `TASK_FILE_SERIALIZATION_ERROR`;
- the lock is released.

## v338 — Lock acquisition failure

Unexpected lock creation failures fail closed as `TASK_FILE_WRITE_LOCK_ERROR`.

Exception text, paths and OS details are not exposed through diagnostics.

## v339 — Release degradation after durable success

A lock-release error after a successful durable task write must not turn that already-committed write into a false failure.

The save remains `SUCCEEDED` and diagnostics record `TASK_FILE_WRITE_LOCK_RELEASE_ERROR`.

No automatic lock deletion retry is attempted.

## v340 — Missing lock on release

If the lock disappears before release, the already-completed durable write remains successful.

Diagnostics record `TASK_FILE_WRITE_LOCK_MISSING`.

## v341 — Normal cleanup

A normal successful save removes the lock and leaves:

- `write_lock_guard=True`;
- `last_lock_release_issue=None`;
- the optimistic fingerprint guard enabled.

## v342 — Safety boundary

The lock protocol never:

- retries a business action;
- executes recovered intent;
- performs Product Decision execution;
- performs Product Task Draft execution;
- calls Ozon;
- changes mapping authorization;
- changes finance calculations;
- touches `data/users.json`.

There is deliberately no automatic stale-lock reclamation. If a process dies while holding a lock, ownership cannot be proven safely from the current contract, so a remaining lock fails closed until an operator resolves the persistence artifact.

## Scope

This is local filesystem serialization for the existing task JSON persistence boundary. It is not presented as a distributed database transaction or a network filesystem lease.

All writers must use the production terminal-safe task owner for this guarantee to hold.

## Verification

Focused regressions cover:

1. contention before atomic replace;
2. exclusivity between live instances;
3. private empty `0600` lock artifact;
4. fingerprint check while lock is held;
5. serialization rollback;
6. stable acquisition failure;
7. release failure after durable success;
8. missing lock on release;
9. normal cleanup;
10. no business-execution claim or automatic retry.

Full GitHub Actions verification is required before merge.
