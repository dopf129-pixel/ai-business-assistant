# Decision 068 — Keep provisional FIFO estimates separate from factual FIFO

Date: 2026-11-23  
Status: accepted for the staged PR A–C implementation in PR #740.

## Decision

The provisional ledger is a separate analytical model. It reads exact-case, owner/store/product/offer/SKU-scoped evidence and produces explicitly non-authoritative ranges or timelines. It never supplies evidence to the factual FIFO readiness contract and never writes factual FIFO layers, allocations/events, current cost history, Return COGS, or canonical Period Profit.

Keep result statuses separate from factual lifecycle values: `NEED_INPUT`, `SOURCE_CONFLICT`, `SUMMARY_RANGE`, `TIMELINE_MODEL`, `TIMELINE_GAP`, and `STALE`. None may be represented as factual `READY`, `APPLIED`, `CONFIRMED`, or `COMPLETE`. A gap blocks the full timeline result but does not discard a valid independent summary range.

PR A uses a short-lived Telegram session for editable scenario assumptions and a pure summary calculator. PR B adds owner-triggered file inputs and a pure event replay; incomplete order/event coverage remains a gap. PR C stores immutable scenario snapshots in an additive, separately keyed estimate table with backup/restore coverage. That table is not a FIFO fact table and cannot participate in canonical profit without a separately approved future business decision.

## Required safeguards

- All evidence reads remain bound to the exact active case revision and tenant/store/SKU scope. Partial, stale, filename-only period candidates and conflicting control totals cannot produce a money estimate.
- Owner hypotheses stay explicit and are included in the result fingerprint. Unknown closing stock defaults to a wide interval; observed fragments do not become exact stock counts.
- Timeline events require source references, valid effective timestamps and non-ambiguous ordering. A gap preserves a separate summary result instead of fabricating exact sale-to-layer assignment.
- Saved estimates preserve their original input assumptions and source fingerprints. A stale estimate can be read historically but cannot silently become the current scenario or factual COGS.
- No path in this feature calls factual readiness, prepare, apply, canonical cost mutation, or a live Ozon/Telegram API.

## Rationale

The owner's operational history has gaps in physical acceptance, returns, order chronology and old-stock composition. Forcing incomplete evidence into factual FIFO would risk attributing a wrong cost to past sales. A distinct scenario ledger provides useful, reviewable uncertainty while protecting existing factual calculations and owner data.

## Consequences

- The UI must call every result a preliminary model and show its assumptions, periods, source coverage and uncertainty.
- PR A is useful independently for aggregate ranges but is not the complete FIFO feature.
- PR B may produce `TIMELINE_MODEL` only when chronology and stock transitions are reproducible; otherwise it reports `TIMELINE_GAP`.
- PR C may make provisional estimates durable, but persistence alone never authorizes their use as accounting facts.

