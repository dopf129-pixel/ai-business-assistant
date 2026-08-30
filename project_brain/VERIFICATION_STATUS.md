# Verification Status

Date: 2026-08-30

## Latest verified product baseline

`5131832339239f87886f9172f71cc1c0ec3553b4`

Latest merged production-correctness batch:

`v597-v603: Entry/Core Result Integrity`

### Entering exact-main verification

- exact main: `de084ad62b251b1d308ece4fa36f7f70e585b4c9`
- push Verify #252
- conclusion: success
- tests: 1495 passed / 0 failed

### Failed intermediate feature evidence

- exact SHA: `3fd85c7eb6052ed4047e81b0a2571eca98702c02`
- push Verify #256
- conclusion: failure
- tests: 1499 passed / 4 failed

This SHA remains failed evidence. The failures were legacy direct-runtime fixtures
that omitted the explicit boolean `error` marker required by the hardened entry
boundary. Later green evidence is not transferred back to this SHA.

### Exact final feature-head verification

- branch: `fix/entry-core-result-integrity-v597-v603`
- exact SHA: `4808e27661f869aeef59baca4d07035132f012c7`
- push Verify #260
- conclusion: success
- tests: 1503 passed / 0 failed
- artifact: `verification-4808e27661f869aeef59baca4d07035132f012c7`
- artifact digest: `sha256:22836898eee87f26725f6fb8b4b2ed9cd5c3ca7920dc1a0c302d82bdc3fb08da`

### PR merge-ref integration verification

- PR #250
- branch head: `4808e27661f869aeef59baca4d07035132f012c7`
- synthetic merge SHA: `6ea107c8c27def9a7531c19d725ee7e8fea25330`
- pull_request Verify #261
- conclusion: success
- tests: 1503 passed / 0 failed
- artifact: `verification-6ea107c8c27def9a7531c19d725ee7e8fea25330`
- artifact digest: `sha256:d14789f4f3d04fbfe2c262e20698326ad9edba3dd733b1289c73042df06ee2e2`

This is synthetic merge-ref integration evidence only.

### Post-merge exact-main verification

- exact main: `5131832339239f87886f9172f71cc1c0ec3553b4`
- push Verify #262
- conclusion: success
- tests: 1503 passed / 0 failed
- artifact: `verification-5131832339239f87886f9172f71cc1c0ec3553b4`
- artifact digest: `sha256:bfe98cd795f9b22933c7cdf3a510787d135356e31533f3a47383dff511d7849d`

## Entry/Core Result Integrity

Application entry and core boundaries now reject malformed direct-runtime and
orchestrator results before they can be forwarded, mutated, or interpreted as
successful responses.

No new business execution capability, Product Decision execution, Ozon mutation,
or persistence owner was introduced.

## Verification policy

Exact branch push verification proves only that exact branch head.
Pull-request runs prove only their synthetic merge refs.
Every squash-main SHA requires its own exact push verification.
Workflow/test-manifest evidence is not independent external verification;
`externally_verified=False`.

## Related implementation

- `app/services/assistant_entry_service.py`
- `app/services/assistant_core_service.py`
- `tests/test_entry_core_result_integrity_v597_v603.py`
- `project_brain/CURRENT_CHECKPOINT_V597_V603.md`
