# Task Persistence Kernel Lock V2

Date: 2026-08-30  
Stages: v378-v387  
Architecture Review Required: Yes

## Goal

Replace orphan-prone lock-file ownership with a kernel-backed advisory lock while preserving the existing exact-fingerprint, atomic-write and crash-durability boundaries.

The previous v333-v342 implementation used `O_CREAT | O_EXCL` as both the coordination artifact and the ownership primitive. If a process died after creating the lock file, the file could remain and block every later writer even though no owner was alive.

This package removes that failure mode without introducing automatic lock-file deletion.

## v378 — Kernel-backed ownership

The production task owner uses POSIX `fcntl.flock` with:

- `LOCK_EX`;
- `LOCK_NB`.

The lock file is opened with `O_CREAT | O_RDWR` and mode `0600`.

The open file descriptor, not file existence, is the ownership evidence.

## v379 — Stable coordination artifact

The lock file is intentionally persistent and empty.

It contains no:

- PID;
- user ID;
- timestamps;
- task contents;
- credentials;
- owner token.

A successful release does not unlink the file.

This avoids unlink/recreate inode races between concurrent writers.

## v380 — Live contention

If another live file descriptor owns the kernel lock, acquisition fails immediately.

The existing stable failure remains:

`TASK_FILE_WRITE_LOCKED`

No waiting, automatic retry or state merge is introduced.

## v381 — Crash-like release

Kernel ownership is released when the owning file descriptor is closed.

Therefore process termination does not require deleting a stale file before a later writer can proceed.

A leftover coordination file is inert ownership-wise.

## v382 — Honest diagnostics

The operator lock diagnostics no longer infer active ownership from file presence.

Canonical states are:

- `SELF_HELD`: this service instance currently owns its kernel lock fd;
- `NO_ACTIVE_LOCK_EVIDENCE`: this instance does not own a lock and diagnostics intentionally do not probe another process by temporarily acquiring a lock;
- `CHECK_ERROR`: lock diagnostics cannot be established safely.

`NO_ACTIVE_LOCK_EVIDENCE` is not a claim that another process definitely has no lock.

The diagnostic route deliberately avoids a probing flock because a read-only status request must not transiently block a real writer.

## v383 — Orphan artifact compatibility

An empty lock file left by the old `O_EXCL` protocol no longer blocks writes.

No automatic deletion is needed.

The artifact remains:

- path-hidden in public diagnostics;
- non-stale evidence;
- non-owner evidence.

## v384 — Operator blocker source

Operator readiness no longer blocks on coordination-file presence.

A lock contention blocker comes from actual save evidence:

`TASK_FILE_WRITE_LOCKED`

The operator action becomes:

`WAIT_FOR_ACTIVE_WRITER_AND_RETRY_MANUALLY`

This does not authorize automatic retry or lock deletion.

## v385 — Unsupported kernel primitive

If `fcntl.flock` is unavailable, task persistence fails closed through the existing write-lock error boundary.

The system does not silently fall back to unguarded writes.

Lock diagnostics become `CHECK_ERROR` with `kernel_lock_guard=False`.

## v386 — Release degradation

Unlock failure is reported separately as:

`TASK_FILE_WRITE_LOCK_RELEASE_ERROR`

The fd is still closed in the release path, so the OS can release ownership.

A release warning after a durable write does not turn that committed write into a false failure.

## v387 — Safety boundary

Kernel-lock hardening never:

- deletes a coordination file automatically;
- retries a business operation automatically;
- infers lock owner, PID, age or stale state;
- executes recovered intent;
- executes Product Decisions;
- executes Product Task Drafts;
- mutates Ozon;
- changes mapping authorization;
- changes financial calculations;
- enables business execution.

Public operator flags remain:

- `automatic_lock_recovery_allowed=False`;
- `manual_lock_removal_allowed=False`;
- `business_execution_ready=False`;
- `mutation_ready=False`;
- `executed=False`.

## Ordering

The critical write path remains:

1. acquire kernel-backed exclusive lock;
2. compare exact persisted-byte source fingerprint;
3. canonical JSON serialization;
4. temp-file write;
5. file flush + fsync;
6. atomic `os.replace`;
7. update expected source fingerprint;
8. parent-directory fsync;
9. unlock and close kernel lock fd.

## Scope

This is a POSIX local-filesystem advisory-lock contract.

It is not presented as a distributed lock or network-filesystem lease.

All task writers must continue to use the hardened production task owner for the guarantee to hold.

## Verification

Focused regressions cover:

1. supported kernel primitive;
2. stable private coordination artifact;
3. live cross-instance contention;
4. fd-close crash-like release;
5. self-held diagnostics;
6. orphan artifact compatibility;
7. operator blocker from real contention;
8. unsupported primitive fail-closed;
9. unlock degradation with fd close;
10. no business execution or auto-delete permission.

Full GitHub Actions verification is required before merge.
