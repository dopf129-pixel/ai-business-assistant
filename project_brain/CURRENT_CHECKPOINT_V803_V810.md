# CURRENT_CHECKPOINT_V803_V810

Date: 2026-08-31

## Telegram Adapter Runtime Exception Containment

Production package:

`v803-v810: Telegram Adapter Runtime Exception Containment`

Goal:

Prevent seller-facing Telegram failures from leaking internal exceptions while preserving fail-closed semantics.

## Preserved invariants

- No retry after an internal exception.
- Legacy handler arity selection remains pre-call only.
- One invocation remains one invocation.
- Internal exception text is not exposed to sellers.
- Explicit downstream failures remain failures.
- No Product Decision execution.
- No Product Task Draft execution.
- No Ozon mutation.
- No quantity or price inference.
- `data/users.json` unchanged.

## SHA-bound verification evidence

Entering exact main:

- SHA: `ad3692c46e31d4eceeef504e4b55d7cbaa829a09`
- Verify #482
- 1703 passed / 0 failed

Cancelled evidence:

- Verify #483
- cancelled
- not transferable evidence

Failed intermediate:

- SHA: `c3336160fccddbc25a9d8e2b1f7aeccccaa8be70`
- Verify #484
- 1710 passed / 1 failed
- Failed permanently.

Cause:

A stale test expected internal button TypeError propagation. The no-retry invariant remained valid. The new SHA updated the stale expectation without weakening production containment.

Final feature head:

- SHA: `21776a8cdd61dd35e28a885b5c573a2db3b15c92`
- Verify #485
- 1711 passed / 0 failed

PR synthetic merge-ref:

- SHA: `929a1bd4c8ace607ff0bf6c67924aa14ec84b612`
- PR #296 Verify #486
- 1711 passed / 0 failed

Squash main:

- SHA: `01300c69d1ab54731657ea741687cc728c9e5600`
- Verify #487
- 1711 passed / 0 failed

## Review classification

Architecture Review Required: Yes

Critical Review Required: No

GitHub Actions evidence is project CI evidence only.

`externally_verified=False`.
