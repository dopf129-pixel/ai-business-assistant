# Multi-tenant stage completion — 2026-09-10

## Status

The multi-user / multi-tenant isolation milestone is complete for the currently audited seller-owned state and request-bound service paths.

Production code commit: `4b4746c9971e67c599f2cbb23a0ebab7eb81ed8a`.

## Completed scope

- Request-bound tenant storage remains late-bound instead of being captured at process/factory construction time.
- `tenant_storage_path()` is now a pure path resolver and does not create directories during lookup; actual write/database-open paths create parents explicitly.
- Core SQLite storage initializes schema in the active tenant database.
- Product cost storage remains tenant-local.
- Expense storage defaults to the active tenant while explicit custom database paths remain request-independent.
- Return COGS inventory recovery, attribution, recognition, authorization, and commit repositories initialize their schemas in each active tenant database.
- Product Decision history and action-task draft in-memory caches are partitioned by storage identity to prevent A→B leakage in long-lived service instances.
- Product Unit Economics resolves tax configuration per active tenant at operation time; explicitly supplied fixed tax constructor settings keep backward-compatible behavior when no dynamic tax configuration service is supplied.
- Period Profit tenant-dynamic tax behavior already present on main remains preserved.
- End-to-end A/B acceptance coverage validates tax, product cost, expenses, Return COGS recovery, Product Decision history, physical SQLite separation, and no-tenant legacy isolation.

## Intentional globals / compatibility

`AssistantUserStorageService` and `data/users.json` remain a global multi-user index keyed by user id. Global indexes, system configuration, and development tooling are not seller-owned tenant state and remain outside tenant-local storage.

Without an active tenant, legacy/default paths continue to work for backward compatibility. Explicit caller-provided storage paths also remain explicit and are not silently tenant-localized.

## Safety invariants retained

- Ozon integration remains READ-ONLY.
- `ReturnedToOzon` remains candidate evidence only and is not proof of `SALEABLE_RESTORED`.
- Unknown values are not treated as zero.
- Return COGS is not guessed from quantity × cost when exact evidence is unavailable.
- Accounting facts are not auto-created.
- Seller-facing Period Profit remains read-only/non-executing.
- Commit readiness is distinct from commit execution.
- Final application observability does not permit repeated commit.
- Downstream readiness requires the canonical status and corresponding boolean jointly.
- Inventory recovery is presentation-authoritative only when `inventory_recovery_evidence_status == "RETURN_INVENTORY_RECOVERY_READY"` and recovery state is `SALEABLE_RESTORED` or `NON_SALEABLE`.
- Historical warning `8 unresolved` must not be conflated with `785 exact raw Returns API records`; identities must not be invented.

## Verification

PR #501 was conflict-resolved by preserving both the prior Period Profit tenant-dynamic tax regression coverage and the new completion-storage / Product Unit Economics coverage.

PR synthetic merge SHA: `6c411c7fa22de72cb205a1502206022db6bb92fe`.

PR Verify #1817: success. Artifact: `verification-6c411c7fa22de72cb205a1502206022db6bb92fe`. Digest: `sha256:46b28d520fecda6e4588bb8e28b58b81abcefeb089f1e85a6998cbfabda7071f`.

Production main Verify #1818: success. Artifact: `verification-4b4746c9971e67c599f2cbb23a0ebab7eb81ed8a`. Digest: `sha256:b8a024fd66ad34874ae647489c69f722eee3cb0282c9c0b5031fe378cd331e66`.
