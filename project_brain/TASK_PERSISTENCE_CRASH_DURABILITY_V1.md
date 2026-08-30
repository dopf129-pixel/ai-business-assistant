# Task Persistence Crash Durability V1

Date: 2026-08-30  
Stages: v343-v352  
Architecture Review Required: Yes

## Goal

Strengthen crash durability of the existing task JSON persistence boundary after atomic rename.

Before this package the task file itself was flushed and fsynced before `os.replace`, and v333-v342 serialized writers with an exclusive lock. The remaining durability gap is the parent directory entry created/updated by the rename.

## v343 — Parent directory fsync

After the existing atomic save completes, the production owner opens the parent directory and calls `os.fsync` on the directory file descriptor.

For a task file in the current directory, `.` is used as the parent.

The directory is opened read-only, with `O_DIRECTORY` when the platform exposes it.

## v344 — Fsync inside persistence lock

Directory fsync occurs before the exclusive task write lock is released.

Critical ordering:

1. exclusive write lock;
2. exact source fingerprint check;
3. canonical serialization;
4. temp-file write + file fsync;
5. `os.replace`;
6. source fingerprint update;
7. parent directory fsync;
8. lock release.

## v345 — Durability warning semantics

A parent-directory fsync failure happens after the new task file is already visible through the successful atomic rename.

Therefore the operation must not be reported as a failed write and must not rollback to older state.

The public persistence state becomes:

- `last_save_state=SUCCEEDED_WITH_DURABILITY_WARNING`;
- `last_save_issue=TASK_DIRECTORY_FSYNC_ERROR`;
- `last_save_rolled_back=False`.

The caller still receives the normal successful task mutation result.

## v346 — No false rollback

Directory-fsync uncertainty is not treated as evidence that the new file was not written.

The owner keeps the new in-memory state and the new expected fingerprint.

## v347 — Continued exact concurrency

Because the new source fingerprint is updated from canonical serialized bytes immediately after the successful atomic write, the same instance can perform a later explicitly requested mutation even if the preceding directory fsync produced a durability warning.

No automatic retry is introduced.

## v348 — Non-sensitive failure evidence

Directory open/fsync failures collapse to the stable code `TASK_DIRECTORY_FSYNC_ERROR`.

Diagnostics do not expose:

- filesystem paths;
- exception strings;
- file descriptors;
- task contents;
- user IDs;
- credentials.

## v349 — Lock cleanup

A directory durability warning does not skip the write-lock release path.

The lock is still released in the outer `finally`.

## v350 — Independent degradation dimensions

Directory durability and write-lock release are separate evidence dimensions.

If both degrade after a committed write:

- the save remains committed;
- `last_save_issue` describes directory durability;
- `last_lock_release_issue` separately describes lock cleanup.

Neither warning is converted into a false pre-commit write failure.

## v351 — Diagnostics contract

Public persistence diagnostics expose `directory_fsync_required=True` but never the parent directory path.

## v352 — Safety boundary

Crash-durability handling never:

- executes a business action;
- retries a business mutation;
- calls Ozon;
- executes Product Decisions;
- executes Product Task Drafts;
- changes mapping authorization;
- changes financial calculations;
- touches `data/users.json`.

The feature is persistence evidence only.

## Scope and platform note

This contract strengthens the local POSIX-style filesystem persistence path used by the project. It does not claim distributed filesystem transactional guarantees.

A directory fsync warning means the rename succeeded in the running system but crash-survival durability could not be fully confirmed.

## Verification

Focused regressions cover:

1. actual directory fsync on successful save;
2. fsync while the write lock is held;
3. committed-write warning semantics;
4. no rollback after warning;
5. subsequent same-instance save;
6. non-sensitive directory-open failure;
7. lock cleanup after warning;
8. distinct durability and lock-release warnings;
9. public diagnostics contract;
10. no business-execution claim.

Full GitHub Actions verification is required before merge.
