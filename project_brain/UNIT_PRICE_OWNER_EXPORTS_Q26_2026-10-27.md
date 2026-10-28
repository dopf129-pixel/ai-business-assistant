# Unit-price owner exports — Q26 acceptance

Date: 2026-10-27
Stage: Q26 — unified owner exports
Status: VERIFIED

## Result

The unit-price calculator now exports saved comparisons, tariff profiles and observation results as CSV or JSON. Exports use the existing analytics serializer and Telegram document transport. They preserve exact stored revisions, owner-facing identity, evidence basis, quality/completeness states and unknown values. Export callbacks do not refresh Ozon data or recalculate stored results.

The tariff profile screen and files are generated from the same frozen scenario snapshot. The screen is bounded to 32 rows and indicates when the file contains more; the domain export allows at most 20 profiles × 20 segments (400 rows). Shared serializer limits remain active: 5,000 rows, 64 columns, 2 MiB.

## Evidence

- `tests/test_unit_price_owner_exports.py`: fixed schemas, CSV/JSON row parity, exact revision metadata, unknown versus zero, identity checks, internal-record ID redaction, tariff segment coverage and bounds.
- `tests/test_telegram_unit_price_observation_runtime.py`: observation and comparison export buttons; reopen/export uses stored revisions and makes no collection-source call.
- `tests/test_telegram_unit_price_tariff_profile_runtime.py`: screen/file consistency, exact scenario revision, callback byte limit and owner/store scope.
- Existing serializer/document contract tests were included.
- Focused Windows/Python 3.12.10 profile: **39 passed in 2.38s**.
- Linked price-planning, tariff, observation and export profile: **439 passed across 30 targets in 10.25s**.
- `py_compile` for 9 changed Python files: passed. `git diff --check`: passed. `git diff -- data`: empty.

## Scope and limitations

Tests use synthetic records and the existing document adapter contract. No live Ozon requests, `.env`, owner database or real Telegram send were used. Full repository pytest and exact-head Windows/Linux/Docker CI remain Q33–Q35. `DECISIONS.md` is unchanged because the stage reuses Decision 061, the shared export serializer and existing document transport.

## Review focus

Review redaction and allowlists in all three export paths, confirm screen/file projection parity, verify that old comparison and observation revisions remain immutable, and check that no export callback initiates source reads.
