# CI Verification Foundation v1

Date: 2026-08-30

Stages: v269-v278

## Goal

Provide repository-native, SHA-bound verification for the full Python test suite so later hardening work can be evaluated against the exact commit under review instead of carrying forward a historical local test count.

## Contract

The workflow `.github/workflows/verify.yml` runs on:

- every pull request;
- pushes to `main`;
- explicit workflow dispatch.

It uses Python 3.11 and installs only the explicit verification dependencies from `requirements-dev.txt`.

## Verification sequence

1. Check out the exact GitHub revision.
2. Install bounded development dependencies.
3. Compile `app/` with `python -m compileall -q app`.
4. Record `GITHUB_SHA`, ref, run ID and Python version.
5. Run the complete repository test suite with `python -m pytest -q`.
6. Emit JUnit XML.
7. Upload revision metadata and JUnit output even when tests fail.

## Security and side-effect boundary

The workflow has only `contents: read` permission.

`OZON_CLIENT_ID` and `OZON_API_KEY` are explicitly empty. The workflow does not receive Ozon secrets and is not an execution or production-mutation path.

No Product Decision, Product Task Draft, mapping authorization or business execution permission is changed by CI.

## SHA semantics

A green workflow run verifies only the exact `GITHUB_SHA` recorded by that run. It does not automatically verify later commits.

The historical user-confirmed `982 passed` result remains valid evidence only for SHA `11883f901d3bb344816735b834392a59185c0c81` until a new exact-SHA run succeeds.

## Failure handling

A failing run is useful evidence. Its JUnit artifact and revision metadata remain available for diagnosis. Do not hide or reinterpret a failing run as a stale-success baseline.

## Concurrency

Superseded runs for the same workflow/ref are cancelled to avoid wasting CI resources and to reduce confusion over which revision is current.

## Architecture review

Architecture Review Required: Yes.

Reason: this introduces repository-level verification infrastructure that becomes a gate/evidence source for future production hardening, although it does not change business runtime behavior.
