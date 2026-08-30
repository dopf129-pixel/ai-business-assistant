# Current Checkpoint v514-v520

Date: 2026-08-30  
Package: Unknown Advertising Financial Evidence V1  
Architecture Review Required: Yes

## Baseline entering package

Exact verified `main` before implementation:

`1d67e822848b07074b5c3cf76d34c74f14fdd7e4`

Push Verify #72 for that SHA completed successfully with 1328 passed.

## Completed package

PR #225 corrected production financial evidence semantics for advertising expense data.

Implemented:

- production advertising defaults to unknown instead of implicit zero;
- explicit numeric zero remains a known zero;
- empty/missing advertising input stays unknown;
- BusinessAnalyticsService blocks business-profit and margin calculation while advertising evidence is missing;
- revenue and gross profit remain available separately;
- tax missing/error semantics remain distinct;
- AdvertisingService exposes configured state for missing vs known values;
- dashboards render unknown/malformed finance values as «—»;
- sales-analysis output does not render unknown profit/margin as 0 or Python None.

## Architecture review

Required because the package changes production composition and an existing financial evidence contract and exceeds the approximate 300 changed-line threshold.

Review confirmed:

- no new service/layer;
- optional DI remains backward compatible;
- explicit zero is not conflated with missing evidence;
- no hidden advertising API fetch;
- no fuzzy advertising classification;
- no financial double counting;
- no RETURN/ADVERTISING/STORAGE remapping;
- no Product Decision or Product Task Draft execution;
- no Ozon mutation;
- no `data/users.json` change.

## PR verification

Initial PR head:

`866f28102cd6f8f1ea80987e4fa5adf5bb572f61`

Verify #73 failed because one newly added regression test connected SalesIntelligenceService directly to BusinessAnalyticsService instead of the actual StoreAnalyticsService contract.

The test was corrected in the same branch.

Final PR head:

`fbcc64ffa58611dde0a7b2364b0e17a7cdfb5e4a`

GitHub Actions:

- workflow: `Verify`;
- run number: **74**;
- run id: **33315001914**;
- event: pull request;
- status: completed;
- conclusion: success;
- tests: **1342 passed**;
- failed: **0**.

The failed earlier SHA is not treated as verified evidence.

## Squash merge

Exact resulting `main` SHA:

`f10679a2d3eb8890480a9cdf59f15c1db5541823`

## Post-merge push verification

GitHub Actions:

- workflow: `Verify`;
- event: **push**;
- run number: **75**;
- run id: **33315031971**;
- status: completed;
- conclusion: success;
- exact SHA: `f10679a2d3eb8890480a9cdf59f15c1db5541823`;
- tests: **1342 passed**;
- failed: **0**;
- canonical SHA-bound test-report artifact: generated.

Artifact:

`verification-f10679a2d3eb8890480a9cdf59f15c1db5541823`

This completed run verifies the exact squash-merge SHA and is not described as independent external verification.

## Current interpretation

Unknown advertising evidence is now fail-closed.

The package does not make advertising data complete and does not claim complete accounting profit.

The next package should be selected from a concrete current repository/product/operational gap.
