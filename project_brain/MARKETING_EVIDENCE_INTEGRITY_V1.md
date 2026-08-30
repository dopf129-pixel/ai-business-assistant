# Marketing Evidence Integrity V1

Date: 2026-08-30
Stages: v548-v553
Architecture Review Required: Yes

## Gap

The existing Marketing executor had no marketing data service or API dependency,
but returned statements that advertising channels had been checked and
opportunities found.

That was invented runtime evidence.

## Contract

- marketing actions require explicit `marketing_evidence_available=True`;
- recommendation requires a non-empty `marketing_context`;
- executor requires a non-empty list of factual string `evidence`;
- executor formats supplied evidence only;
- missing/malformed evidence returns an error;
- router `run()` therefore enters the existing FAILED lifecycle;
- unavailable marketing evidence creates no marketing action and the generic
  fallback reports insufficient data.

## Safety

No marketing API, campaign mutation, Ozon mutation, Product Decision execution,
Product Task Draft execution, persistence-format change or `data/users.json`
change is introduced.

Architecture Review Required: Yes because seller-facing execution semantics
change across an existing recommendation/executor boundary.
