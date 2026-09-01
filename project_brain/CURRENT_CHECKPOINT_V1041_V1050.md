# CURRENT_CHECKPOINT_V1041_V1050

Date: 2026-09-01

## Product Decision Durable Application Lineage

Production package:

`v1041-v1050: Product Decision Durable Application Lineage`

Goal:

Persist exact persistence-application lineage with the durable Product Decision snapshot so runtime verification can later be reconstructed read-only without persistence side effects.

## Verified behavior

- application lineage is constructed before durable history write;
- lineage contains exact application/readiness/authorization/eligibility/review/delta/preview IDs, draft_id and SKU;
- existing Product Decision History owner validates exact fields and all prefix-derived relationships;
- malformed and cross-SKU lineage is rejected before storage mutation;
- durable snapshot and COMMITTED receipt carry the same lineage;
- persistence application rejects forged receipt lineage;
- persistence verification rejects forged receipt or durable snapshot lineage;
- JSON storage restart preserves lineage;
- feedback mutation preserves lineage;
- restart readback verifies without execution;
- no persistence IDs are inferred or synthesized after write;
- Telegram remains read-only and does not invoke persistence application.

## SHA-bound verification evidence

### Entering exact main
- SHA: `835b710e2ad7ad37f8b27415064a6900bcb36ada`
- push Verify #749
- 1941 passed / 0 failed
- artifact id: 9820823725
- digest: `sha256:26594c818d43ced50ab12e62a1ff5862f87b9f40e0e0b4bbfdacd83a54d9f4c7`

### Failed intermediate
- SHA: `cfeb3528d5f902625819b6897db192bf794fddda`
- push Verify #751
- 1915 passed / 36 failed
- artifact id: 9821284999
- digest: `sha256:094c2a223c66afa81f078f606f72c6de0ab6ea594c3d9198ee33e8f9eaa94ca1`

This SHA remains failed evidence permanently.

### Exact final feature head
- SHA: `5e856591925d2288db871ac9632eab5ee7f7a649`
- push Verify #752
- 1951 passed / 0 failed
- artifact id: 9821304515
- digest: `sha256:98b8cba6e7a80c1063c53de00f9b60aa989a4c6e181af95ddc8b51f0eb81bbfb`

### PR synthetic merge-ref
- PR #344
- synthetic SHA: `13f8cb191c24eb0589cf4f5ba892d7b13b402bc5`
- pull_request Verify #753
- 1951 passed / 0 failed
- artifact id: 9821329483
- digest: `sha256:381635fc6256628f30de341e4c4f2d95b5418cf758120a7802a99f46b3b52ebd`

### Squash-main verification
- exact main SHA: `19851b9d40827b3ca5e3889c3858ca32c5602f67`
- push Verify #754
- 1951 passed / 0 failed
- artifact id: 9821356516
- digest: `sha256:f23470a2f0ab528fe64569dd7b8e7bcb3fcfee9ff8e783900ffbc3337f6b3317`

## Remaining integration blocker

Durable lineage exists. Telegram verified guidance/checklist still requires a read-only reconstruction/verification path that consumes this exact stored lineage and snapshot without invoking persistence application.

## Review classification

Architecture Review Required: Yes

Critical Review Required: No

Reason: the persisted Product Decision history schema now carries exact application lineage in the existing persistence owner. No new persistence owner/service/layer, business mutation, executor, finance rule or Ozon write was introduced.

GitHub Actions evidence is project CI evidence only.
`externally_verified=False`.
`data/users.json` unchanged.
