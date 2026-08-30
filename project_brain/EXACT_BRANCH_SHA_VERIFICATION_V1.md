# Exact Branch SHA Verification V1

Date: 2026-08-30  
Stage: v547  
Architecture Review Required: No for CI trigger itself

## Discovered verification gap

The existing `Verify` workflow ran for pull requests, but GitHub's default
`pull_request` checkout used the synthetic PR merge ref.

The workflow API could report the branch head SHA while the actual checkout,
`GITHUB_SHA`, revision artifact and canonical test report were bound to the
synthetic merge commit.

Therefore a green pull-request run must not be described as exact PR-head
verification unless the executed revision actually matches that head.

## Contract

`Verify` now also runs on branch pushes while preserving the explicit `main`
push trigger.

This produces two complementary checks for an open PR:

1. branch push run — exact feature/docs branch SHA;
2. pull-request run — synthetic merge ref against the current PR base.

Before merge, the branch push run is the SHA-bound exact-head evidence.
The PR run remains useful integration evidence against the current base.

After squash merge, a separate `main` push run is still mandatory for the exact
merged SHA.

## Evidence separation

Do not transfer evidence across these revisions:

- feature branch head SHA;
- synthetic PR merge SHA;
- squash-merge `main` SHA.

Each run's `revision.txt`, test report and artifact remain bound to its actual
`GITHUB_SHA`.

A failed exact-head run remains failed evidence even if a synthetic PR merge run
is green.

## Safety

This is development CI behavior only.

It does not:

- add production runtime GitHub access;
- change product/business execution;
- change Product Decisions;
- change persistence data;
- mutate Ozon;
- modify `data/users.json`.

## Regression coverage

`tests/test_exact_branch_verification_v547.py` verifies that:

- the explicit `main` push contract remains present;
- branch pushes are enabled for exact-SHA verification;
- exact revision checkout and SHA-bound manifest inputs remain present.
