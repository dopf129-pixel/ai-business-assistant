# Autonomous Assistant v20 — Freshness Evidence Application Approval Contract

Status: complete on feature branch pending merge.

This block adds a non-persistent approval boundary after v19 validation preview.

Completed:

- approval readiness requires exact draft/candidate/preview identity;
- request identity must match;
- preview must be read-only and freshness-validated;
- candidate and preview evidence must match exactly after whitelisting;
- approval is never granted automatically;
- evidence is never applied by this contract;
- Product Decision execution remains disconnected.

Validation: targeted assistant-side pytest `8 passed in 0.05s`.

Next safe boundary: an explicit approval signal contract may record a user approval decision for this evidence-only workflow. It must not apply evidence, recompute Product Decisions, or enable business execution by itself.
