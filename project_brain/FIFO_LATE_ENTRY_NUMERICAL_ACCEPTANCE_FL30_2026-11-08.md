# FIFO late-entry numerical acceptance — FL30

Date: 2026-11-08. Source: `FIFO_LATE_ENTRY_CASE_AND_ACCEPTANCE_2026-11-07.md`.
All identifiers and files used by this matrix are synthetic. Tests run with temporary SQLite and generated source fixtures; no owner downloads/database, live Ozon/Telegram request, or bot process was used.

## Independent arithmetic controls

- N04: `6234 + 600 + 148 = 6982`; this is an owner total and three different source states, not proof that all units are accepted or a FIFO opening.
- N14: `1182 + 9 = 1191`; FBS return is a subset of available stock, not a second addition to the same rows.
- N17: `4492 + 0 - 775 - 5 - 3712 = 0`; redeemed sales are 775; seller withdrawal is a separate 5-unit outflow.
- N21: old layer `3 × 21.00 = 63.00`; two new units `2 × 14.65 = 29.30`; five-unit COGS `92.30`; remaining new units `98`.
- N23: only two old units physically sold before the transition: `2 × 21.00 = 42.00`; a later rate change has zero effect on that period.
- N24: COGS `105.00 → 92.30`; with net accrual `500.00` and tax mode NONE, profit `395.00 → 407.70`, delta `+12.70`.
- N25: with FNS `1000.00` and USN income tax 6%, tax remains `60.00`; profit `335.00 → 347.70`, delta `+12.70`.
- N27: pre-cutoff legacy COGS `2 × 21.00 = 42.00` is separate from the opening queue. Post-cutoff COGS for `3 × 21.00 + 1 × 14.65` is `77.65`.
- N29: withdrawal consumes one old unit separately (`21.00`) and does not count as a sale. Three later sales cost `2 × 21.00 + 1 × 14.65 = 56.65`.

These values are independently calculated in tests with `Decimal`; assertions compare them with replay, impact, or repository outputs. They are synthetic controls, not estimates of the owner's actual inventory or profit.

## N01–N40 coverage map

