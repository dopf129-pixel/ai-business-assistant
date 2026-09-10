# Telegram runtime dependency readiness — 2026-09-10

## Status

The Telegram polling runtime now has an explicit production dependency contract and CI coverage that imports the actual Telegram runtime package.

Production code/config commit: `79b170e10feb1ee2d076434ebef80427db421d72`.

## Problem fixed

`app/telegram_app_layer/telegram_api_bot.py` is an executable polling entrypoint. It imports `telegram` / `telegram.ext`, builds a `python-telegram-bot` `Application`, registers handlers, and calls `run_polling()`.

Before this package, the repository had no root production `requirements.txt`, while `requirements-dev.txt` did not include `python-telegram-bot`. That meant a production dependency install from the repository could not install the Telegram runtime package, and normal verification did not prove that the executable entrypoint's third-party Telegram imports were available.

## Implemented

- Added `requirements.txt` with bounded production dependencies:
  - `requests>=2.31,<3`
  - `python-dotenv>=1,<2`
  - `cryptography>=43,<46`
  - `python-telegram-bot>=20.7,<22`
- `requirements-dev.txt` now includes `-r requirements.txt` while retaining the explicit bounded dependency lines required by the existing verification contract.
- Verify pip caching now tracks both `requirements.txt` and `requirements-dev.txt`.
- Added a smoke test that imports the Telegram runtime symbols used by the production polling entrypoint.
- Full verification passes with the Telegram runtime dependency installed from the repository's requirements contract.

## Verification

Feature SHA: `a1527890713ec5a475bb2ad3d77a2b90092eea27`.

Feature Verify #1837 / run `34470473754`: success. Artifact: `verification-a1527890713ec5a475bb2ad3d77a2b90092eea27`. Digest: `sha256:888ab9ddb442333eb73e2c1fb3c82d12468e6dfea54a125dbd825dee00dc93dc`.

PR #505 synthetic merge SHA: `396006e40ba5fd558331523e4317f545c416bb92`.

PR Verify #1838 / run `34470565357`: success. Artifact: `verification-396006e40ba5fd558331523e4317f545c416bb92`. Digest: `sha256:b1bc1a054e83da5e99c9457e4ecd413361e5d67ae4c194fbbc28939d66440260`.

Production main SHA after squash merge: `79b170e10feb1ee2d076434ebef80427db421d72`.

Production Verify #1839 / run `34470634392`: success. Artifact: `verification-79b170e10feb1ee2d076434ebef80427db421d72`. Digest: `sha256:90a3859e8f1fb1887e13c0d0b3e49e74309bc5c9b8a58c4b1aa1f7b918a7c576`.

## Safety invariants retained

- Ozon integration remains READ-ONLY.
- `ReturnedToOzon` remains candidate evidence only and is not proof of `SALEABLE_RESTORED`.
- Unknown values are not treated as zero.
- Return COGS is not guessed from quantity × cost when exact evidence is unavailable.
- Accounting facts are not auto-created.
- Seller-facing Period Profit remains read-only/non-executing.
- Commit readiness remains distinct from commit execution.
- Final application observability does not permit repeated commit.
- Downstream readiness requires the canonical status and corresponding boolean jointly.
- Inventory recovery is presentation-authoritative only when `inventory_recovery_evidence_status == "RETURN_INVENTORY_RECOVERY_READY"` and recovery state is `SALEABLE_RESTORED` or `NON_SALEABLE`.
- Historical warning `8 unresolved` is not conflated with `785 exact raw Returns API records`; identities are not invented.
