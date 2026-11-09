# FR03 — contracts for temporal FIFO replay and durable transition evidence

Status: design frozen for implementation; no implementation claim. Prepared 2026-11-09 as FR03 of [the review-blocker task](LUNA_FIFO_REVIEW_BLOCKERS_COMPLETION_TASK_2026-11-08.md).

This document makes the task's already-selected design concrete for implementation. It does not authorize a second inventory ledger, new profit formula, factual owner application, or relaxation of Decision 066's cutoff gate.

## 1. Temporal FIFO DTOs

### `FifoRateBoundaryEvent`

Add to `app/services/fifo_cost_allocation_service.py` as a frozen typed value:

| Field | Contract |
|---|---|
| `event_id: str` | Unique bounded replay event ID. |
| `new_rate_change_id: str` | Exact persisted rate ID or deterministic hypothetical proposal ID. |
| `new_unit_cost_rub: Decimal | str | int` | Positive RUB unit cost, normalized to kopecks by existing money rules. |
| `previous_rate_change_id: str \| None` | Null only for the first open-rate boundary. Otherwise exact active predecessor ID. |
| `previous_rate_remaining_units: int \| None` | Null only at the first boundary. Later boundaries require independently confirmed non-negative residual. `bool` is invalid. |
| `expected_older_finite_units: int \| None` | Null only at the first boundary. Later boundaries require exact finite balance immediately before the boundary, including confirmed restocks and excluding the open-rate residual. |
| `reconciliation_evidence_fingerprint: str` | Canonical 64-character lowercase SHA-256 digest of the independent stock/bridge reconciliation. |

Do not put `trusted`, `confirmed`, `status=READY`, or caller-authorized balance flags on this DTO. The DTO describes claimed/provenance-bound facts; the dated replay validator enforces the proof contract.

### `FifoDatedRateBoundaryEvent`

Add to `app/services/fifo_cost_replay_service.py`:

| Field | Contract |
|---|---|
| `event: FifoRateBoundaryEvent` | Exact allocation event. |
| `effective_at: str \| None` | ISO-8601 timestamp with explicit offset; only when the source proves an instant. |
| `effective_date: str \| None` | Strict `YYYY-MM-DD` store-local calendar date when evidence supports date precision only. |
| `store_timezone: str` | Valid IANA timezone; the current store setting is required, never inferred from the host. |
| `boundary_kind: str` | `EXACT_INSTANT` iff `effective_at` is present, or `END_OF_LOCAL_DATE` iff `effective_date` is present. |
| `boundary_evidence_fingerprint: str` | Exact selected confirmation/source fingerprint; must equal/refer to the event's reconciliation evidence. |

Exactly one of `effective_at` / `effective_date` is present. `END_OF_LOCAL_DATE` means the boundary follows all events on that local date; events on the next local date follow it. Convert exact instants to the store timezone before comparing with date-only boundaries. Never compare UTC date substrings. Same-position non-identical boundaries conflict; an exact idempotent duplicate collapses to one event.

`FifoCostReplayService.preview` gains keyword-only `rate_boundaries: Iterable[FifoDatedRateBoundaryEvent] = ()`, `complete_through` and `store_timezone`; old `open_rate`/`open_rate_effective_date` remains a compatible single-rate wrapper. Supplying both forms is `FIFO_RATE_CHAIN_CONFLICT`. Existing callers with no rate boundaries keep their prior output contract.

The replay result keeps current fields and adds:

- `rate_balances`: exact rate ID → derived remaining balance (`None` for the current open rate), unit cost and reconciliation fingerprint;
- allocation-line `basis_kind` and `rate_change_id` for rate-derived/materialized units, while preserving existing `layer_id` compatibility;
- `complete_through` and `store_timezone` in the sealed fingerprint.

These are derived replay balances, never receipt events, supplier shipment totals, or known physical quantity for an open rate.

## 2. Stable failures

Add typed/allowlisted errors while retaining existing contracts:

| Code | Condition |
|---|---|
| `FIFO_RATE_BOUNDARY_UNPROVEN` | Missing boundary descriptor, independent evidence fingerprint, or required residual/finite balance. |
| `FIFO_RATE_CHAIN_CONFLICT` | Wrong predecessor, competing rate input forms, duplicate identity with different content, or ambiguous boundary order. |
| `FIFO_RATE_BALANCE_MISMATCH` | Finite balance differs from the exact proof or physical total does not equal finite + prior open residual. |
| `FIFO_RATE_REPLAY_REQUIRED` | A repository operation would otherwise value/reconcile a rate without a complete current replay. |
| `FIFO_TRANSITION_EVIDENCE_MISSING` | Durable selected evidence is absent or does not cover the required scope/period. |
| `FIFO_TRANSITION_EVIDENCE_CONFLICT` | Durable evidence/hash/confirmation revisions conflict or fail verification. |
| `FIFO_TRANSITION_EVIDENCE_QUOTA_EXCEEDED` | Per-document or per-case bound exceeded; no truncation. |
| `FIFO_PHYSICAL_SALES_DOCUMENT_INVALID` | CSV bytes/schema/identity/rows are malformed or ambiguous. |
| `FIFO_TRANSITION_PREVIEW_STALE` | Current case/evidence/tax revision differs from the sealed basis. |
| `FIFO_TRANSITION_CONFIRMATION_EXPIRED` | Exact preview ticket/TTL expired. |

