# Verification Status

Date: 2026-09-04

## Latest verified product baseline

`08d407f045e588b83b1c2096c5f652e663781b2d`

Latest merged production batch:

`v1351-v1360: Return COGS Accounting Recognition`

### Entering exact docs-reconciled main

- exact main: `ba6346473a8e7dd9d1d3124408f901efc5a860d4`;
- no verification evidence is transferred from this predecessor to later revisions.

### Failed intermediate evidence

- SHA `5ec279e5da0581af8fb79b726476324ac3309cb8` — Verify #1192 — 2267 passed / 1 failed;
- failure was a package-test assertion using a one-cent difference where the service contract intentionally accepts differences up to and including one cent;
- this SHA remains failed evidence permanently and no success evidence is transferred from it.

### Exact feature-head verification

- SHA `e311c2faec20d4236cb5ee5bf6e1799cbdbad7e3`;
- Verify #1193;
- 2268 passed / 0 failed;
- artifact 9936817042;
- digest `sha256:fdedfbf5bcaf5aca554bd052fc99d6b2377325fab31558c841eebc2a663d3e56`.

### PR merge-ref integration verification

- PR #407;
- synthetic SHA `555c977d64d0a3613a820e7efe8b2eaabb8114d8`;
- Verify #1194;
- 2268 passed / 0 failed;
- artifact 9936855181;
- digest `sha256:5fa6954544b93fa3ca8da3814df524a93cc80eb7a04881a16470bbaef64613e0`;
- CI checkout explicitly used `refs/pull/407/merge` at the synthetic SHA.

### Post-merge exact-main verification

- exact main `08d407f045e588b83b1c2096c5f652e663781b2d`;
- Verify #1195;
- 2268 passed / 0 failed;
- artifact 9936912356;
- digest `sha256:bbe069338654fcfac72ad782de2e14d07e8e9d370835d738f5f332d0adf1aa90`;
- CI checkout explicitly used `refs/heads/main` at the exact SHA.

## Current Return COGS recognition boundary

Accounting recognition is now a separate explicit evidence layer after recognition eligibility.

Recognition requires exact identity coverage and exact reconciliation with the eligible candidate set for:

- `return_id + posting_number + SKU`;
- accounting recognition date;
- recognized amount;
- RUB currency;
- explicit recognition state;
- append-only versioned confirmation evidence.

A later revocation supersedes an earlier recognition. Missing, malformed, conflicting, mismatched, or revoked evidence fails closed.

When exact recognition is confirmed, `period_cogs_recovery_confirmed`, `accounting_cogs_recovery_confirmed`, and `confirmed_cogs_recovery_amount` may be promoted. Period Profit application remains closed: `profit_adjustment_allowed=False`, `automatic_recovery_allowed=False`, and the canonical Period Profit formula is unchanged.

## Verification policy

Exact branch push verification proves only that exact branch head. Pull-request verification proves only the synthetic merge ref. Every squash-main SHA requires its own exact push verification. Failed SHAs remain failed evidence permanently. Cancelled/pending SHAs carry no transferable success claim. Missing evidence remains unknown and is never interpreted as zero or clean. Workflow evidence is project CI evidence only; `externally_verified=False`.
