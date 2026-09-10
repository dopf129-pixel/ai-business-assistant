# Production Docker verification contract

Date: 2026-09-10

The canonical GitHub Actions `Verify` workflow now verifies the production container artifact in addition to the Python test suite.

## Required verification behavior

For every verified revision, CI must:

1. Build the repository root `Dockerfile` into a SHA-tagged local image.
2. Record the image tag and Docker image ID in `verification-artifacts/revision.txt`.
3. Run `runtime_healthcheck` inside the built image with:
   - a non-secret verification Telegram token,
   - an ephemeral Fernet master key generated inside the image,
   - a writable temporary storage root.
4. Import the canonical `telegram_api_bot` and `runtime_healthcheck` modules inside the built image.
5. Fail the canonical `Verify` job if the Docker build or either container smoke check fails.

The workflow does not require repository or GitHub secrets for this smoke test. The Fernet key is generated ephemerally for the verification run and is not a production credential.

## Scope and invariants

This change validates packaging/runtime readiness only. It does not introduce deployment to any provider and does not select a hosting platform.

Ozon remains strictly read-only. No seller-side write or mutation capability is introduced.

Accounting facts are not auto-created. Seller-facing Period Profit remains read-only/non-executing. Return COGS rules remain unchanged: candidate return evidence is not proof of saleable inventory restoration, unknown is not zero, and quantity × cost must never be guessed when the required evidence is absent.

The canonical status plus its boolean readiness flag remain jointly required downstream. Inventory presentation is authoritative only when `inventory_recovery_evidence_status == "RETURN_INVENTORY_RECOVERY_READY"` and the recovery state is `SALEABLE_RESTORED` or `NON_SALEABLE`.

The historical warning `8 unresolved` must not be conflated with `785 exact raw Returns API records`; this verification change does not alter either fact set.