Errors contain no raw SKU, posting, shipment, product name, ciphertext, or owner-supplied lookup ID. UI may attach a safe next action/required period.

## 3. Replay invariants and boundary sequence

1. Initial confirmed finite layers remain FIFO queue head; first open rate adds zero units behind them.
2. Every later boundary links to the currently open predecessor by exact rate ID and reconciliation evidence.
3. At that instant, replayed finite remaining must equal `expected_older_finite_units`; predecessor-open residual must equal `previous_rate_remaining_units`.
4. Verify `physical_total = expected_older_finite_units + previous_rate_remaining_units`. Materialize only the predecessor residual as a finite derived balance at the queue tail; activate the new open rate after it.
5. Do not move the predecessor residual to replay start and do not infer residual from future sales. Past sales were valued at the rate active then.
6. A return referring to a closed/open rate restores a finite slice with the original sale cost and exact origin lineage at the return position, before the currently open rate. It does not amend prior sales COGS automatically.
7. Owner-approved partial-return policy (2026-11-09): when a returned quantity is linked to a sale but the source cannot identify individual units, assign it to the latest original FIFO allocation lines first (reverse allocation-line order). Earlier partial returns consume that same latest-first capacity before a later partial return is assigned. This is a deterministic costing convention, not evidence that Ozon identified the physical unit or cost layer. A full-sale return keeps the original allocation order.
8. Confirmed non-sale outflow consumes proven finite balances only. It never consumes the unknown open-rate quantity.
9. Cancellation guards remain authoritative. Cancelled rates are excluded by exact existing cancellation records; do not derive predecessor by `rate_sequence - 1`.
10. Physical event order uses proof boundaries and the store timezone, not `created_at`, database sequence, or rate ID. Existing bounded same-day order analysis and work limits remain.
11. Unknown/missing proof is incomplete, not zero. No latest-rate-for-history fallback.

## 4. Transition persistence and application contract

Repository remains the only SQL, tenant, migration, CAS and commit authority in `ozon_assistant.db`; Planning schema and `PRAGMA user_version` are untouched. Expected FIFO migration is v15→v16 after confirming the live schema constant is still 15.

Additive append-only records:

- `fifo_cost_transition_bridge_evidence`: scoped typed evidence metadata, exact revisions, period/as-of, completeness, canonical fingerprint and encrypted payload;
- `fifo_cost_transition_evidence_confirmations`: immutable owner confirmation bound to the exact evidence ID/hash, typed fields, scope and case revision;
- `fifo_cost_allocation_rate_balances`: immutable allocation-revision output balances by exact rate lineage, including restored origin sale when present.

The repository's public keyword-only methods are `append_transition_bridge_evidence`, `confirm_transition_evidence`, `read_transition_bridge_evidence`, and `read_transition_preview`. Scope comes from tenant context; all SQL helpers compose within caller-owned transactions and do not commit an external transaction. Append/update/delete triggers, FK, scoped indexes, idempotency and quotas follow existing FIFO conventions. Migration failure must roll back without altering v15 evidence, hashes or planning state.

Evidence kinds are the task's exact allowlist: `PHYSICAL_SALES_DOCUMENT`, `FINANCE_IDENTITY_SNAPSHOT`, `MOVEMENT_COVERAGE`, `CUTOFF_SELECTION`, `OPENING_COMPOSITION`, `RATE_BOUNDARY_PROOF`, `PERIOD_SUMMARY_SNAPSHOT`, `TAX_POLICY_SNAPSHOT`. Generic user JSON cannot set trusted completeness. Missing/invalid tenant Fernet key is a blocker; never store plaintext raw references as fallback.

Limits: metadata ≤256 KiB, confirmation ≤64 KiB, physical CSV ≤50,000 rows/16 MiB encrypted, case aggregate ≤64 MiB/100 document or snapshot versions, selected identity/event set ≤100,000. Exceeding limits returns a specific quota error without dropping rows.

### N / N+1 revisions

