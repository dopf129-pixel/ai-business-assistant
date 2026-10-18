# Planning workspace H–O — independent review handoff

Status: **READY FOR INDEPENDENT ARCHITECTURE REVIEW — all four PR verification workflows passed.**

Execution task: `LUNA_PLANNING_WORKSPACE_TASK_2026-10-19.md`
Progress journal: `LUNA_PLANNING_WORKSPACE_PROGRESS_2026-10-19.md`
Review classification: **Architecture Review Required**.

## PR stack and exact revisions

| Order | Modules | Pull request | Base | Head | Verify run |
|---:|---|---|---|---|---|
| 1 | H — local process lifecycle | [#705](https://github.com/dopf129-pixel/ai-business-assistant/pull/705) | `main` `722f368526c278b701cbfd69f3dbb9a474d52386` | `050563b6e8766efa06e3b733fc69bc35e086899d` | [39175656753](https://github.com/dopf129-pixel/ai-business-assistant/actions/runs/39175656753) — **success**, 3,443 tests on Windows and Linux; Docker smoke passed. CI merge ref: `a2cfd6b673e68eb4ef068399e39974404db7666e` |
| 2 | I — tenant planning repository | [#706](https://github.com/dopf129-pixel/ai-business-assistant/pull/706) | `codex/planning-workspace-h` `050563b6e8766efa06e3b733fc69bc35e086899d` | `4e6b1bc1f2d05433537f7caf2fda450b33ccce65` | [39175669828](https://github.com/dopf129-pixel/ai-business-assistant/actions/runs/39175669828) — **success**, 3,454 tests on Windows and Linux; Docker smoke passed. CI merge ref: `902f475f886bfff1d740121b392a8f608ad4187d` |
| 3 | J–K — advertising cap and sales mix calculation | [#707](https://github.com/dopf129-pixel/ai-business-assistant/pull/707) | `codex/planning-workspace-i` `4e6b1bc1f2d05433537f7caf2fda450b33ccce65` | `b66ebc45686e276c76bfcb4173c92cade6100c9c` | [39175679778](https://github.com/dopf129-pixel/ai-business-assistant/actions/runs/39175679778) — **success**, 3,466 tests on Windows and Linux; Docker smoke passed. CI merge ref: `4c091f6c38017bb3a687e2b08ee6cf5fe6bf9289` |
| 4 | L–N + O integration/evidence | [#708](https://github.com/dopf129-pixel/ai-business-assistant/pull/708) | `codex/planning-workspace-jk` `b66ebc45686e276c76bfcb4173c92cade6100c9c` | `a5041e5d7355d593bae6dacbc20c1590930eed21` | [39175690904](https://github.com/dopf129-pixel/ai-business-assistant/actions/runs/39175690904) — **success**, 3,497 tests on Windows and Linux; Docker smoke passed. CI merge ref: `814895b4a09316d9715f586eaef6b315572c8afc` |

Merge order must follow this dependency chain. The top PR is intentionally not a standalone diff against `main`. No PR has been merged and no deployment has been performed.

## Completed scope

- H: token-scoped single-instance lock, readiness only after polling/update processing start, local foreground/background start, status, and authenticated graceful stop; no process-wide kill.
- I: additive versioned SQLite planning tables, owner/store isolation, idempotency, revision CAS, bounded history, and historical document service.
- J: bounded Decimal advertising-cap solver over the canonical unit calculator.
- K: explicit successful-sales quantities, rounded per-sale components, period expenses once, and one aggregate call to the existing tax service.
- L: exact-scope plan/fact projection and arithmetic revenue bridge; incompatible profit scope is explicitly unavailable.
- M: separate calculation/history/fact readiness and targeted edits with preview and revision CAS.
- N: historical revision comparison and saved-plan, advertising-cap, sales-mix, and comparison CSV/JSON through existing export/document boundaries.
- O00: connected user flows and local cross-module acceptance. O01 remains pending exact-head full CI; O02 independent review remains pending.

## Local verification

- Broad H–O Windows/Python 3.12 profile: **249 passed in 9.98s**.
- Documentation drift/manager tests: **3 passed**.
- `python -m compileall -q app tests`: passed.
- PowerShell AST parse for `start_bot.ps1`, `status_bot.ps1`, `stop_bot.ps1`: passed.
- `git diff --check`: passed.
- No real Telegram bot, Telegram/Ozon API, `.env`, seller credentials, or seller reports were used.

The earlier full local pytest attempt produced **3431 passed / 28 failed** due to 7 shared-storage expectation failures and 21 Windows temporary-directory ACL failures, and modified root `data/tasks.json` and `data/users.json`. Exact original copies were unavailable, so no restoration was attempted. The current data hashes are recorded in the progress journal. Neither file, their lock, nor scratch directories are included in the PR commits. Do not rerun the full suite in this workspace; use the complete current GitHub verification jobs instead. No tests were deleted or disabled.

## Architecture and compatibility notes

- The planning schema is additive in the existing tenant SQLite database; no destructive migration or production data migration is included.
- Hypothetical planning documents remain separate from confirmed seller accounting/cost/tax facts. Historical plan reads and comparisons do not query Ozon.
- Existing canonical calculator and `TaxService` remain the calculation authorities; aggregate sales mix does not sum per-SKU taxes.
- Runtime callbacks and writes are scoped to authenticated owner/store and expected revision. Expired, stale, incompatible, partial, and future-schema states fail closed.
- User report exports may contain the current owner's figures and are authorization-scoped separately from strict anonymized support diagnostics.
- Existing main-menu flows remain available; process stop is cooperative and never kills an arbitrary PID.

## Independent review checklist

1. Verify SQLite additive migration, tenant identity, allowlist validation, CAS/idempotency, archive/restore/delete boundaries, and future-schema behavior.
2. Inspect callback tickets, stale-edit races, owner/store switches, reset/expiry, and revision conflict behavior.
3. Confirm saved planning data cannot enter financial fact, seller-cost, expense, or tax-setting stores.
4. Recheck Decimal bounds/rounding, monotonicity/evaluation budget, unknown-vs-zero quantity, fixed expenses once, and aggregate `TaxService` invocation.
5. Validate exact period/SKU/tax/calculation-version gates for fact and revision comparison; ensure incompatible derived deltas remain suppressed.
6. Confirm historical operations use snapshots and do not repeat Ozon calls; inspect source-operation budgets and expiry behavior.
7. Review export full-scope semantics, null/reason representation, Unicode/escaping/formula protection, size limits, delivery failure, and separation from diagnostic allowlists.
8. Verify process-lock ownership/readiness/loopback authentication and that stop cannot signal or kill an unrelated process.
9. Confirm every PR's exact-head Verify run passes Windows, Linux/full test suite, compile, and production Docker smoke before review completion.

## Final verification gate

- All four code-head PR Verify workflows completed with `success`; each includes Windows and Linux full-suite jobs, compile checks and the full-verification Docker build/runtime smoke. PR workflows test the GitHub merge ref for the declared stacked base plus the PR head; merge refs and exact head SHAs are listed above.
- This handoff and final progress record are documentation-only additions to PR #708. Before closing O01, confirm the **latest Verify run on PR #708** succeeded for the current head; the PR's latest run is authoritative if later documentation-only commits advance that head.
- Independent architecture review has not yet been performed. CI success is not a review approval and does not authorize merge.