| Case | Independently expected behavior | Executed regression coverage |
|---|---|---|
| N01 | Save 21.00→14.65 while FIFO is uninitialized; no FIFO layer or financial cost switch. | `test_telegram_fifo_cost_transition_runtime_service::test_transition_wizard_saves_confirmed_fields_and_resumes_after_runtime_restart`; `test_fifo_cost_period_profit_source_service::test_uninitialized_scope_stays_on_legacy_cost_mode`; atomic apply test. |
| N02 | Components `10+3+1.65` and TOTAL_LANDED `14.65` produce the same total with different provenance. | `test_telegram_fifo_cost_transition_runtime_service::test_components_mode_saves_exact_total_without_inventing_components`; components preview test. |
| N03 | TOTAL_LANDED keeps components null; it does not write fictitious zeroes or purchase cost. | Wizard restart test; `test_total_landed_history_and_csv_never_invent_component_breakdown`. |
| N04 | `6234+600+148=6982`; declarations persist, acceptance stays unknown until evidence. | `test_confirmed_supply_declarations_are_typed_and_report_import_is_case_bound`; `test_control_case_keeps_owner_linked_receiving_and_report_buckets_separate`. |
| N05 | Missing observation for 148 retains declaration and last known RECEIVING; accepted remains unknown, never zero. | `test_latest_missing_observation_preserves_last_known_receiving_without_zeroing`; `test_missing_refresh_appends_without_erasing_declaration_or_partial_receipt`. |
| N06 | Explicit, complete act quantity zero is confirmed zero; empty/missing acts remain unknown. | `test_explicit_zero_acceptance_is_not_confused_with_missing_act_evidence`; source-normalizer empty-act test. |
| N07 | Later PRESENT observation refreshes the same declaration; count remains 148 without duplicate receipt. | `test_later_present_observation_refreshes_same_declaration_without_duplicate_receipt`. |
| N08 | Cumulative 40→70→100 and stale duplicate 70 resolve to 100, not 210/280. | `test_cumulative_40_70_100_uses_latest_total_instead_of_summing`; stale-70 test. |
| N09 | Distinct acts 40+60 resolve to 100; repeating the same act/snapshot adds nothing. | `test_two_distinct_acceptance_acts_sum_but_duplicate_snapshots_do_not`; repeated-act test. |
| N10 | Final 98/100 is discrepancy 2; no automatic inventory write-off. | `test_final_accepted_shortage_is_discrepancy_and_requires_confirmed_movement`; transition supply reconciliation final-shortage test. |
| N11 | 100→90 correction preserves 100 history and requests review. | `test_downward_acceptance_correction_preserves_old_value_and_requires_review`. |
| N12 | Cross-SKU/store act identity is conflict; no first-row/name-based mapping. | Other-SKU acceptance conflict; wrong-scope report and foreign-tenant store tests. |
| N13 | Planned 600 and owner-shipped 6982 remain distinct provenance; planned is not silently moved back home. | `test_control_case_keeps_owner_linked_receiving_and_report_buckets_separate`; opening proposal must not add accepted supply twice. |
| N14 | Available stock is 1182+FBS subset 9 =1191, once. | `test_stock_import_preserves_fbs_return_and_independent_status_buckets`. |
| N15 | Parallel stock views remain separate snapshots; they are not summed. | `test_two_stock_reports_remain_two_snapshots_and_are_not_summed`; duplicate warehouse dimension test. |
| N16 | Preparing 18, checking 5, and removed 41 remain distinct buckets, not reserved/sales/available by guess. | Stock-management bucket and removed-row import tests. |
| N17 | Turnover control balances to zero; 775 sales and 5 withdrawals are distinct. | `test_turnover_import_normalizes_exact_sku_and_separates_sales_from_expenses`; opening proposal control-number test. |
| N18 | Closing 3712 with 1646 buyer deliveries cannot become 3712 physical sellable opening without bridge. | `test_cutoff_period_gap_is_explicit_and_buyer_delivery_is_separate`; cutoff bridge exact identity tests. |
| N19 | Evidence only through 05.11 cannot claim complete coverage through 07.11. | Incomplete finance page, coverage watermark, and readiness complete-through tests. |
| N20 | Dispatch/document-created date 05.11 is not a physical receipt or sale date. | Filename-date/cutoff rejection and bridge owner-date confirmation tests. |
| N21 | Mixed FIFO COGS for 5 sales is 92.30; remaining new finite units are 98. | `test_n21_decimal_total_is_exact_and_replay_order_is_stable`; `test_uninitialized_fifo_preview_is_read_only_and_atomic_cutover_applies_once`. |
| N22 | Known shipped 6982 does not invent purchase/home total or infinite availability. | `test_fl19_unknown_new_home_keeps_new_rate_without_creating_unbounded_stock`; cutoff proposal tests. |
| N23 | New rate does not reprice the two physically pre-transition old units; profit delta is zero. | `test_late_entry_before_old_layer_is_spent_has_zero_cogs_tax_and_profit_delta`. |
| N24 | NONE-tax profit moves 395.00→407.70 from COGS only. | New `test_late_entry_numeric_acceptance_five_units_uses_independent_decimal_oracle[ NONE ]`. |
| N25 | USN income tax remains 60.00; profit moves 335.00→347.70. | Same independent numeric test, USN_INCOME parameter. |
| N26 | USN income-minus-expenses tax is recalculated by canonical TaxService. | `test_late_entry_impact_applies_minimum_tax_and_expense_based_policy`; TaxService integration tests. |
| N27 | Two pre-cutoff units cost 42.00; opening keeps 3 old units and post-cutoff four-unit COGS is 77.65. | New `test_n27_pre_cutoff_sales_are_not_consumed_again_from_opening_fifo`; mixed-period integration tests. |
| N28 | Re-accrual of one physical sale does not create a second allocation/COGS. | `test_reaccrued_finance_sale_consumes_fifo_once_across_period_days`. |
| N29 | One old withdrawal is a 21.00 non-sale outflow; subsequent 3-sale COGS is 56.65. | New `test_n29_old_stock_withdrawal_is_not_a_sale_and_new_sale_uses_remaining_fifo`; non-sale COGS separation tests. |
| N30 | Return restores its original layer basis; later rate does not reprice it; Return COGS gate remains. | `test_fc18_exact_full_return_restores_original_multi_layer_basis`; return normalizer and impact authorization tests. |
| N31 | Unknown/unlinked return order blocks exact basis; no guessed provenance. | Return identity/order and incomplete-source tests; cutoff bridge unlinked-return test. |
| N32 | Double confirm/timeout commits one transition revision and returns idempotent result. | Atomic apply idempotency, case CAS, and restart tests. |
| N33 | Changed evidence/tax/FIFO between preview and confirm returns stale/conflict with no partial rows. | `test_new_stock_evidence_after_ready_preview_invalidates_confirmation_without_fifo_writes`; changed tax/return evidence test. |
| N34 | Injected failure at every write boundary fully rolls back and leaves case READY. | `test_commit_rolls_back_at_every_write_boundary`. |
| N35 | Wizard values survive restart; late report import remains bound to the same case/revision. | Wizard restart test; `test_confirmed_supply_declarations_are_typed_and_report_import_is_case_bound`. |
| N36 | Wrong owner/store/SKU callback and stale tickets cannot mutate another case; navigation preserves other workflows. | Cross-store callback test; case store/SKU isolation; FIFO ReturnInventory and external-expense navigation regressions. |
| N37 | A→B→A report order and all input permutations yield identical COGS and no ledger mutation. | `test_fc32_every_input_order_preserves_layer_totals_and_consumes_units_once`; Period Profit read-order and replay idempotence tests. |
| N38 | Saved plan before apply remains frozen; new plan uses current FIFO revisions. | `test_fc27_fifo_saved_plan_survives_restart_copy_new_revision_and_export`. |
| N39 | Backup/restore preserves FIFO history, encrypted references, plans, and does not duplicate movements. | `test_backup_restore_reopens_fifo_history_current_cost_export_and_plan`; transition backup/restore tests. |
| N40 | Synthetic “complete” flags without source proof cannot unlock factual profit/apply. | `test_fl18_readiness_accepts_only_current_case_revision_bridge_proof`; missing cutoff and source-provenance readiness tests. |

## FL30 execution results

- Code commit: `2dec7566` (`Persist FIFO transition acceptance act evidence`); documentation checkpoint commit follows.
- Linked `test_fifo_cost_*.py`, `test_telegram_fifo_cost_*.py`, and `test_period_profit*.py`: **1094 passed in 44.41s**.
- Focused acceptance/review/reconciliation profile: **39 passed in 2.04s**. The durable refresh test saves acceptance from a complete source result, reconstructs it after new service instances, distinguishes explicit zero from missing acts, and verifies no FIFO inventory write occurred.
- Numeric controls plus Telegram runtime E2E tests from the initial FL30 pass: **9 passed in 1.63s**. The E2E paths cover uninitialized FIFO wizard/restart, typed in-flight supply declarations plus report-import handoff, and total/component input preview.
- `python -m compileall -q app tests`, `git diff --check`: PASS.
- Tracked `data/` diff: none; six files were fingerprinted after checks (aggregate manifest SHA-256 `4e540517654f0ab646dd704b8fb4f0cd7fdce93132b866ff961eae26414f8e07`). No data file was written by the new tests or implementation.
- Synthetic temporary SQLite/generated workbooks only. No actual owner facts were applied and no real API/bot/merge/deployment was used.
