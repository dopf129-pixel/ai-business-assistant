# Seller E2E production readiness — 2026-09-10

## Status

Production hardening is complete for the Ozon credential-bearing Telegram connection boundary audited in this package.

Production code commit: `0c3da150dd42a6841b0890b0576a83652fa037b5`.

## Implemented

- `TelegramRunner.receive_message()` no longer persists the raw payload of a leading `/ozon_connect` command into assistant history or context.
- The persisted representation is `/ozon_connect [REDACTED]`; Client ID and API Key are omitted from assistant-local history, `last_message`, and `current_task`.
- The original command text is still dispatched to `TelegramBotService` / `TelegramCommandService`, so the connection flow receives the actual credentials it needs.
- Redaction is case-insensitive and tolerant of surrounding whitespace, but applies only when `/ozon_connect` is the leading command token. Ordinary seller messages remain unchanged.
- The Telegram tenant ContextVar boundary remains active and is reset after dispatch.

## E2E acceptance coverage

`tests/test_seller_e2e_production_readiness.py` covers:

- Telegram command -> account service -> read-only Ozon `get_products(limit=1)` probe -> encrypted local credential persistence.
- No plaintext API key in the credential SQLite file.
- No Client ID or API Key in assistant history/context records.
- Restart/status behavior using a reconstructed repository/service with the same encrypted credential store.
- Normal seller messages still persist and dispatch unchanged.
- Mixed-case/whitespace command redaction and command-token-only matching.

## Safety invariants retained

- Ozon integration remains READ-ONLY; this package introduces no Ozon mutation calls.
- The only external Ozon operation exercised by the onboarding acceptance path is the existing read-only product probe.
- No accounting facts are auto-created and no accounting execution path is added.
- Unknown values are not converted to zero.
- Return COGS evidence/readiness/application invariants remain unchanged.
- `ReturnedToOzon` remains candidate evidence only and is not proof of `SALEABLE_RESTORED`.
- Commit readiness remains distinct from commit execution; final application observability does not permit repeat commit.

## Verification evidence

Feature head: `b029128704170e4a2e8c3ba0766a4632dc140658`.
Feature Verify #1825 / run `34469061973`: success. Artifact `verification-b029128704170e4a2e8c3ba0766a4632dc140658`; digest `sha256:071873d89fb4fdc48576a4f45b228c4450519be6972944e93f4a2938896e2ede`.

PR #503 synthetic merge: `be66cc73e5acb988e43a4bb4ad27d1ba385ef884`.
Synthetic Verify #1826 / run `34469180063`: success. Artifact `verification-be66cc73e5acb988e43a4bb4ad27d1ba385ef884`; digest `sha256:aeca19f8189632874eb6a1da5b53a1cbe84eb2997757e9f6976aa90c4c967901`.

Production main: `0c3da150dd42a6841b0890b0576a83652fa037b5`.
Production Verify #1827 / run `34469256383`: success. Artifact `verification-0c3da150dd42a6841b0890b0576a83652fa037b5`; digest `sha256:0e020f82d420a1a1c7128691bdea32b7282ac791485123d8c7b7b370c839b80a`.