- Evidence bundle, exact case revision, identity, case basis and historical selection are read under tenant/store/product/offer/SKU scope. The READY preview basis is case revision **N**.
- `prepare` recomputes the bundle, bridge, read-only baseline/candidate reconstruction and canonical TaxService/Period Profit impact. It persists a preview seal and advances case revision to **N+1 / READY_TO_CONFIRM**. The bridge stored in the seal is bound to revision N; no FIFO business rows are written.
- `read_preview` reads that exact persisted preview ID and never recomputes or refreshes it.
- `apply` requires explicit case revision N+1, preview ID, preview fingerprint and stable idempotency key. It validates the seal's revision N evidence basis, current authorization and exact scope, then commits rate/event/allocation/projection/cutoff mappings/APPLIED atomically.
- New evidence appends a new case revision and returns READY to AWAITING_EVIDENCE; it never edits the old seal.
- Exact idempotent retry after commit/restart is looked up before current preview TTL or changed source/tax revalidation and returns the original commit. Any non-exact retry is stale/conflict.
- HTTP/worker wait is outside DB write transactions. Invalidation occurs only after commit and cannot repeat business writes.

No Telegram input can carry a bridge, impact, `ready=True`, or trusted completeness flag.

## 5. Fixed public service relationships

- `FifoCostTransitionEvidenceService.load(case_id, identity, expected_case_revision)` reconstructs a read-only immutable typed evidence bundle from repository records.
- `FifoCostTransitionReviewService` consumes that service, creates the real bridge using the existing normalizers/adapter and checks readiness without HTTP or writes.
- `FifoCostTransitionApplyService` exposes only `prepare`, `read_preview`, `apply` with the exact arguments documented in the task; it owns no second formula or SQL.
- `FifoCostPhysicalSalesImportService` validates the exact UTF-8/BOM, semicolon CSV template in the task; Telegram selection/save/confirm is case/revision-bound and durable. It is owner-imported, not an official Ozon XLSX.
- `create_fifo_cost_transition_workflow` is the one production assembly used by `create_telegram_assistant`; the runtime and the public factory share the same evidence/review/apply objects. Tests replace HTTP/clock/delivery/path IO only.

## 6. Independently calculated numeric controls

All amounts use Decimal RUB and canonical half-up kopeck rounding. The first five MR cases share one chain, boundaries in `Europe/Moscow`; synthetic clock completes no earlier than local end of 15 November.

| Control | Independent arithmetic | Expected |
|---|---|---|
| MR01 first sale | `3×21.00 + 2×14.65` | `92.30`; finite layer at 14.65 has 98 remaining. |
| MR02 second rate | `98×14.65 + 10×14.65 + 2×16.00` | `1614.20`; exactly 10 prior-open units materialized; current open R2 physical quantity remains unknown. |
| MR03 third rate | `7×16.00 + 3×18.00` | `166.00`; rate history aggregate MR01–MR03 is `1872.50`; stock decrease 108→7 accepted only because complete bridge explains sales. |
| MR04 returned R2 unit | Origin rate cost `16.00×1` | One finite restored unit at 16.00; prior sales COGS unchanged. |
| MR05 re-sell restored unit | `1×16.00`; aggregate adds 16.00 to MR01–MR03 | Sale COGS `16.00`; aggregate `1888.50`. |
| MR06 non-sale path | Outflow `1×21.00`, then sale `2×21.00 + 3×14.65` | Outflow `21.00`, sales COGS `85.95`, separately. |
| MR07 unknown open qty | `4×14.65` | Sales COGS `58.60`; known inventory remains unknown; outflow is blocked. |
| MR12 tax NONE | `400−105`, `400−92.30` | Profit `295.00→307.70`, delta `12.70`. |
| MR13 USN income | Tax `6%×(1000−200)=48`; profit `400−COGS−48` | Profit `247.00→259.70`, delta `12.70`. |
| MR14 USN income-minus-expenses | Tax `15%×(400−COGS)` with minimum 1% revenue; round half-up | Tax `44.25→46.16`; profit `250.75→261.54`, delta `10.79`. |
| MR15 minimum tax | Minimum `1%×1000=10`; profit `110−COGS−10` | Tax `10→10`; profit `−5.00→7.70`, delta `12.70`. |

MR08–MR11 and MR16–MR22 retain the exact input/expected controls in sections 5 and 6 of the implementation task. Verify with independent `Decimal` expectations and the existing canonical TaxService. Do not change TaxService to fit this table.

## 7. Verification gates

- Pure kernel: MR01–MR07 with no SQLite; prove per-line unit and rate IDs, no negative finite balances and unknown open-rate quantity.
- Replay: MR08–MR10, exact permutation/duplicate semantics, bounded ambiguous-order path.
- Repository: MR02–MR05 through public application methods and append-only current allocation revisions, including restart.
- Evidence/apply: exact-scope/hash/confirmation/period/tax/cutoff, stale/CAS/idempotency, rollback and no-write-before-confirm.
- Production: one shared factory, real importer/normalizers/bridge/TaxService/impact/repository/Telegram routing; replace only IO boundaries in tests.
- Full acceptance: MR01–MR22 and prior N01–N40; source-incomplete owner case remains blocked and preserved.

No verification item allows live Ozon/Telegram access or a real bot start.
