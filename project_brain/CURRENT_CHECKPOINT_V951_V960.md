# CURRENT_CHECKPOINT_V951_V960

Date: 2026-09-01

## Product Decision Action Proposal Result Integrity

Production package:

`v951-v960: Product Decision Action Proposal Result Integrity`

Goal:

Fail closed when the seller-facing Product Decision action-proposal dependency returns malformed, contradictory, unsafe, or exceptional results before those results reach cache, task-draft lifecycle, assortment counts, or Telegram controls.

## Verified behavior

- action proposal result must be a mapping;
- proposal availability/action/confirmation markers are exact booleans;
- `execution_allowed=False` and `automation_status=PROHIBITED` are mandatory;
- proposal SKU, priority, decision type, and reasons remain exactly bound to the Product Decision;
- proposal type and confirmation requirements must match Product Decision semantics;
- proposal-service exceptions become deterministic non-secret failure;
- malformed proposal results are not cached;
- task-draft lifecycle is not entered from malformed proposal state;
- assortment query fails closed rather than counting malformed proposals;
- Telegram renders a neutral failure message and exposes no proposal controls for invalid proposal state.

## Telegram verified-guidance integration finding

The current production Product Decision history snapshot does not persist the exact persistence-application lineage required by `ProductDecisionPersistenceVerificationService`.

Specifically, the durable history snapshot contains decision facts, recorded_at, feedback, proposal and outcome state, but not:

- `decision_persistence_application_id`;
- readiness / authorization / eligibility IDs;
- preview review / delta / recompute IDs;
- the complete persistence application receipt.

There is no separate durable persistence-application receipt storage service in the current repository.

Therefore the verified Product Decision → user-action guidance/checklist chain remains intentionally **not wired into Telegram**. Safe wiring must not:

- synthesize application IDs;
- infer lineage from decision-shaped history snapshots;
- call persistence application as a side effect of a read-only Telegram view.

This is an identified integration blocker, not a clean/complete integration claim.

## SHA-bound verification evidence

### Entering exact main

- SHA: `2c0e9fcce68a25c3518ff8cdb134470bed73e25d`
- push Verify #664
- 1851 passed / 0 failed
- artifact id: 9813494352
- digest: `sha256:b179cdf1117a663888430b4a7de3f9aa3549e0f807cdfe30812c710ccd7c3531`

### Exact final feature head

- branch: `fix/product-decision-action-proposal-result-integrity-v951-v960`
- SHA: `70cbcc825fc49ab868ae1ac3c58ff80ea115482a`
- push Verify #666
- 1861 passed / 0 failed
- artifact id: 9813694083
- digest: `sha256:f589a96e408596b8e64294a9608185dd366fb503c0b42050bf22fbcf208fe4d1`

### PR synthetic merge-ref

- PR #326
- synthetic SHA: `4b8792f73e6f54836d358b4c0215d885d40c2a93`
- pull_request Verify #667
- 1861 passed / 0 failed
- artifact id: 9813722308
- digest: `sha256:c3283632626262262c73c92e37b3dc5fe6dcad802536169c3a903d2060756602`

This is synthetic integration evidence only.

### Squash-main verification

- exact main SHA: `7637177202c21d3f2894105e39137efd86855b8c`
- push Verify #668
- 1861 passed / 0 failed
- artifact id: 9813762224
- digest: `sha256:34ccac02b0cbf26e1a8aa67b90d08b572d7076583a4929c796f9a4c49aa95c63`

No failed intermediate production SHA occurred in v951-v960.

## Review classification

Architecture Review Required: Yes

Critical Review Required: No

Reason: an existing seller-facing service contract was materially hardened and the production/test diff exceeds the architecture-review size threshold. No new persistence owner, runtime route, execution layer, or business mutation path was introduced.

GitHub Actions evidence is project CI evidence only.
`externally_verified=False`.
`data/users.json` unchanged.
