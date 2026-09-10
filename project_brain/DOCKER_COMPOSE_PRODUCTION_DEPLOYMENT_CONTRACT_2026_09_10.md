# Docker Compose Production Deployment Contract — 2026-09-10

## Purpose

This package adds a provider-neutral deployment manifest for running the production Telegram polling assistant with Docker Compose without introducing a cloud-vendor dependency.

## Canonical Compose contract

The repository root now contains `docker-compose.production.yml`.

The `telegram-assistant` service:

- builds the repository-owned `Dockerfile`;
- uses the existing canonical container command and inherited image healthcheck;
- requires `TELEGRAM_BOT_TOKEN` from the runtime environment using Compose required-variable expansion;
- sets `AI_ASSISTANT_STORAGE_ROOT=/var/lib/ai-business-assistant`;
- mounts the named volume `ai_business_assistant_data` at `/var/lib/ai-business-assistant`;
- uses `restart: unless-stopped`;
- gives graceful shutdown a `30s` stop grace period;
- does not publish network ports.

The manifest intentionally does not embed a Telegram token or other seller credentials.

## Runtime behavior

The deployment contract composes the repository-owned production packages already established earlier:

1. `Dockerfile` provides the production Python runtime and canonical `python -m telegram_api_bot` entrypoint.
2. The image healthcheck validates required Telegram configuration and persistent-storage availability without Telegram/Ozon network calls or seller-runtime initialization.
3. `STOPSIGNAL SIGTERM` and explicit SIGINT/SIGTERM polling handling provide graceful process termination.
4. `AI_ASSISTANT_STORAGE_ROOT` plus the named volume preserve mutable seller/tenant state across container recreation.
5. Compose restart policy restarts the process after ordinary runtime failure while `unless-stopped` still permits an operator to stop it intentionally.

## Secret boundary

`TELEGRAM_BOT_TOKEN` is required at Compose interpolation time:

```text
${TELEGRAM_BOT_TOKEN:?TELEGRAM_BOT_TOKEN is required}
```

The repository contains no production token value. Deployment operators must inject the token through the runtime environment or an external secret-management mechanism supported by their host.

## Persistence boundary

The named Compose volume is mounted at:

```text
/var/lib/ai-business-assistant
```

Tenant-local state continues to use the existing SHA-256-derived partitioning under the storage root. The Compose manifest does not flatten or merge tenant state.

## Verification coverage

`tests/test_docker_compose_production_contract.py` locks the following properties:

- the repository Dockerfile remains the build source;
- the persistent runtime storage root and named volume are wired together;
- `TELEGRAM_BOT_TOKEN` is required but no value is committed;
- restart policy is `unless-stopped`;
- graceful stop window is `30s`;
- no host ports are published;
- Compose does not override the canonical image command or healthcheck.

## Safety invariants

This package changes deployment orchestration only. It does not add Ozon write calls, accounting execution, or seller-facing mutation flows.

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

## Provider relation

This manifest is intentionally provider-neutral. It is suitable as the deployment baseline for a single-host Docker/Compose environment and can be translated later into a provider-specific manifest once a hosting platform is chosen. Any provider-specific adaptation must preserve the same secret, persistence, healthcheck, restart, graceful-shutdown, tenant-isolation, Ozon READ-ONLY, and accounting fail-closed boundaries.
