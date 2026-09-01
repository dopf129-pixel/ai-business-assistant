# Verification Status

Date: 2026-09-01

## Latest verified product baseline

`9a504323b6b4bb0adb2a6d5a75507b4c0b6f19f9`

Latest merged production-correctness batch:

`v931-v940: Product Decision User Action Learning Evidence Quality Summary Integrity`

### Entering exact-main verification
- exact main: `d3c7f5837133cfa0b14b0a0995545370e99a3a0e`
- Verify #647
- 1831 passed / 0 failed
- artifact id: 9812673839
- digest: `sha256:ad51ebfbdb81ef1558778afbd61932828eab0b6da4247dcbcd864f8e8dec848c`

### Failed intermediate feature SHA
- `849b0d0e78e441f3080631419ecbc0ea192890ec`
- Verify #649
- 1840 passed / 1 failed
- artifact id: 9812759261
- digest: `sha256:39dd79bc32a0afbafb9f2f6c9e7743bfd4627f43c5e28c98b2d85b899eeddb2e`
- test-fixture failure before production builder; remains failed evidence.

### Exact final feature-head verification
- `e600b6726a9eadadce65f8b803b74608b79d96d0`
- Verify #650
- 1841 passed / 0 failed
- artifact id: 9812782745
- digest: `sha256:334db6de14385d4f76238013d40dcabf4e9279395f16afab1099b4e8be9313e9`

### PR merge-ref integration verification
- PR #322
- synthetic SHA: `5b58b853a5e8b402a4e5b61ffd68f4174416b190`
- Verify #651
- 1841 passed / 0 failed
- artifact id: 9812815058
- digest: `sha256:f969bfd7b258d5b858c3717719fb34a9b50a8cc8004ec6ff9ac7bddda9543412`

### Post-merge exact-main verification
- exact main: `9a504323b6b4bb0adb2a6d5a75507b4c0b6f19f9`
- Verify #652
- 1841 passed / 0 failed
- artifact id: 9812849891
- digest: `sha256:8c83aea0ed5003f87584ca25fb95117af6c558439bcd1cf4306c48fa7c5a3d37`

## Verification policy

Exact branch push verification proves only that exact branch head.
Pull-request runs prove only their synthetic merge refs.
Every squash-main SHA requires its own exact push verification.
Failed SHAs remain failed evidence permanently.
Missing evidence remains unknown and is never interpreted as zero/clean.
Workflow evidence is not independent external verification;
`externally_verified=False`.
