# Verification Status

Date: 2026-09-01

## Latest verified product baseline

`84d714909d5082958bf2bb21a30b7b097eb17955`

Latest merged production-correctness batch:

`v991-v1000: Product Decision Assortment Overview Integrity`

### Entering exact-main verification
- exact main: `a942844466b5d2db66fcac1722b0a1876613ee6e`
- Verify #702
- 1891 passed / 0 failed
- artifact id: 9817171958
- digest: `sha256:03170acf5655d8063c710a25d7fdba1fd74a18a79da98a4be1dcf80ae317a7a7`

### Failed intermediate SHA #704
- `3fe8ef0caa6b03a5dabbabae463cb0037a4c9ca5`
- Verify #704
- 1882 passed / 9 failed
- artifact id: 9817272177
- digest: `sha256:5470eb5134c8288016d6c42a669dfac062e755a9723a56427c037cf79116a475`

### Failed intermediate SHA #705
- `86b6e9063c1a9cfa500d4e0409ba6668623c5321`
- Verify #705
- 1892 passed / 9 failed
- artifact id: 9817332979
- digest: `sha256:dd7d4a4787e52797857bbac300e457a2e8c4642cd8dcf707b1646e06d6e0d68b`

### Failed intermediate SHA #706
- `0b2da626f71a45adf54f0f9f0dbfd8b5a8e75353`
- Verify #706
- 1898 passed / 3 failed
- artifact id: 9817403954
- digest: `sha256:d2ab4fe9f3f2b389013b7743911893ceb305e4621edd05be33592b9225296957`

These failed revisions remain failed evidence permanently. Their failures were legacy fake-producer compatibility gaps exposed by the stricter canonical overview contract; production validation was not weakened.

### Exact final feature-head verification
- exact SHA: `63870a305972f7b7e8f33cad251fc6f13235d1fc`
- Verify #707
- 1901 passed / 0 failed
- artifact id: 9817446388
- digest: `sha256:68ef4c6060abc47a59e1da2a224a114a57120f1b68057c1d126ab9a9a738e954`

### PR merge-ref integration verification
- PR #334
- synthetic SHA: `1bbee7e03477b197a474a6807093d6ee344b7505`
- Verify #708
- 1901 passed / 0 failed
- artifact id: 9817534964
- digest: `sha256:25295b20c6603da3da391490513303b4e977088399dba4a8a957ff151eb756e6`

This proves only the PR synthetic integration revision.

### Post-merge exact-main verification
- exact main: `84d714909d5082958bf2bb21a30b7b097eb17955`
- Verify #709
- 1901 passed / 0 failed
- artifact id: 9817585844
- digest: `sha256:3095688649247460b1a6ab0028cd31431d77a1845a8c30cf7c00f34239653100`

## Verification policy

Exact branch push verification proves only that exact branch head.
Pull-request runs prove only their synthetic merge refs.
Every squash-main SHA requires its own exact push verification.
Failed SHAs remain failed evidence permanently.
Cancelled/pending SHAs carry no transferable success claim.
Missing evidence remains unknown and is never interpreted as zero/clean.
Workflow evidence is not independent external verification;
`externally_verified=False`.
