# Freshness Evidence Write Protocol v1 — v184–v188

Date: 2026-08-30

Architecture Review Required: **Yes** — this is the final safety boundary before any future mutation-capable adapter.

## Goal

Continue the freshness-evidence lifecycle after v179–v183 without inventing a storage write primitive. The repository still has no confirmed versioned compare-and-set adapter for task-draft freshness fields, so this batch defines the protocol that such an adapter must satisfy without invoking one.

Workflow:

`v183 write handoff + executor audit → v184 reread/stale check → v185 canonical write request → v186 APPLY/REJECT → v187 adapter invocation contract → v188 audit`

No stage in this batch writes data.

## v184 — write protocol eligibility

`build_write_protocol_eligibility(write_handoff, executor_audit, reread_snapshot)` requires an exact canonical write handoff and executor audit from the previous lifecycle plus a fresh reread snapshot.

It fail-closes unless:

- `application_write_handoff_id` is recomputed exactly from `executor_authorization_id`;
- `executor_admission_audit_id` is recomputed exactly from the same authorization ID;
- target revision and version still match;
- every proposed operation has exact `{field, before, after}` schema;
- operation fields are whitelisted, unique and deterministically ordered;
- no operation is a no-op;
- each `before` value still equals the reread value;
- all mutation/execution safety flags remain false.

A successful v184 result means stale-lineage validation passed at protocol-construction time only. It is not a write.

## v185 — canonical write request

`build_write_request(eligibility)` creates an immutable request containing:

- exact expected revision;
- exact expected version;
- exact sorted write operations;
- mandatory read-back verification requirement.

The downstream validator recomputes the full local lineage `executor_authorization_id → application_write_handoff_id → write_protocol_eligibility_id → write_request_id` rather than trusting supplied child IDs.

## v186 — explicit APPLY / REJECT

`build_write_request_decision(write_request, decision)` accepts only `APPLY` or `REJECT`.

`APPLY` approves creation of an adapter invocation contract only. It deliberately keeps `write_adapter_invocation_allowed=False` and does not persist or mutate anything.

## v187 — adapter invocation contract

`build_write_adapter_invocation_contract(write_decision)` is available only after canonical `APPLY`.

The contract requires:

- compare-and-set semantics;
- exact expected revision/version;
- exact write operations;
- post-write read-back verification.

It still explicitly sets `write_adapter_invocation_allowed=False`. No adapter is called by this module.

## v188 — protocol audit

`build_write_protocol_audit(...)` verifies the canonical eligibility/request/decision chain and, for approved writes, requires an exact matching adapter contract.

For rejected writes an adapter contract is forbidden.

The audit recomputes lineage rather than trusting mutually consistent but forged intermediate IDs.

## Safety invariants

- no persistence;
- no task-draft mutation;
- no Product Decision mutation/recomputation;
- no Ozon mutation;
- no Action Executor connection;
- no business execution permission;
- no source timestamp fabrication;
- observation timestamps do not prove source freshness;
- only six existing freshness timestamp fields are accepted;
- duplicate, unordered, unknown-field and no-op operations fail closed;
- stale revision/version/current-value evidence fails closed;
- `APPLY` is protocol approval, not adapter execution.

## Why no actual write yet

The existing repository inspection still did not reveal a production storage primitive with the required target identity, compare-and-set revision/version behavior and read-back verification. Introducing an ad-hoc write would create hidden mutation semantics and bypass the architecture established by the previous lifecycle.

A future mutation-capable stage must provide an explicit adapter implementing these guards and must separately prove read-back before any application-success claim.

## Validation

Focused regression coverage:

- `tests/test_product_task_freshness_evidence_write_protocol_v184_v188.py`
- `tests/test_product_task_freshness_evidence_write_protocol_lineage.py`

Latest full-suite baseline supplied by the user before v174+: **982 passed**.
