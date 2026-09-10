# Period Profit tenant-dynamic tax reconciliation — 2026-09-10

## Production basis

Code PR: #499 — `Resolve Period Profit tax policy per tenant request`.

- base main: `089b16399a7d12c13545bba597055a4371014ff3`
- published feature head: `6abbc4715a3e25905a96853e79d505945c29e7c4`
- PR synthetic merge SHA: `04ccaca1aca619e6ad9bb262e71c00adb004bd4d`
- resulting production main after squash merge: `ad3989504f5d9a6d76b7b87bf972f786bcd208a7`

Codex reported an internal task SHA `c6e46b8f626ab686f8ff72ed515df7e53edb07f9`; the GitHub-published feature head is the canonical revision for repository verification.

## Implemented contract

`TaxConfigurationService` is now injected into the Period Profit analytics graph as a live dependency. `BusinessAnalyticsService.calculate()` resolves tax policy from that service on each calculation, which means a long-lived analytics object can serve seller A, then seller B, then seller A again without reusing the first seller's materialized tax policy.

The dynamic path is used when `tax_configuration_service` is supplied. Existing direct construction remains backwards-compatible: when no dynamic service is supplied, constructor-provided `tax_mode`, `tax_rate`, and `minimum_tax_rate` remain the fixed fallback path.

`StoreAnalyticsService` forwards the tax configuration service to `BusinessAnalyticsService`. `create_telegram_core()` wires the production `TaxConfigurationService` instance into `StoreAnalyticsService` rather than relying only on the configuration snapshot read while the core is constructed.

## Regression coverage

The focused regression reuses one long-lived `StoreAnalyticsService` instance while switching tenant context A → B → A. Tenant A is configured with 6% and tenant B with 15%; the asserted tax rates and tax amounts switch 6% → 15% → 6% correspondingly.

Factory coverage additionally asserts that the production analytics graph receives the same `TaxConfigurationService` instance returned by `create_telegram_core()`.

## Verification chain

- feature-head Verify #1807: completed/success on `6abbc4715a3e25905a96853e79d505945c29e7c4`
- feature artifact: `verification-6abbc4715a3e25905a96853e79d505945c29e7c4`
- feature artifact digest: `sha256:52b7f4f4a65bb3736054418422eea84f5155eb12c195a3c20f1ff40938342110`
- PR synthetic Verify #1808: completed/success; artifact revision `04ccaca1aca619e6ad9bb262e71c00adb004bd4d`
- PR synthetic artifact: `verification-04ccaca1aca619e6ad9bb262e71c00adb004bd4d`
- PR synthetic artifact digest: `sha256:33937b2b3c974a2e3dc46c95b98b7e1c3fc70b8f05b48788534e5fd660c978f4`
- resulting main Verify #1809: full test suite completed successfully on `ad3989504f5d9a6d76b7b87bf972f786bcd208a7`
- resulting main artifact: `verification-ad3989504f5d9a6d76b7b87bf972f786bcd208a7`
- resulting main artifact digest: `sha256:01eeb972ada9d76361090b9aec3d724af2366a614333725dbaf566b95e52e627`

## Boundaries and remaining audit items

This package closes the identified Period Profit analytics tax-policy capture bug. It does not claim that every tax-consuming object in the wider Telegram graph is tenant-dynamic. In particular, `ProductUnitEconomicsProvider` is still constructed from the factory-time `tax_policy` snapshot and remains a separate multi-tenant audit item.

Return COGS repository schema initialization under tenant context also remains a separate audit item. This package does not change Return COGS state semantics or accounting execution behavior.

## Safety invariants preserved

- Ozon integration remains READ-ONLY.
- `ReturnedToOzon` is candidate evidence only and is not proof of `SALEABLE_RESTORED`.
- unknown values are not treated as zero.
- Return COGS is not inferred from guessed quantity × cost.
- accounting facts are not automatically created.
- seller-facing Period Profit remains read-only/non-executing.
- commit readiness is not commit execution.
- final application observability does not authorize repeat commit.
- downstream inventory presentation is authoritative only when `inventory_recovery_evidence_status == "RETURN_INVENTORY_RECOVERY_READY"` and recovery state is `SALEABLE_RESTORED` or `NON_SALEABLE`.
- the historical warning `8 unresolved` must not be conflated with `785 exact raw Returns API records`; no return identities are invented.
