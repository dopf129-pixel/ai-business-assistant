# Verification Status

Date: 2026-08-30

## Latest verified product baseline

Latest exact verified `main` product baseline:

`15d2051487dccd1c630394424f0675ac50aecdae`

Latest merged production-correctness batch:

`v548-v553: Marketing Evidence Integrity`

GitHub evidence remains SHA-bound and separated by execution layer.

### Exact feature-head verification

- feature branch: `fix/marketing-evidence-integrity-v548-v553`
- exact head SHA: `ec4bfdb0acbcdcf24c82c5ea0990b88b34e384af`
- workflow: `Verify`
- event: **push**
- run number: **134**
- run id: **33326826494**
- conclusion: **success**
- full test suite: **1399 passed**
- failed: **0**
- artifact: `verification-ec4bfdb0acbcdcf24c82c5ea0990b88b34e384af`
- artifact id: **9736469026**

This branch-push run is the exact feature-head evidence.

### PR merge-ref integration verification

- PR: **#235**
- branch head: `ec4bfdb0acbcdcf24c82c5ea0990b88b34e384af`
- workflow: `Verify`
- event: **pull_request**
- run number: **135**
- run id: **33326865201**
- conclusion: **success**
- full test suite: **1399 passed**
- failed: **0**

This is synthetic PR merge-ref integration evidence and is not promoted as
exact branch-head verification.

### Post-merge exact main verification

- exact main SHA: `15d2051487dccd1c630394424f0675ac50aecdae`
- workflow: `Verify`
- event: **push**
- run number: **136**
- run id: **33326897395**
- conclusion: **success**
- full test suite: **1399 passed**
- failed: **0**
- artifact: `verification-15d2051487dccd1c630394424f0675ac50aecdae`
- artifact id: **9736487921**

This completed run verifies the exact squash-merge SHA. It is not independent
external verification.

## Marketing Evidence Integrity

The existing marketing path no longer invents execution-looking analysis.

Contract:

- `marketing_problem=True` alone is not actionable;
- marketing recommendation requires `marketing_evidence_available=True`;
- recommendation also requires a non-empty `marketing_context`;
- executor requires explicit non-empty string `evidence`;
- executor formats supplied evidence only;
- missing or malformed evidence returns an error;
- persisted router execution therefore enters the existing FAILED lifecycle;
- generic fallback reports insufficient data when marketing evidence is unavailable.

The repository still has no production marketing data service/API connected to
this path. No hidden fetch is performed.

## Execution safety

This package does not:

- add a marketing API;
- mutate advertising campaigns;
- mutate Ozon;
- alter Product Decision rules;
- execute Product Task Drafts;
- change persistence format;
- modify `data/users.json`.

Marketing evidence availability is not execution authorization.

## Verification policy

Exact branch push verification is required for feature/docs heads.

PR `pull_request` runs are merge-ref integration evidence and remain separate.

Every resulting `main` SHA must receive its own successful push verification
before becoming the verified baseline.

## Related implementation

- `app/services/assistant_marketing_executor_service.py`
- `app/services/assistant_recommendation_service.py`
- `tests/test_marketing_executor.py`
- `tests/test_marketing_recommendation.py`
- `tests/test_marketing_evidence_integrity_v548_v553.py`
- `project_brain/MARKETING_EVIDENCE_INTEGRITY_V1.md`
- `project_brain/CURRENT_CHECKPOINT_V548_V553.md`
