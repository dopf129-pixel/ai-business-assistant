# Current Checkpoint v620-v628

Date: 2026-08-30

Package: User Storage Load Integrity v1

## Verified implementation

The existing AssistantUserStorageService now fails closed when its backing JSON
store is corrupted, unreadable, or structurally invalid instead of silently
turning that condition into a new empty writable store.

Verified behavior:

- malformed JSON load sets an explicit unavailable state;
- non-dictionary storage roots are rejected;
- load-error state blocks user creation, memory writes, and history writes;
- the original malformed/unreadable file is not overwritten through normal storage calls;
- save failures return explicit errors rather than false success;
- uncommitted in-memory user creation is removed when save fails;
- uncommitted memory/history changes are rolled back in memory when save fails;
- malformed existing user records are not replaced;
- absent-store creation and valid memory/history persistence remain compatible;
- no additional persistence layer was introduced.

## Architecture Review

Architecture Review Required: Yes.

Reason:

- the production user-storage persistence owner contract changed;
- package exceeds the normal meaningful-change threshold and is persistence-adjacent.

Critical Review Required: No.

Review result:

- existing owner hardened in place;
- no parallel persistence owner/layer;
- no Product Decision/Product Task Draft execution;
- no Ozon mutation;
- no business execution capability added;
- no path/PID/secret exposure;
- repository `data/users.json` untouched.

## SHA-bound verification evidence

### Entering verified main

- exact SHA: `e8a133baefb6743d4248842a8ce26069606b5652`
- push Verify #300
- tests: 1519 passed / 0 failed
- artifact: `verification-e8a133baefb6743d4248842a8ce26069606b5652`
- artifact digest: `sha256:1b74c5cfc01a30864f09fb6e74ee499734132764df50e254f42f96a1679ab833`

### Exact final feature head

- branch: `fix/user-storage-load-integrity-v620-v628`
- exact SHA: `65a690512d43a1adc359390dcba7b21369a7c535`
- push Verify #303
- tests: 1528 passed / 0 failed
- artifact: `verification-65a690512d43a1adc359390dcba7b21369a7c535`
- artifact digest: `sha256:ad24a59147a26ebd56497b850610b4449215f1127e73a71f773567147c646cb4`

### PR synthetic merge-ref

- PR #256
- exact feature head: `65a690512d43a1adc359390dcba7b21369a7c535`
- synthetic merge SHA: `1cd14f9079589a228b03da68af294f027424ed47`
- pull_request Verify #304
- tests: 1528 passed / 0 failed
- artifact: `verification-1cd14f9079589a228b03da68af294f027424ed47`
- artifact digest: `sha256:7691263bc8e1afa823b1ba1f351d63026ad7b0fe08c5e70c0f82a76d26de3a54`

### Squash-main verification

- exact main SHA: `0f8ae846a06652743c698ec671ab586bbf1bb4bd`
- push Verify #305
- tests: 1528 passed / 0 failed
- artifact: `verification-0f8ae846a06652743c698ec671ab586bbf1bb4bd`
- artifact digest: `sha256:7f8297c257fdda77a4a5e26938a00dfd19978db59ce550efc6c17f40ee169aea`

## Verification semantics

- feature push, synthetic merge-ref, and squash-main evidence remain distinct;
- no evidence is transferred between SHAs;
- workflow/test-manifest evidence is not independent external verification;
- `externally_verified=False`.
