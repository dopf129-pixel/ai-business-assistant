# FIFO supply list filter fix — progress

## Status

- Current stage: FLF05 in progress; implementation and local verification complete, PR and exact-head CI pending.
- Branch: `codex/fifo-supply-list-filter-fix-20261117`.
- Base: `main` at `23d8a212fd25692b53a082071ef01b9babedff5f`.
- Owner data, `.env`, runtime database and Desktop working copy: untouched.
- Existing untracked `.fl12-deps/` in the prior worktree remains untouched and excluded.

## Evidence

The owner already ran one read-only `/v3/supply-order/list` call on 2026-11-17. Ozon returned HTTP 400 and identified `UNSPECIFIED` at filter state index 11 as a prohibited zero enum value. No new live requests are authorized or needed.

## Stage log

| Stage | Status | SHA | Results |
|---|---|---|---|
| FLF00 | Complete | `23d8a212fd25692b53a082071ef01b9babedff5f` base | Read `AGENTS.md`, `CURRENT_STATE.md`, `DECISIONS.md`, `TEST_MAP.md`, task and source contracts. Created isolated worktree/branch from the current main. Existing owner data and the prior worktree were preserved. |
| FLF01 | Complete | baseline red, then implementation green | In a disposable copy of baseline code, the new regressions failed in six cases: allowlist, both ordinary/durable scans on rejected filter, both 400 diagnostics, and direct wrapper rejection. After the fix, the focused synthetic profile passed **12 tests**. |
| FLF02 | Complete | local changes | Removed only `UNSPECIFIED` from the shared 11-state filter; direct wrapper rejects single/mixed occurrences before HTTP. Other values and order are unchanged. |
| FLF03 | Complete | local changes | Both list paths now retain the generic unavailable issue and prepend a fixed request-rejected issue only for exact `OZON_HTTP_ERROR` plus integer 400. Durable persistence and Telegram restore render the safe message. 429, timeout and string `"400"` do not receive it. |
| FLF04 | Complete | local changes | Related FIFO/list/cross-docking profile: **108 passed in 8.27s**. Full suite in disposable source copy without `.git`, `.env`, runtime/user data, or project `data/` (only synthetic 6% USN_INCOME policy): **5,469 passed in 111.21s**. `compileall -q app tests` passed with one pre-existing float-identity SyntaxWarning. `git diff --check` and `git diff --exit-code -- data` passed. |
| FLF05 | In progress | — | Changelog, current state, test map, source contract and this progress journal are updated. Preparing one PR; exact-SHA Windows/Linux CI and independent review handoff remain. `DECISIONS.md` unchanged because no architectural decision was introduced. |

## Verification notes

- No live Ozon/Telegram request, bot launch, merge, deployment, or update was performed.
- No schema, FIFO rule, quantity, event, layer, allocation, profit, or HTTP/time budget behavior was changed.
- Full-suite disposable copy: `C:\Users\GELASH~1\AppData\Local\Temp\fifo-filter-full-ba834d47f499496aa2b10c5bbce4f737`.
- A preliminary disposable-copy setup call named a nonexistent test path and ran no tests; the subsequent valid baseline and fixed-code profiles are the results recorded above.

## Resume

Continue with FLF05: review the final diff, commit the requested files, push this branch, open a PR to `main`, wait for exact-head Windows/Linux CI, and finish the independent-review packet. Keep FIFO/R1 readiness semantics unchanged and do not use owner files as test fixtures.
