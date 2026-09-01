# CURRENT_CHECKPOINT_V981_V990

Date: 2026-09-01

## Product Decision Result Integrity

Production package:

`v981-v990: Product Decision Result Integrity`

Goal:

Prevent malformed, exceptional, identity-mismatched, or contract-inconsistent Product Decision service results from reaching seller-facing history, action proposal, cache, task-draft lifecycle, assortment aggregation, or Telegram presentation.

## Verified behavior

- `decision_service.decide()` must return a mapping;
- unexpected result fields such as injected `error` / `code` are rejected;
- Product Decision `product_id` and `sku` exactly match the queried product;
- decision type and priority pairing is canonical;
- confidence is canonical and `LOW` is reserved for `INSUFFICIENT_DATA`;
- reasons are non-empty, canonical, unique Product Decision reason strings;
- missing-data entries are canonical unique non-empty strings;
- malformed/exceptional results become deterministic `PRODUCT_DECISION_RESULT_INVALID`;
- invalid decisions cannot enter history, proposal, cache, or task-draft lifecycle;
- Telegram renders a neutral failure message and exposes no keyboard for invalid decision state;
- valid canonical decisions preserve prior seller-facing behavior.

## SHA-bound verification evidence

### Entering exact main
- SHA: `8d3158fbfa0e4e29d40fa0ce1d8b8f373fc74744`
- push Verify #690
- 1881 passed / 0 failed
- artifact id: 9815643598
- digest: `sha256:037368b6a69b736e90f0864427528c64f89392970774e7d61e3e247d0f3ef820`

### Cancelled intermediate branch pushes
- `f21c1ca4b21b57a634a502ecb754e93fabb78e18`: Verify #693 cancelled;
- `689fd2b9db65861f8853251accb0f2a3e0cf86d8`: Verify #694 cancelled;
- no verification claim is transferred from those SHAs.

### Failed intermediate feature SHA
- SHA: `8a286947bdc5862834a05794e330d87ef370ffe7`
- push Verify #695
- 1889 passed / 2 failed
- artifact id: 9816934445
- digest: `sha256:289d68239b8811b713c72e00e5185759b6b76242e41c9ee47f84fd0b0085ac06`
- both failures were legacy freshness tests whose local fake decision returned `HOLD_STOCK` with noncanonical `reasons=[]`;
- production validation remained strict; fixture was updated to the canonical producer contract;
- this SHA remains failed evidence permanently.

### Exact final feature head
- SHA: `8b90c11763622cc413802a488171738cf2332a1a`
- push Verify #696
- 1891 passed / 0 failed
- artifact id: 9816964776
- digest: `sha256:d6a8a29cc277e9229f782020588d2bbbd6ffad6b61088d223bcf577d7edecf21`

### PR synthetic merge-ref
- PR #332
- synthetic SHA: `da5e7689cc87a0597944f371dfe4246082d92806`
- pull_request Verify #697
- 1891 passed / 0 failed
- artifact id: 9816994511
- digest: `sha256:6824d8be6988720e5bb1abe1c0ab10cbab198eb359e6ba22f9cd8cccb578ecdc`

This proves only the PR synthetic integration revision.

### Squash-main verification
- exact main SHA: `5f0534bb72dba2471c3c339a69cd7041552dfb4a`
- push Verify #698
- 1891 passed / 0 failed
- artifact id: 9817030052
- digest: `sha256:c7af1301e9eaa791da1e11038c30503dfb79b2099a91731de90579e625a35830`

## Review classification

Architecture Review Required: Yes

Critical Review Required: No

Reason: an existing seller-facing Product Decision result contract was materially hardened and the production/test diff exceeds the architecture-review size threshold. No new persistence owner, runtime route, execution layer, threshold, or business mutation path was introduced.

GitHub Actions evidence is project CI evidence only.
`externally_verified=False`.
`data/users.json` unchanged.
