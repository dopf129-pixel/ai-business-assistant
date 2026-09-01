# CURRENT_CHECKPOINT_V991_V1000

Date: 2026-09-01

## Product Decision Assortment Overview Integrity

Production package:

`v991-v1000: Product Decision Assortment Overview Integrity`

Goal:

Prevent contradictory or malformed seller-facing assortment overview data from becoming plausible Product Decision counts, proposal statistics, pagination, or Telegram action buttons.

## Verified behavior

- overview requires explicit successful result shape;
- every decision row requires `error=False`;
- SKU is an exact non-empty string and duplicate SKUs fail closed;
- Product Decision type → priority pairing is canonical;
- decision counts are exact positive integer maps and must equal recomputed row counts;
- proposal counts are exact positive integer maps and must equal recomputed nested proposal counts;
- actionable proposal count exactly equals rows with `action_required=True`;
- nested proposal `action_required` is an exact boolean;
- nested proposals remain non-executable with `execution_allowed=False`;
- nested proposal automation remains prohibited;
- unknown proposal types fail closed;
- contradictory overview state is rejected before keyboard generation;
- valid mixed overview remains deterministic and non-mutating.

## SHA-bound verification evidence

### Entering exact main

- SHA: `a942844466b5d2db66fcac1722b0a1876613ee6e`
- push Verify #702
- 1891 passed / 0 failed
- artifact id: 9817171958
- digest: `sha256:03170acf5655d8063c710a25d7fdba1fd74a18a79da98a4be1dcf80ae317a7a7`

### Failed intermediate SHA 1

- SHA: `3fe8ef0caa6b03a5dabbabae463cb0037a4c9ca5`
- push Verify #704
- 1882 passed / 9 failed
- artifact id: 9817272177
- digest: `sha256:5470eb5134c8288016d6c42a669dfac062e755a9723a56427c037cf79116a475`
- strict validator exposed nine legacy fake-producer shapes;
- this SHA remains failed evidence permanently.

### Failed intermediate SHA 2

- SHA: `86b6e9063c1a9cfa500d4e0409ba6668623c5321`
- push Verify #705
- 1892 passed / 9 failed
- artifact id: 9817332979
- digest: `sha256:dd7d4a4787e52797857bbac300e457a2e8c4642cd8dcf707b1646e06d6e0d68b`
- v991-v1000 regressions were present, while the same legacy fake-producer shapes still failed;
- this SHA remains failed evidence permanently.

### Failed intermediate SHA 3

- SHA: `0b2da626f71a45adf54f0f9f0dbfd8b5a8e75353`
- push Verify #706
- 1898 passed / 3 failed
- artifact id: 9817403954
- digest: `sha256:d2ab4fe9f3f2b389013b7743911893ceb305e4621edd05be33592b9225296957`
- three remaining legacy assertions/proposal fixtures used pre-contract priority/proposal semantics;
- this SHA remains failed evidence permanently.

Production validation was not weakened. Legacy fakes were aligned to the current canonical producer contract.

### Exact final feature head

- SHA: `63870a305972f7b7e8f33cad251fc6f13235d1fc`
- push Verify #707
- 1901 passed / 0 failed
- artifact id: 9817446388
- digest: `sha256:68ef4c6060abc47a59e1da2a224a114a57120f1b68057c1d126ab9a9a738e954`

### PR synthetic merge-ref

- PR #334
- synthetic SHA: `1bbee7e03477b197a474a6807093d6ee344b7505`
- pull_request Verify #708
- 1901 passed / 0 failed
- artifact id: 9817534964
- digest: `sha256:25295b20c6603da3da391490513303b4e977088399dba4a8a957ff151eb756e6`

This proves only the PR synthetic integration revision.

### Squash-main verification

- exact main SHA: `84d714909d5082958bf2bb21a30b7b097eb17955`
- push Verify #709
- 1901 passed / 0 failed
- artifact id: 9817585844
- digest: `sha256:3095688649247460b1a6ab0028cd31431d77a1845a8c30cf7c00f34239653100`

## Review classification

Architecture Review Required: Yes

Critical Review Required: No

Reason: an existing seller-facing Telegram overview trust boundary was materially hardened and the package exceeds the architecture-review size threshold. No Product Decision threshold, persistence owner, execution layer, or business mutation path was introduced.

GitHub Actions evidence is project CI evidence only.
`externally_verified=False`.
`data/users.json` unchanged.
