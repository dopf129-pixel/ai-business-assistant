# Development Verification Gate v240-v247

## Goal

Connect SHA-bound pytest verification to the existing AI Development Agent workflow without changing product runtime behavior.

A historical green test run is useful evidence, but it must not make a newer revision checkpoint-ready.

## v240 — Workflow verification metadata

`AssistantDevelopmentWorkflowService` accepts an optional verification service.

When `current_sha` is supplied, `start_workflow` attaches the canonical verification result and exposes one of:

- `verified`;
- `failed`;
- `unverified`.

Legacy calls without verification context keep the previous workflow contract.

## v241 — Test-validation gate

`complete_step("test_validation", ...)` fails closed when SHA-aware verification is requested:

- stale or missing exact-SHA evidence → `current_suite_not_verified`;
- exact-SHA failing suite → `current_suite_failed`;
- exact-SHA green suite → completed.

No tests are executed by this service. It evaluates supplied evidence only.

## v242 — Verified checkpoint preparation

`AssistantGitCheckpointService.prepare_verified_checkpoint` requires:

1. a connected `AssistantProjectVerificationService`;
2. an exact current SHA;
3. a SHA-bound report for that same revision;
4. a passing verified suite.

Otherwise checkpoint preparation is `blocked`.

The existing `prepare_checkpoint` method is unchanged for backward compatibility and remains metadata-only.

## v243 — Development decision gate

If a development report explicitly carries verification metadata, `AssistantDevelopmentDecisionService` does not return `complete` unless the current suite is both verified and passed.

Reports without verification metadata retain legacy behavior.

## v244 — Agent propagation

`AssistantDevelopmentAgent.run_development_cycle` accepts optional:

- `current_sha`;
- `test_report`.

When provided, they are propagated to verification-aware workflow/checkpoint services.

## v245 — Agent-level fail-closed report

When a SHA-aware cycle is requested, the final development report is blocked unless:

- workflow verification proves the exact current SHA passed;
- checkpoint service returns a verified checkpoint with `checkpoint_ready=True`.

Partial verification wiring does not silently downgrade to the legacy path.

## v246 — Backward compatibility

Calls without `current_sha` preserve existing behavior:

- workflow starts as before;
- test-validation step can complete as before;
- plain checkpoint preparation remains available.

This avoids turning a development metadata hardening change into an unrelated migration.

## v247 — Capability and partial-wiring guards

If a SHA-aware agent cycle is requested but its checkpoint service lacks `prepare_verified_checkpoint`, the cycle returns:

`VERIFIED_CHECKPOINT_CAPABILITY_MISSING`

and remains blocked.

A verification-aware workflow without a verified checkpoint path also remains blocked.

## Security / trust model

The gate consumes `AssistantProjectVerificationService` output.

It does not independently claim that tests were genuinely executed by a trusted external CI system. Its guarantees are narrower:

- test evidence is bound to an exact canonical commit SHA;
- stale baseline evidence cannot verify current SHA;
- report counts/status/identity contradictions fail closed;
- development checkpoint readiness cannot silently reuse an old green baseline.

## Product safety

This is development tooling only.

It does not:

- change Product Decision rules;
- change freshness business semantics;
- modify task drafts;
- enable product execution;
- connect Action Executor;
- call Ozon;
- modify financial calculations;
- modify `data/users.json`.

## Validation

Focused regression coverage:

`tests/test_development_verification_gate_v240_v247.py`

The full repository pytest suite is not claimed as executed for this branch in the connector-only environment.
