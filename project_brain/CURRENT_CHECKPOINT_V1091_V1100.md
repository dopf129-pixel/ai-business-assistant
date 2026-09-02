# CURRENT_CHECKPOINT_V1091_V1100

Date: 2026-09-02

## Tax Configuration Persistence & Result Integrity

Production package:

`v1091-v1100: Tax Configuration Persistence & Result Integrity`

Goal:

Keep persisted tax configuration finite, bounded, fail-closed and atomically durable while preserving the existing TaxService calculation contract.

## Verified behavior

- persisted tax policy root must be a mapping;
- tax and minimum-tax rates reject booleans, non-numeric values, NaN/inf, negatives and values above 100%;
- NONE preserves explicit zero-tax normalization;
- malformed and truncated durable tax policy is treated as unconfigured instead of raising;
- valid policy is serialized before touching the durable target;
- valid policy is written to an fsynced temp file then atomically replaces the target;
- failed replace reports `TAX_CONFIGURATION_SAVE_FAILED`;
- failed replace cleans temporary data and preserves the previous durable file;
- production core construction survives malformed tax config and leaves tax unknown;
- TaxService formulas/calculation branches are unchanged.

## SHA-bound verification evidence

### Entering exact main
- SHA: `5b2e3ddcc579da318685f3eea4d730119a27f6e9`
- push Verify #792
- 1991 passed / 0 failed
- artifact id: 9844280616
- digest: `sha256:c642dfd52b1e678cc8939c46f757204cdb1344b475562a389fef02237bfda968`

### Exact final feature head
- SHA: `8cc003f6fa66eb499c67d7d3d74f90c0c75abecf`
- push Verify #794
- 2001 passed / 0 failed
- artifact id: 9845404869
- digest: `sha256:b5fbdff88ec8df18c47b60b0ede4742010b5d9fcc481d3eaba784d24a1a2c364`

### PR synthetic merge-ref
- PR #354
- synthetic SHA: `5167b644bc53edc27a40c7b15c7068e0c669d2fc`
- pull_request Verify #795
- 2001 passed / 0 failed
- artifact id: 9845447757
- digest: `sha256:179121b28a8375c804e9a6d63ba8f30155d473cd9d25a9373b5117f3f58db4df`

### Squash-main verification
- exact main SHA: `38e54ddc6d289f0f75121cc63efa0268ef2784f8`
- push Verify #796
- 2001 passed / 0 failed
- artifact id: 9845488004
- digest: `sha256:a5c706c2d9e0f3613a9129506b2ae9fc1d66acbb57d1f3ec21fd06cd64ede38e`

## Remaining blocker

No blocker introduced by this package.

Business execution remains separately blocked pending explicit architecture and authorization.

## Review classification

Architecture Review Required: No

Critical Review Required: No

Reason: this package hardens validation and atomic durability inside the existing TaxConfigurationService owner. No tax formula, new persistence owner, retry, business mutation, execution permission or Ozon write was introduced.

GitHub Actions evidence is project CI evidence only.
`externally_verified=False`.
`data/users.json` unchanged.
