# W35 — сквозная числовая приёмка маршрутов и потребителей

Дата: 29.10.2026
Статус: DONE (engineering acceptance; owner/live validation remains pending).

## Область

W35 не меняет расчётные формулы. Добавлены assertions на существующие public-route и persisted-history сценарии, а также четыре требуемые регрессии: восстановление неполного источника, финансовая корректировка после результата, несколько единиц в одном отправлении и атомарный откат незавершённой фазы.

Финальные числа получены в synthetic временном хранилище через проектный `.venv`; `PYTHON_DOTENV_DISABLED=1`, `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`, локальная IANA timezone database передана через `PYTHONTZPATH`. Реальные Ozon/Telegram API, бот, ключи и данные владельца не использовались.

## Новые сквозные регрессии

| Сценарий | Фактическое утверждение |
|---|---|
| Public Telegram observation: incomplete → available | Первый сбор остаётся `INSUFFICIENT_DATA`, прибыль не рассчитывается. Повторный сбор с полным Returns даёт 4 успешные единицы, CPC 100.00 ₽ / 4 = 25.00 ₽ на единицу и модельную прибыль 36.00 ₽ при цене 100 ₽. Сохранённая альтернативная цена 95 ₽ с замороженным тарифом 12% даёт 33.60 ₽/шт. Результаты помечены как модельные, а не как фактическая прибыль. |
| Неполный Returns → полный источник в экспериментальной фазе | Первая ревизия остаётся `INSUFFICIENT_DATA`, denominator неизвестен. После полного обновления: 35 единиц выборки, 30 доставленных/успешных, 4 возврата и статус фазы `READY`. Созданы collection/result revisions 2 и 4; прежняя коллекция и результат сохранены без перезаписи. |
| Финансовая корректировка после результата и до решения | Revision 1: baseline 10.00, candidate 11.50, delta +1.50 ₽/шт. Revision 2: baseline 10.00, candidate 9.00, delta −1.00 ₽/шт. Обе записи читаются неизменными; owner decision по revision 1 отклоняется как stale. |
| Несколько единиц в одном отправлении | Одна строка posting содержит 3 товара: `posting_count=1`, `total_units=3`, `delivered_units=3`. Return event для 2 единиц даёт `customer_return_units=2`, не превращая число строк в число единиц. |
| Ошибка при частичном commit фазы | При синтетическом сбое вставки результата collection и result отсутствуют; result revision остаётся 0, phase state revision и журналы ревизий совпадают с состоянием до операции. |

Тесты: `test_public_flow_incomplete_buyout_then_modelled_rate_and_comparison` в `tests/test_unit_price_profit_per_unit_end_to_end.py`; `test_incomplete_return_collection_recovers_to_ready_without_rewriting_history` в `tests/test_unit_economics_experiment_phase_readiness_service.py`; `test_decision_requires_latest_candidate_result_and_valid_selection` в `tests/test_unit_economics_experiment_owner_decision_repository.py`; `test_one_posting_and_return_event_keep_multi_unit_quantities` в `tests/test_returns_buyout_facts_source.py`; `test_snapshot_and_result_rollback_together_when_result_insert_fails` в `tests/test_unit_economics_experiment_phase_collection_service.py`.

## N01–N18: проверка oracle и consumer parity

