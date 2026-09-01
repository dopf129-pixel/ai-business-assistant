# CURRENT_CHECKPOINT_V1011_V1020

Date: 2026-09-01

## Product Decision Unit Economics Result Integrity

Production package:

`v1011-v1020: Product Decision Unit Economics Result Integrity`

Goal:

Prevent malformed, exception-throwing, contradictory or non-finite Product Unit Economics results from becoming finance facts in seller-facing Product Decisions.

## Verified behavior

- Unit Economics query exceptions are sanitized;
- downstream `error` must be an exact boolean;
- explicit `error=True` means economics unavailable/unknown, never zero;
- successful results require exact boolean `available`;
- `missing_fields` is a unique list of non-empty strings;
- decision-relevant numeric values reject booleans, NaN and infinity;
- `available=False` cannot claim profit or margin;
- confirmed returns-adjusted profit requires `returns_finance_complete=True` and known per-delivered-unit returns cost;
- estimated returns profit requires exact `returns_estimate_available=True` and required estimate evidence;
- malformed economics fails closed with `PRODUCT_DECISION_UNIT_ECONOMICS_RESULT_INVALID`;
- malformed economics is not cached;
- no finance formula, fee subtraction, tax policy or Product Decision threshold changed.

## SHA-bound verification evidence

### Entering exact main
- SHA: `116bbbfe62c6c0f27d33764ffdeff78e14a31550`
- push Verify #721
- 1911 passed / 0 failed
- artifact id: 9818600357
- digest: `sha256:389ba9d7c14d8d820cbbeec43da6f0230da4513fd2660d45b0b611bae13f7b99`

### Failed intermediate 1
- SHA: `c27b1fbfba804d36167855228f1881c08c4ef506`
- push Verify #723
- 1917 passed / 4 failed
- artifact id: 9818770098
- digest: `sha256:4befff3abaa04a2495c064f894ccbf62e4f351ff4c0dcd788be848ab6de4828e`

### Failed intermediate 2
- SHA: `1114863bdc5b23969fe8cf2d3c9166fe5e7cd523`
- push Verify #724
- 1918 passed / 3 failed
- artifact id: 9818796986
- digest: `sha256:2f1512681c65a5b470a063e260b62f5689c448a68ad891a0a0bd561355009eda`

Both failed SHAs remain failed evidence permanently.

### Exact final feature head
- SHA: `fa9cd0e874347ba00320c8e9c36c85d0efb530a0`
- push Verify #725
- 1921 passed / 0 failed
- artifact id: 9818832270
- digest: `sha256:000475d4668fa695df71c6e226f8f988fad57e9a4703d4c83928c0c74c9b3319`

### PR synthetic merge-ref
- PR #338
- synthetic SHA: `8014a74ae903863da672ee4b82f9fb565ad3d6cc`
- pull_request Verify #726
- 1921 passed / 0 failed
- artifact id: 9818861081
- digest: `sha256:425a071b7d1b996951d6f5ae0cde8858a94c7cf2940155ec582ff81eab8c47fd`

### Squash-main verification
- exact main SHA: `982dc4f58fec6172a4fa99475ae72800c107981f`
- push Verify #727
- 1921 passed / 0 failed
- artifact id: 9818889552
- digest: `sha256:ceda4fa16efb58e088edcf5799e82c9b2afa41ac1d2de46a45fa46598b3d6170`

## Review classification

Architecture Review Required: Yes

Critical Review Required: No

Reason: an existing finance-sensitive Product Decision downstream contract was materially hardened. No new service/layer, persistence owner, finance formula, execution path or mutation boundary was introduced.

GitHub Actions evidence is project CI evidence only.
`externally_verified=False`.
`data/users.json` unchanged.
