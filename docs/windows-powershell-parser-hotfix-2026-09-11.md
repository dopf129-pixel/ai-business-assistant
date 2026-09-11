# Windows PowerShell launcher parser hotfix — 2026-09-11

## Problem

`start_bot.ps1` failed to parse on Windows PowerShell because the interpolated error message contained `$LASTEXITCODE:`. PowerShell treats the colon immediately after a variable name as part of variable-reference syntax, so the launcher stopped before any Python or Telegram code ran.

## Fix

The launcher now uses `${LASTEXITCODE}:` to delimit the variable name explicitly before the literal colon.

A regression test verifies that `start_bot.ps1` contains `${LASTEXITCODE}:` and does not contain the invalid `$LASTEXITCODE:` form.

## Runtime impact

This is a bootstrap parsing fix only. It does not change Telegram behavior, Ozon access, storage semantics, or accounting logic. Ozon access remains read-only.

## Verification

The feature revision and pull-request synthetic merge passed the repository Verify workflow. The squash-merged `main` revision `b2b571237fc6c65b46ec0f7409c98c273e70fdec` also passed Verify and produced a SHA-bound verification artifact.
