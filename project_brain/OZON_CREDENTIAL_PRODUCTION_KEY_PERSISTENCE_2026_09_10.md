# Ozon credential production key and persistence contract — 2026-09-10

## Scope

This reconciliation documents the production-readiness contract introduced by implementation PR #517 for encrypted seller Ozon credentials. Ozon access remains strictly read-only. No accounting execution, Return COGS commit behavior, or seller-facing Period Profit execution semantics were changed.

## Production gap closed

Before this package, `OzonAccountRepository` encrypted API keys with `OZON_CREDENTIAL_MASTER_KEY`, but its default SQLite database path was the relative file `ozon_assistant.db`. In the production container that path resolved under the application working directory rather than the mounted persistent runtime volume. A container replacement could therefore discard the encrypted credential database even though other runtime storage used `AI_ASSISTANT_STORAGE_ROOT`.

The production Compose contract also did not require or inject `OZON_CREDENTIAL_MASTER_KEY`, and the local runtime healthcheck did not validate that a stable Fernet-compatible key was configured. A deployment could therefore start with persistent application storage while encrypted Ozon credentials were not operationally recoverable across redeploys.

## Persistence contract

For the repository default `ozon_assistant.db` path, `OzonAccountRepository` now resolves the database beneath `AI_ASSISTANT_STORAGE_ROOT` when that environment variable is configured. With the repository-owned production container/Compose contract, the encrypted credential database therefore lives under `/var/lib/ai-business-assistant`, which is backed by the persistent named volume.

Compatibility boundaries are deliberate:

- An explicit absolute database path is not rebased.
- An explicitly supplied custom database path/name is not rebased.
- When `AI_ASSISTANT_STORAGE_ROOT` is absent, the legacy relative `ozon_assistant.db` behavior is preserved for development/tests and existing callers.
- Parent directories are created only on actual database access; path resolution itself does not require a network call.

## Master-key contract

`OZON_CREDENTIAL_MASTER_KEY` is a deployment secret and must be stable across restarts and redeploys for previously encrypted credentials to remain decryptable. It must be a valid Fernet key. The key itself is not committed to the repository.

`docker-compose.production.yml` now requires both runtime secrets through deployment-time interpolation:

- `TELEGRAM_BOT_TOKEN`
- `OZON_CREDENTIAL_MASTER_KEY`

If the Ozon master key is missing, the production Compose configuration fails before a valid deployment can be formed. Operators must preserve the same master key for the lifetime of credentials encrypted with it. Replacing the key without an explicit migration/reconnection process makes existing ciphertext unreadable; the application does not guess, regenerate, or silently overwrite a replacement key.

## Health contract

When `AI_ASSISTANT_STORAGE_ROOT` is configured, `runtime_healthcheck` now fails closed if `OZON_CREDENTIAL_MASTER_KEY` is missing or not syntactically valid for Fernet. Health messages are generic and never echo the key value.

The check remains local and side-effect constrained:

- no Telegram network request;
- no Ozon network request;
- no seller assistant initialization;
- no credential decryption probe against Ozon;
- no missing storage-root creation by the healthcheck.

The no-storage-root legacy/development health path remains compatible and does not impose the production master-key requirement by itself.

## Credential safety and restart behavior

Regression coverage confirms that:

- the default credential DB resolves under the configured persistent runtime root;
- the API key is stored as Fernet ciphertext rather than plaintext;
- reconstruction of `OzonAccountRepository` with the same master key decrypts the saved credential after restart;
- a wrong master key fails to decrypt and does not mutate the stored ciphertext on the read path;
- restoring the correct key still decrypts the original credential;
- explicit custom database paths remain independent of the runtime root;
- absence of `AI_ASSISTANT_STORAGE_ROOT` preserves the legacy default path;
- production Compose requires the master key without embedding a secret value;
- healthcheck errors do not disclose the secret.

The existing seller connection flow still validates Ozon credentials with a read-only `get_products(limit=1)` probe before encrypted local persistence. The API key is never returned to the seller after storage.

## Safety invariants preserved

- Ozon remains READ-ONLY; this package adds no Seller API write call.
- `ReturnedToOzon` remains candidate evidence only and is not proof of `SALEABLE_RESTORED`.
- Unknown values remain unknown, not zero.
- No guessed quantity × cost Return COGS is introduced.
- No accounting facts are created automatically.
- Seller-facing Period Profit remains read-only/non-executing.
- Commit readiness remains distinct from commit execution.
- Final application observability does not authorize repeat commit.
- Downstream Return COGS logic still requires canonical status and boolean readiness jointly.
- Inventory presentation is authoritative only for `RETURN_INVENTORY_RECOVERY_READY` with `SALEABLE_RESTORED` or `NON_SALEABLE`.
- Historical `8 unresolved` is not conflated with `785 exact raw Returns API records`; no return identities are invented.

## Verification lineage

Canonical implementation feature head: `49d087026bf1cd0ec731e746186da0153b17dcb5`.

Implementation PR #517 synthetic merge revision: `b3806dc91fd5113ff06dd06f1d6435d44394b1bf`.

Production main after implementation squash merge: `4f7b789798054a5f17be2289c4c04d44a13b0f05`.

All three canonical revisions completed the repository Verify workflow successfully with SHA-bound verification artifacts before this documentation reconciliation was created.
