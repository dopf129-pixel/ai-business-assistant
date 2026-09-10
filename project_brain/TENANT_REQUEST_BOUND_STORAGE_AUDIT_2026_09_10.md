# Tenant request-bound storage audit — 2026-09-10

## Production basis

This checkpoint documents production code merged as:

- `main`: `c0a7536be235fb39d0b98e0174a6449a7acd7941`
- feature head: `6ee7861d045e5a2e7546261eda9781e561e395ca`
- PR #497 synthetic merge: `8f92aed2827225a5b0df7af19c28889975eee3ca`

The package extends tenant isolation from the core Ozon/Return COGS repositories to seller-specific JSON-backed assistant state and hardens shared-service behavior across Telegram requests.

## Request-bound late binding

Telegram request handling already binds the current user through `services.tenant_context` before dispatch and resets the ContextVar afterwards. The audit found that several storage services resolved their default path at construction time. A service instance created before request dispatch could therefore retain a legacy/global path even while later operations ran inside a tenant context.

The corrected contract is:

- default seller-specific paths are resolved at operation time from the current tenant context;
- one shared service instance may safely serve sequential requests from different tenants;
- explicit custom paths remain fixed and are not silently rewritten;
- when no tenant context exists, the legacy path is preserved.

## Storage covered by this package

Late-bound tenant defaults now cover:

- `actions.json`;
- `assistant_memory.json`;
- `assistant_session.json`;
- `assistant_user_memory.json`;
- `conversation_history.json`;
- `data/product_decision_history.json`;
- `store_reports.json`;
- default `data/tax_configuration.json`.

Tenant-local paths continue to use `data/tenants/<sha256-prefix>/<basename>` through `tenant_storage_path(...)`.

`AssistantUserStorageService` / `data/users.json` was not mechanically converted in this batch: that store is a global multi-user profile index keyed by user id, so its ownership semantics differ from seller-local request state. This preserves the rule that tenant isolation is applied according to data ownership rather than filename alone.

## Tax configuration

`TaxConfigurationService` now keeps only an explicitly supplied `file_path` fixed. With the default path, each `get_policy()` or `save_policy()` operation resolves the current tenant path. This prevents a long-lived/shared configuration service from pinning the path belonging to the context in which the object happened to be constructed.

This storage fix does not claim that every higher-level analytics object already refreshes a tax policy that was materialized earlier during graph construction. Factory/runtime tax-policy materialization remains a separate audit item and must be verified before claiming the entire long-lived Period Profit graph is tenant-dynamic.

## Regression coverage

`tests/test_multi_tenant_request_bound_storage.py` proves that the same storage-service instance can be reused for seller A and seller B without cross-user reads or writes. It also verifies explicit custom path compatibility and the legacy no-tenant defaults.

## Safety and accounting boundaries

This package changes local storage selection only.

- Ozon remains READ-ONLY.
- `ReturnedToOzon` remains candidate evidence only, never proof of `SALEABLE_RESTORED`.
- `unknown != zero`.
- Return COGS is not inferred from guessed quantity × cost arithmetic.
- No accounting fact is synthesized from storage presence.
- seller-facing Period Profit remains read-only/non-executing.
- commit readiness remains distinct from commit execution.
- final application observability does not authorize repeat execution.
- canonical status and boolean gates remain jointly enforced downstream.

## Verification chain

- feature head `6ee7861d045e5a2e7546261eda9781e561e395ca` — Verify #1799 passed; artifact `verification-6ee7861d045e5a2e7546261eda9781e561e395ca`, digest `sha256:e7f4ac7b0da823584704366ccbf583704953206adf30952a6cc0957ad5504079`;
- PR #497 synthetic merge `8f92aed2827225a5b0df7af19c28889975eee3ca` — Verify #1800 passed; artifact `verification-8f92aed2827225a5b0df7af19c28889975eee3ca`, digest `sha256:d0d7bb88103641d1995c901ffc081d3ab9818ab9d73ea8b58dd4bc5d9103a190`;
- production code `c0a7536be235fb39d0b98e0174a6449a7acd7941` — Verify #1801 passed; artifact `verification-c0a7536be235fb39d0b98e0174a6449a7acd7941`, digest `sha256:7e76d7625e771e6cda1342c38ab4e3ccc74d92156aa52b504fb449ed38ba17c6`.

The docs branch, docs synthetic merge, and final `main` verification complete the lifecycle after this checkpoint is merged.
