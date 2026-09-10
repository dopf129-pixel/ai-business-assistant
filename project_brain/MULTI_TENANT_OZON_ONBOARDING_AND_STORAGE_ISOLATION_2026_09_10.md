# Multi-tenant Ozon onboarding and seller storage isolation — 2026-09-10

## Production basis

This checkpoint documents the production code merged as:

- `main`: `1f017a3a506abb457615706cef75e56238c44303`
- feature head: `df1e7cf7c91cdcd69a4f648577841f84a4fd2f8f`
- PR #495 synthetic merge: `49cc5f0804c2e1e9c71604b7c79b06c498e3a614`

The package introduces per-Telegram-user Ozon account onboarding and extends tenant isolation to seller-local operational and accounting storage. It does not broaden Ozon permissions and does not weaken Return COGS evidence gates.

## Tenant request context

`services.tenant_context` uses a `ContextVar` to bind the current Telegram user to the active request. Telegram request handling sets this context before dispatch and resets it afterwards.

The context is request-scoped. Repository code must resolve the current tenant at connection/open time rather than capture a user globally at import time.

## Tenant-local storage path

`services.tenant_storage.tenant_storage_path(...)` maps a storage filename to:

`data/tenants/<sha256-prefix>/<basename>`

when a tenant is present.

The directory component is derived from a SHA-256 digest prefix of the user identifier. Raw Telegram/user identifiers are therefore not used as directory names.

When no tenant context exists, the helper returns the supplied legacy path unchanged. This preserves existing non-Telegram/test/admin compatibility and does not imply an automatic migration of pre-existing global seller data into tenant directories.

## Ozon account onboarding

The package adds:

- encrypted per-user Ozon credential persistence;
- tenant-aware credential resolution;
- Telegram commands for connect/status/disconnect;
- request binding so a user can resolve only that user's connected account;
- explicit behavior where a tenant with no stored account does not fall back to another seller's credentials.

Ozon API keys are encrypted at rest by the account repository. Credential connection validation does not grant any new Ozon mutation capability.

## Seller-local data isolated by tenant

The tenant boundary now covers the seller-facing local state used by the current application path:

- core local SQLite product data;
- product cost and cost-history storage;
- Return inventory recovery evidence;
- Return COGS accounting attribution evidence;
- Return COGS accounting recognition history;
- Return COGS profit-application authorization history;
- Return COGS exact-once commit ledger;
- external seller expenses and expense coverage;
- the default local tax configuration file.

Each tenant receives an independent local SQLite database/path namespace. Identical natural business identifiers or independent integer history IDs in two tenants do not cause cross-user reads or uniqueness collisions.

## Return COGS controlled commit

Tenant isolation does not change the controlled-commit semantics. Recognition, authorization, and commit history for one tenant reside in the same tenant-local database, so the existing `BEGIN IMMEDIATE` revalidation can still validate the current recognition and authorization chain atomically before an append.

The following distinctions remain mandatory:

- recognition evidence is not authorization;
- authorization is not commit readiness;
- commit readiness is not commit execution;
- a committed record is not permission to repeat a commit;
- final seller-facing Period Profit application remains governed by the existing canonical status+boolean chain and final integrity checks.

## Accounting and Return COGS boundaries

Tenant isolation is only a storage/security boundary. It is not accounting evidence.

In particular:

- `ReturnedToOzon` remains candidate evidence only and is not proof of `SALEABLE_RESTORED`;
- `unknown != zero`;
- Return COGS must not be inferred from guessed `quantity × cost` arithmetic;
- inventory recovery, exact identity/quantity, accounting attribution, compensation/no-double-count clearance, recognition, authorization, commit, and final application gates remain fail-closed;
- seller/accounting facts are not synthesized merely because a tenant storage location exists.

## Ozon safety boundary

Ozon remains READ-ONLY for this project package. The onboarding work changes credential selection and local persistence only. It does not add seller-account mutation, posting mutation, inventory mutation, advertising mutation, price mutation, or any other Ozon write path.

Seller-facing Period Profit / Return COGS observability remains non-executing except for the already-controlled local accounting evidence/commit mechanisms whose semantics were established separately. No new Ozon execution authority is introduced here.

## Compatibility and migration boundary

No automatic migration of historical contents from the legacy global `ozon_assistant.db` or legacy tax configuration into a tenant directory is claimed by this package.

Compatibility behavior is explicit:

- with tenant context: use tenant-local storage;
- without tenant context: preserve the legacy supplied/default path.

A future migration, if required, must be an explicit identity-aware operation. Historical global rows must not be assigned to tenants by guessing ownership.

## Regression coverage

The package includes cross-user regression coverage proving that two tenants can use the same business identities independently while reading only their own state. Coverage includes:

- Ozon credentials;
- core product storage;
- product costs;
- Return inventory recovery;
- accounting attribution;
- accounting recognition;
- application authorization;
- exact-once Return COGS commit ledger;
- expenses;
- default tax configuration;
- request-context set/reset behavior;
- legacy no-tenant storage compatibility.

## SHA-bound verification chain

Verified production path at the time of this document:

- feature head `df1e7cf7c91cdcd69a4f648577841f84a4fd2f8f` — Verify #1783 passed;
- PR #495 synthetic merge `49cc5f0804c2e1e9c71604b7c79b06c498e3a614` — Verify #1784 passed;
- production code `1f017a3a506abb457615706cef75e56238c44303` — Verify #1785 passed.

SHA-bound production artifact for the code merge:

- `verification-1f017a3a506abb457615706cef75e56238c44303`
- `sha256:cf1334f6fa908a8443f5f48a8a455a3b0c9ce7b7ba4ff8984b521d7b251e4731`

The final documentation reconciliation SHA and its final `main` verification are recorded by the repository workflow after the docs PR is merged.
