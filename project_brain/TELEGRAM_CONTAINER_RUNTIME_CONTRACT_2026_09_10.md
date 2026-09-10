# Telegram Container Runtime Contract — 2026-09-10

## Purpose

This package adds a repository-owned container runtime for the Telegram polling assistant so the production startup contract can be used directly by container platforms without provider-specific configuration.

## Canonical image contract

The repository root now contains `Dockerfile`.

The image:

- uses `python:3.12-slim`;
- sets `PYTHONDONTWRITEBYTECODE=1` and `PYTHONUNBUFFERED=1`;
- sets `PYTHONPATH=/app/app`;
- installs `requirements.txt` only;
- copies the application package into `/app/app`;
- starts the existing canonical Telegram entrypoint with `python -m telegram_api_bot`.

`TELEGRAM_BOT_TOKEN` is not baked into the image. The existing startup boundary continues to require it from the runtime environment and fails closed when it is absent.

## Persistent runtime storage contract

PR #511 adds a provider-neutral persistent storage root for seller and tenant state.

The production image sets:

```text
AI_ASSISTANT_STORAGE_ROOT=/var/lib/ai-business-assistant
```

and declares:

```text
VOLUME /var/lib/ai-business-assistant
```

Default relative storage paths are resolved beneath this root when the environment variable is configured. Tenant-local storage remains partitioned using the existing SHA-256-derived tenant directory under `data/tenants/<digest>/`.

The behavior is intentionally opt-in outside the production container: when `AI_ASSISTANT_STORAGE_ROOT` is unset, historical relative paths are preserved exactly. Explicit absolute storage paths are not rebased. Path resolution itself remains side-effect free; directories are created only when a storage write or database open actually requires them.

This means container recreation can preserve seller/tenant databases and JSON state as long as the runtime mounts durable storage at `/var/lib/ai-business-assistant`. The contract does not depend on a specific cloud or container provider.

## Build-context safety

`.dockerignore` excludes repository metadata, virtual environments, `.env` files, local seller data, SQLite databases, local assistant state, tests, and development/reconciliation material from the container build context.

This prevents local credentials and tenant/seller state from being unintentionally copied into a production image. Runtime persistence is therefore supplied by the mounted volume, not by baking mutable state into the image.

## Verification coverage

`tests/test_telegram_container_runtime_contract.py` locks the following properties:

- the Dockerfile starts the canonical `telegram_api_bot` module;
- application imports resolve through `/app/app`;
- only production requirements are installed;
- the persistent storage root and volume are declared;
- `.env` and seller-state/database paths are excluded from the build context;
- no `TELEGRAM_BOT_TOKEN` value is defined in the Dockerfile.

`tests/test_persistent_runtime_storage_contract.py` additionally verifies:

- historical paths remain unchanged when the storage root is unset;
- legacy default state is relocated beneath the configured persistent root;
- tenant A and tenant B remain physically isolated beneath the same persistent root;
- path resolution does not create directories;
- parent directories are created only through the explicit storage-write helper;
- absolute paths are not rebased by the persistent root.

## Safety invariants

This package changes deployment persistence only. It does not introduce Ozon write calls or accounting execution.

The existing invariants remain mandatory:

- Ozon is READ-ONLY;
- `ReturnedToOzon` is candidate evidence only;
- unknown is not zero;
- Return COGS is never guessed from quantity × cost;
- accounting facts are not auto-created;
- seller-facing Period Profit remains read-only/non-executing;
- readiness does not imply execution;
- final observability cannot authorize repeated commit;
- downstream gates require canonical status and boolean together;
- inventory presentation is authoritative only for `RETURN_INVENTORY_RECOVERY_READY` with `SALEABLE_RESTORED` or `NON_SALEABLE`.

## Production relation

The container runtime intentionally delegates to the canonical Telegram startup package introduced by PR #507. PR #511 extends that runtime with a durable storage contract rather than creating a second persistence implementation.

Provider-specific deployment manifests can be added later if a concrete hosting platform is selected. Any such provider configuration must mount durable storage at the declared runtime storage root and must continue to inject secrets only at runtime.
