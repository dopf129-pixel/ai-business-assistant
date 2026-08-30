# Optimistic Task Persistence Concurrency V1

Date: 2026-08-30  
Stages: v323-v332  
Architecture Review Required: Yes

## Goal

Prevent two live production task-service instances from silently overwriting a newer durable task store.

The contract is optimistic concurrency at the whole-file persistence boundary. It does not introduce distributed locking, automatic retry, background recovery, task execution, Product Decision execution, Product Task Draft execution, or Ozon mutation.

## v323 — Source fingerprint

On load, the production owner computes a SHA-256 fingerprint from the exact persisted bytes.

The fingerprint is internal concurrency evidence only. It is never exposed through public diagnostics.

An absent file is represented by an internal `None` source fingerprint.

## v324 — Pre-write compare

Before every save, the owner reads the current durable file bytes and computes the current fingerprint.

The write is eligible only when the current fingerprint exactly equals the fingerprint observed by this service instance.

No fuzzy comparison, timestamps, mtimes, or inferred freshness are used.

## v325 — Absent-file race

Two instances may both start from an absent store.

After the first instance creates the store, the second instance has stale `None` evidence and must fail closed rather than overwrite the new file.

## v326 — Stale writer rejection

A mismatch raises `TASK_FILE_STALE_WRITE` before the atomic write primitive is reached.

There is no automatic retry and no hidden merge.

## v327 — Durable-state rollback

After a stale-write rejection, the owner reloads the current durable store using the existing fail-closed loader.

Any unpersisted in-memory mutation is discarded.

## v328 — External corruption/deletion

Deletion or byte-level replacement of the source file changes the exact persistence evidence.

A subsequent stale writer fails closed and reloads the resulting source state, including `ABSENT` or `UNREADABLE`.

## v329 — Concurrency-check read failure

Failure to read the current durable bytes fails closed as `TASK_FILE_CONCURRENCY_CHECK_ERROR`.

Diagnostics do not expose exception text, file paths, task contents, user identifiers, or fingerprints.

## v330 — Successful writer refresh

The expected fingerprint for a successful write is computed from the same canonical JSON serialization used by the existing atomic persistence primitive:

- UTF-8;
- `ensure_ascii=False`;
- `indent=4`.

It is computed before the write. Therefore a successful `os.replace` does not require a second read and cannot become ambiguous because a post-write fingerprint read fails.

## v331 — Diagnostics

Public persistence diagnostics expose only:

- guard enabled;
- stable load/save state;
- stable issue code;
- rollback flag;
- loaded task count;
- read-only diagnostic marker;
- `executed=False`.

The raw fingerprint remains private.

## v332 — Safety boundary

Concurrency handling never:

- retries a business action;
- merges task state automatically;
- executes recovered intent;
- calls Ozon;
- recomputes Product Decisions;
- executes Product Task Drafts;
- changes mapping authorization;
- changes financial calculations;
- touches `data/users.json`.

A stale writer must explicitly reload through the fail-closed path before any later caller-driven mutation can succeed.

## Verification

Focused regression coverage includes:

1. non-sensitive diagnostics;
2. two live writers against the same existing store;
3. two live writers starting from an absent store;
4. no atomic replace on stale rejection;
5. external deletion;
6. external corruption;
7. concurrency-check read failure;
8. repeated writes by the same fresh instance;
9. hidden fingerprint evidence;
10. no business-execution claim.

Full GitHub Actions verification is required before merge.
