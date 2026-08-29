# Roadmap Note — Autonomous Assistant v18

Date: 2026-08-29

Completed:

- read-only refresh results can be normalized into a freshness evidence update candidate;
- only canonical `*_source_recorded_at` fields count as source evidence;
- observation aliases remain observation-only;
- cache/request/lifecycle timestamps are not promoted;
- no Product Decision or task draft mutation occurs.

Next boundary:

Introduce a separately reviewed evidence-application workflow only if product policy permits updating stored freshness evidence. Any such application must remain independent from Product Decision execution and must re-run the existing freshness guard after evidence is applied.
