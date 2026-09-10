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

## Build-context safety

`.dockerignore` excludes repository metadata, virtual environments, `.env` files, local seller data, SQLite databases, local assistant state, tests, and development/reconciliation material from the container build context.

This prevents local credentials and tenant/seller state from being unintentionally copied into a production image.

## Verification coverage

`tests/test_telegram_container_runtime_contract.py` locks the following properties:

- the Dockerfile starts the canonical `telegram_api_bot` module;
- application imports resolve through `/app/app`;
- only production requirements are installed;
- `.env` and seller-state/database paths are excluded from the build context;
- no `TELEGRAM_BOT_TOKEN` value is defined in the Dockerfile.

## Safety invariants

This package changes deployment packaging only. It does not introduce Ozon write calls or accounting execution.

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

The container runtime intentionally delegates to the canonical Telegram startup package introduced by PR #507. It does not create a second runtime implementation. Provider-specific deployment manifests can be added later if a concrete hosting platform is selected.