| Oracle | Числовой/поведенческий evidence |
|---|---|
| N01 | `test_n01_applies_additional_window_expense_before_tax_exactly_once`: 100 − 20 − 10 − 7 − 12 − 5 = 46.00 ₽; Performance CPC не добавляется второй раз. |
| N02 | `test_n02_exact_return_nonbuyout_cogs_and_nonoverlapping_compensation_reconcile_once`: потери возвратной когорты 350.00/100 = 3.50 ₽/шт.; storage 150.00/100 = 1.50 ₽/шт.; всего 5.00 ₽/шт. |
| N03 | `test_multi_service_operation_and_exact_duplicate_are_counted_once_without_raw_ids` и `test_changed_duplicate_is_conflict_and_disputed_amount_is_not_exposed`: −30, −20 и −10 дают расход 60.00 ₽; точный повтор не меняет итог, изменённый повтор — conflict. |
| N04 | `test_related_correction_preserves_signed_credit_and_normalizes_net_expense`: −300 + 50 = −250 ₽; связанный кредит не переписывается в отрицательную recurring rate. |
| N05 | `test_n05_absolute_advertising_over_price_is_applied_as_fixed_successful_unit_cost`: абсолютная реклама 120 ₽/шт. допустима при цене 100 ₽ и даёт прибыль −62.00 ₽; отсутствующий расход отличим от подтверждённого нуля. |
| N06 | `test_saleable_restored_inventory_does_not_create_a_cogs_loss`, `test_pending_inventory_disposition_is_not_zero_cogs`, `test_n02_strict_return_loss_from_resolver_enters_canonical_profit_once`: восстановленный товар не списывает COGS, неизвестный статус не превращается в ноль, подтверждённая потеря входит один раз. |
| N07 | `test_n07_exact_sku_paid_storage_is_exposed_as_numerator_without_guessing_denominator`: три начисления −0.58 ₽ дают SKU numerator 1.74 ₽, но без подтверждённого denominator сумма не выдается за ₽/шт.; отдельные tests блокируют overlap и account-level allocation. |
| N08 | `test_weighted_rate_uses_total_numerator_over_total_units`: 100+100 ₽ / 10+100 ед. = 200/110 = 1.82 ₽/шт. после округления, не среднее 5.50 ₽; нулевой denominator оставляет ставку неизвестной, неполные страницы не считаются полным окном. |
| N09 | `test_n09_extended_profit_is_taxed_on_existing_usn_income_base_without_discount_points`: налог 6.00 ₽ и прибыль 40.00 ₽; при points 20 ₽ налог 4.80 ₽ и прибыль 41.20 ₽. |
| N10 | `test_n10_extended_profit_uses_regular_tax_once_without_subtracting_expense_after_tax`: gross profit 46.00 ₽, налог 6.90 ₽, итог 39.10 ₽; минимум налога проверен отдельной веткой. |
| N11 | `test_compatible_mature_phases_compare_observed_net_without_double_subtracting_fees` и public route выше проверяют прямую модельную прибыль/дельту; цена и комиссия повторно сопоставляются с конкретной сохранённой тарифной точкой. |
| N12 | `test_child_collection_uses_remaining_parent_request_budget_and_downgrades_status`, shared-time-budget tests, batch and observation budget tests: дочерние источники не сбрасывают общий бюджет; исчерпание сохраняет partial/unknown. |
| N13 | `tests/test_unit_price_target_planning_service.py`: solver проверяет canonical forward и предыдущий цент, разделяет тарифные интервалы и unknown gaps, ограничивает число оценок; exhaust/gap не выдаются за глобальный оптимум. |
| N14 | `test_experiment_phase_result_replay_cas_and_append_only_history`, `test_experiment_freezes_exact_tariff_and_observation_revisions` и snapshot export tests: сохранённые ревизии и cost/tariff refs не переписываются, projections/export используют тот же frozen scope. |
| N15 | Repository/runtime tests проверяют same/other store, idempotent callback, changed-payload conflict, transaction rollback, quota failure и privacy allowlists; W35 добавил сравнение точных старой и новой сумм в append-only history. |
| N16 | `test_q0_and_below_sample_gate_never_create_a_per_unit_profit`, `test_partial_cpc_is_unknown_not_zero_and_does_not_mark_phase_ready`, phase comparison tests: недостаточный denominator/coverage и несовместимые окна блокируют числовой ranking. |
| N17 | Phase confirmation/timezone tests и `test_late_source_response_after_pause_is_rejected_without_persisting_snapshot`: окно начинается с полного локального дня, незавершённое окно и поздний ответ не записываются. |
| N18 | `test_threshold_uses_rounded_rub_per_unit_and_reports_no_clear_difference`, `test_nonpositive_baseline_never_gets_relative_improvement_percent`, changed-control/cost tests: tie не получает победителя, проценты нет при неположительной базе, смена условий блокирует сравнение. |

## Исправление тестового ожидания

Первый широкий W35 профиль дал 600 passed и 2 failed: старые assertions в `tests/test_planning_workspace_repository.py` ожидали database schema 10, хотя текущая additive migration в `PlanningWorkspaceRepository` уже имеет версию 12. Код миграции не менялся. Два теста обновлены на сравнение с `repo.DATABASE_SCHEMA_VERSION`; их отдельный повтор дал **2 passed**.

## Проверки

Связанный W35 regression профиль (47 файлов: canonical scenario, returns/expense evidence, tariff/target/sensitivity/batch, current consumers, experiments, repository/migrations, Telegram public routes и exports):

```text
667 passed in 16.53s
```

Изоляция: новый synthetic storage root; секреты/`.env` отключены; только локальная timezone database. Первый профиль до правки ожиданий: `600 passed, 2 failed`; финальный повтор — зелёный. Реальных Ozon-запросов и запуска Telegram-бота не было.

Дополнительный targeted W35 профиль новых regression файлов: `41 passed in 2.64s`. В начале тестирования один из новых rollback assertions был поставлен на соседний cancel test и обнаружил неподдерживаемое поле; он перемещён в транзакционный rollback test. Это не изменение производственного поведения.

`git diff --check` и `git diff -- data` проверяются перед завершением W35. PR CI/full pytest относятся к W38–W39 и пока не заявляются.

## Ограничения и следующий этап

W35 подтверждает реализацию и числовую согласованность тестируемых маршрутов. Это не закрывает W31 production first-run acquisition полного 56-дневного reference snapshot и отсутствующий Telegram шаг управления candidate-фазой; реальная приёмка владельцем остаётся pending. Дальше — W36: конкурентность, квоты, приватность, общие бюджеты запросов и ограниченный soak.
