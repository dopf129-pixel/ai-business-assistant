from copy import deepcopy


def build_period_profit_response(
    summary,
    comparison=None,
    return_evidence=None,
    return_financial_evidence=None,
    advertising_financial_evidence=None,
    storage_financial_evidence=None,
    mapping_observability=None,
    return_cogs_recovery_evidence=None,
    external_expense_evidence=None,
    external_expense_adjustment=None,
):
    source = deepcopy(dict(summary or {}))
    if source.get("status") != "PERIOD_PROFIT_SUMMARY_READY" or source.get("error") is not False:
        return {"error": True, "code": "PERIOD_PROFIT_RESPONSE_SUMMARY_REQUIRED", "status": "PERIOD_PROFIT_RESPONSE_UNAVAILABLE"}

    revenue = float(source.get("revenue") or 0)
    external_expense_layer_active = (
        external_expense_evidence
        is not None
    )
    profit_label = (
        "Прибыль до внешних расходов"
        if external_expense_layer_active
        else "Прибыль"
    )
    margin_label = (
        "Маржа до внешних расходов"
        if external_expense_layer_active
        else "Маржа"
    )

    lines = [
        f"💰 Прибыль за период {source.get('date_from')} — {source.get('date_to')}",
        "",
        (
            "Выручка: "
            + _money_with_revenue_share(
                source.get("revenue"),
                revenue,
            )
        ),
        (
            "Начисления Ozon после комиссий/услуг: "
            + _money_with_revenue_share(
                source.get("net_accrual"),
                revenue,
            )
        ),
    ]

    if (
        source.get(
            "account_level_ozon_accruals_included"
        )
        is True
    ):
        reconciliation = float(
            source.get(
                "ozon_account_reconciliation"
            )
            or 0
        )
        if abs(reconciliation) >= 0.005:
            lines.extend([
                "",
                (
                    "Корректировка по итоговому "
                    "кабинету Ozon: "
                    + _money_with_revenue_share(
                        reconciliation,
                        revenue,
                    )
                ),
                (
                    "Это разница между итоговыми "
                    "начислениями кабинета и суммой "
                    "SKU-атрибутированных начислений."
                ),
            ])

    if source.get("fee_components_included") is True:
        lines.extend([
            "", "Расшифровка удержаний Ozon:",
            (
                "• Комиссия: "
                + _money_with_revenue_share(
                    source.get("commission"),
                    revenue,
                    absolute=True,
                )
            ),
            (
                "• Логистика: "
                + _money_with_revenue_share(
                    source.get("logistics"),
                    revenue,
                    absolute=True,
                )
            ),
            (
                "• Эквайринг: "
                + _money_with_revenue_share(
                    source.get("acquiring"),
                    revenue,
                    absolute=True,
                )
            ),
            (
                "• Прочие начисления/удержания: "
                + _money_with_revenue_share(
                    source.get("other_fees"),
                    revenue,
                    absolute=True,
                )
            ),
        ])

    lines.extend([
        "",
        (
            "Себестоимость: "
            + _money_with_revenue_share(
                source.get("product_cost"),
                revenue,
            )
        ),
        (
            "Налог: "
            + _money_with_revenue_share(
                source.get("tax"),
                revenue,
            )
        ),
        (
            profit_label + ": "
            + _money_with_revenue_share(
                source.get("profit"),
                revenue,
            )
        ),
        (
            margin_label
            + ": "
            + _percent(
                source.get("margin_percent")
            )
        ),
    ])

    _append_external_expense_evidence(
        lines,
        external_expense_evidence,
        external_expense_adjustment,
        revenue,
    )

    if (
        isinstance(return_evidence, dict)
        and return_evidence.get("status")
        in {
            "PERIOD_PROFIT_RETURN_EVIDENCE_READY",
            "PERIOD_PROFIT_RETURN_EVIDENCE_PARTIAL",
        }
    ):
        count = int(
            return_evidence.get(
                "return_record_count"
            )
            or 0
        )
        exact_marker = (
            return_evidence.get(
                "return_record_count_exact"
            )
        )
        if type(exact_marker) is bool:
            exact = exact_marker
        else:
            exact = (
                return_evidence.get("status")
                == "PERIOD_PROFIT_RETURN_EVIDENCE_READY"
            )

        if return_evidence.get("returns_observed") is True:
            if exact:
                lines.extend([
                    "",
                    (
                        "↩️ Ozon зафиксировал возвраты "
                        f"за период: {count}."
                    ),
                ])
            else:
                lines.extend([
                    "",
                    (
                        "↩️ Ozon вернул как минимум "
                        f"{count} записей о возвратах "
                        "за период."
                    ),
                    (
                        "Выборка возвратов неполная; "
                        "это не точное итоговое количество."
                    ),
                ])

            if (
                source.get(
                    "account_level_ozon_accruals_included"
                )
                is True
            ):
                lines.append(
                    "Денежные начисления и удержания Ozon "
                    "уровня кабинета уже входят в итоговые "
                    "начисления; отдельно проверяется "
                    "восстановление товарной себестоимости."
                )
            else:
                lines.append(
                    "Их денежное влияние пока не включено "
                    "в прибыль как отдельная корректировка."
                )
        elif exact:
            lines.extend([
                "",
                (
                    "↩️ Ozon не вернул записей о возвратах "
                    "за выбранный период."
                ),
            ])
            lines.append(
                "Это не доказывает отсутствие всех "
                "возвратных расходов."
            )
        else:
            lines.extend([
                "",
                (
                    "↩️ Выборка возвратов неполная; "
                    "точное количество недоступно."
                ),
            ])

    if isinstance(return_financial_evidence, dict) and return_financial_evidence.get("status") == "PERIOD_PROFIT_RETURN_FINANCIAL_EVIDENCE_READY" and return_financial_evidence.get("authorized_mapping_applied") is True:
        lines.extend([
            "", "Подтверждённые возвратные финансовые операции:",
            f"• Совпавших операций: {int(return_financial_evidence.get('matched_operation_count') or 0)}",
            f"• Сумма по mapping: {_money_abs(return_financial_evidence.get('matched_amount'))}",
        ])
        mapping_id = return_financial_evidence.get("authorized_mapping_id")
        if mapping_id:
            lines.append(f"• Mapping ID: {mapping_id}")
        lines.append("Эти операции уже входят в net_accrual и повторно из прибыли не вычитаются.")

    _append_return_cogs_recovery_evidence(
        lines,
        return_cogs_recovery_evidence,
        revenue,
    )

    _append_expense_evidence(lines, "📣 Подтверждённые операции рекламы", advertising_financial_evidence)
    _append_expense_evidence(lines, "🏬 Подтверждённые операции хранения", storage_financial_evidence)
    _append_mapping_observability_warning(lines, mapping_observability)

    if isinstance(comparison, dict) and comparison.get("status") == "PERIOD_PROFIT_COMPARISON_READY":
        direction = {"UP": "выросла", "DOWN": "снизилась", "UNCHANGED": "не изменилась"}.get(comparison.get("profit_direction"), "изменилась")
        delta = _money(abs(float(comparison.get("profit_change") or 0)))
        percent = comparison.get("profit_change_percent")
        suffix = f" ({abs(percent):.2f}%)" if percent is not None else ""
        lines.extend(["", f"К предыдущему сопоставимому периоду прибыль {direction} на {delta}{suffix}."])

    missing = []
    if source.get("returns_included") is not True:
        missing.append("возвраты")
    if source.get("advertising_included") is not True:
        missing.append("реклама")
    if source.get("storage_included") is not True:
        missing.append("хранение")
    if missing:
        if (
            source.get(
                "account_level_ozon_accruals_included"
            )
            is True
        ):
            lines.extend([
                "",
                (
                    "ℹ️ Все денежные начисления и "
                    "удержания Ozon уровня кабинета "
                    "уже входят в сумму "
                    "«Начисления Ozon»."
                ),
                (
                    "Пока не завершена отдельная "
                    "классификация по категориям: "
                    + ", ".join(missing)
                    + "."
                ),
                (
                    "Эти операции не вычитаются "
                    "повторно из прибыли."
                ),
                (
                    (
                        "Показатель учитывает Ozon-начисления, "
                        "себестоимость, настроенный налог и "
                        "подтверждённые внешние расходы за период, "
                        "но ещё не является полной бухгалтерской "
                        "чистой прибылью."
                    )
                    if (
                        isinstance(
                            external_expense_evidence,
                            dict,
                        )
                        and external_expense_evidence.get(
                            "coverage_complete"
                        )
                        is True
                    )
                    else (
                        "Показатель учитывает Ozon-начисления, "
                        "себестоимость и настроенный налог; "
                        "учёт внешних расходов ещё неполный, "
                        "поэтому это не бухгалтерская чистая прибыль."
                    )
                ),
            ])
        else:
            lines.extend([
                "",
                (
                    "⚠️ В текущую версию прибыли пока "
                    "не включены полностью: "
                    + ", ".join(missing)
                    + "."
                ),
            ])
            lines.append(
                "Это операционная оценка в указанном "
                "составе, а не бухгалтерская чистая прибыль."
            )

    return {"error": False, "status": "PERIOD_PROFIT_RESPONSE_READY", "text": "\n".join(lines), "profit_scope": source.get("profit_scope")}


def _append_external_expense_evidence(
    lines,
    evidence,
    adjustment,
    revenue,
):
    source = dict(evidence or {})
    derived = dict(adjustment or {})

    if source.get("error") is True:
        lines.extend([
            "",
            "🏢 Внешние расходы: —",
            (
                "Источник внешних расходов недоступен; "
                "они не считаются нулевыми."
            ),
        ])
        return

    if source.get("status") not in {
        "PERIOD_PROFIT_EXTERNAL_EXPENSE_EVIDENCE_READY",
        "PERIOD_PROFIT_EXTERNAL_EXPENSE_EVIDENCE_PARTIAL",
    }:
        return

    count = int(
        source.get("expense_count")
        or 0
    )
    total = float(
        source.get("observed_expense_total")
        or 0
    )
    complete = (
        source.get("coverage_complete")
        is True
    )

    lines.extend([
        "",
        (
            "🏢 Внешние расходы"
            + (
                ""
                if complete
                else " — внесённые"
            )
            + ": "
            + _money_with_revenue_share(
                total,
                revenue,
            )
        ),
        (
            "• Записей: "
            f"{count}"
        ),
    ])

    categories = source.get(
        "category_breakdown"
    )
    if isinstance(categories, dict):
        for category, amount in (
            categories.items()
        ):
            lines.append(
                "• "
                + str(category)
                + ": "
                + _money_with_revenue_share(
                    amount,
                    revenue,
                )
            )

    if complete:
        lines.append(
            "• Coverage расходов: полный "
            "за выбранный период."
        )
        adjusted_profit = derived.get(
            "complete_profit_after_external_expenses"
        )
        adjusted_margin = derived.get(
            "complete_margin_percent"
        )
        if (
            adjusted_profit is not None
            and adjusted_margin is not None
        ):
            lines.extend([
                (
                    "Прибыль после внешних расходов: "
                    + _money_with_revenue_share(
                        adjusted_profit,
                        revenue,
                    )
                ),
                (
                    "Маржа после внешних расходов: "
                    + _percent(
                        adjusted_margin
                    )
                ),
            ])
        return

    gaps = source.get(
        "coverage_gaps"
    )
    if isinstance(gaps, list) and gaps:
        rendered = []
        for gap in gaps[:3]:
            if not isinstance(gap, dict):
                continue
            start = gap.get("date_from")
            end = gap.get("date_to")
            if start and end:
                rendered.append(
                    (
                        str(start)
                        if start == end
                        else f"{start} — {end}"
                    )
                )
        if rendered:
            lines.append(
                "• Нет подтверждённого coverage: "
                + "; ".join(rendered)
                + (
                    "; …"
                    if len(gaps) > 3
                    else ""
                )
            )

    if count > 0:
        observed_profit = derived.get(
            "observed_profit_after_external_expenses"
        )
        observed_margin = derived.get(
            "observed_margin_percent"
        )
        if (
            observed_profit is not None
            and observed_margin is not None
        ):
            lines.extend([
                (
                    "Наблюдаемая прибыль после внесённых "
                    "внешних расходов: "
                    + _money_with_revenue_share(
                        observed_profit,
                        revenue,
                    )
                ),
                (
                    "Наблюдаемая маржа: "
                    + _percent(
                        observed_margin
                    )
                ),
            ])

    lines.append(
        "Учёт внешних расходов не покрывает весь "
        "период; отсутствующие записи не считаются нулём."
    )


def _append_return_cogs_recovery_evidence(
    lines,
    evidence,
    revenue,
):
    source = dict(evidence or {})
    if (
        source.get("status")
        != "PERIOD_PROFIT_RETURN_COGS_RECOVERY_EVIDENCE_READY"
        or source.get("error") is not False
    ):
        return

    candidate_units = int(
        source.get("candidate_recovery_units")
        or 0
    )
    candidate_value = float(
        source.get("candidate_value_at_current_cost")
        or 0
    )
    compensated_units = int(
        source.get("compensated_units")
        or 0
    )
    unresolved_units = int(
        source.get("unresolved_units")
        or 0
    )
    lineage_candidates = int(
        source.get(
            "sale_lineage_candidate_record_count"
        )
        or 0
    )
    lineage_matched = int(
        source.get(
            "sale_lineage_matched_candidate_record_count"
        )
        or 0
    )
    lineage_available = (
        source.get(
            "sale_lineage_evidence_available"
        )
        is True
    )
    sale_period_confirmed = (
        source.get(
            "originating_sale_period_confirmed"
        )
        is True
    )
    historical_candidates = int(
        source.get(
            "historical_cost_candidate_record_count"
        )
        or 0
    )
    historical_matched = int(
        source.get(
            "historical_cost_matched_candidate_record_count"
        )
        or 0
    )
    historical_cost_confirmed = (
        source.get(
            "historical_cost_basis_confirmed"
        )
        is True
    )
    historical_value = source.get(
        "candidate_value_at_historical_cost"
    )
    inventory_candidates = int(
        source.get(
            "inventory_recovery_candidate_record_count"
        )
        or 0
    )
    inventory_saleable = int(
        source.get(
            "inventory_recovery_saleable_candidate_record_count"
        )
        or 0
    )
    inventory_non_saleable = int(
        source.get(
            "inventory_recovery_non_saleable_candidate_record_count"
        )
        or 0
    )
    inventory_state_complete = (
        source.get(
            "inventory_recovery_state_complete"
        )
        is True
    )
    inventory_available = (
        source.get(
            "inventory_recovery_evidence_available"
        )
        is True
    )

    lines.extend([
        "",
        "📦 Возвратная себестоимость — evidence:",
        (
            "• Возвраты на return-place: "
            f"{candidate_units} шт."
        ),
        (
            "• Потенциальная стоимость по текущей "
            "себестоимости: "
            + _money_with_revenue_share(
                candidate_value,
                revenue,
            )
        ),
        (
            "• Возвраты с компенсацией Ozon: "
            f"{compensated_units} шт."
        ),
        (
            "• Неопределённый recovery-статус: "
            f"{unresolved_units} шт."
        ),
    ])

    if lineage_candidates > 0:
        if sale_period_confirmed:
            lines.append(
                "• Исходная продажа в выбранном периоде: "
                f"подтверждена для {lineage_matched}/"
                f"{lineage_candidates} return-records "
                "по posting_number + SKU."
            )
        elif lineage_available:
            lines.append(
                "• Исходная продажа в выбранном периоде: "
                f"подтверждена для {lineage_matched}/"
                f"{lineage_candidates} return-records; "
                "lineage остаётся неполным."
            )
        else:
            lines.append(
                "• Исходная продажа в выбранном периоде: "
                "evidence недоступен."
            )

    if historical_candidates > 0:
        if (
            historical_cost_confirmed
            and historical_value is not None
        ):
            lines.append(
                "• Историческая себестоимость исходных продаж: "
                f"подтверждена для {historical_matched}/"
                f"{historical_candidates} return-records; "
                + _money_with_revenue_share(
                    historical_value,
                    revenue,
                )
                + "."
            )
        elif historical_matched > 0:
            lines.append(
                "• Историческая себестоимость исходных продаж: "
                f"подтверждена для {historical_matched}/"
                f"{historical_candidates} return-records; "
                "evidence остаётся неполным."
            )
        else:
            lines.append(
                "• Историческая себестоимость исходных продаж: "
                "нет полного effective-dated evidence."
            )

    saleable_confirmed = (
        source.get(
            "saleable_inventory_recovery_confirmed"
        )
        is True
    )

    if inventory_candidates > 0:
        if saleable_confirmed:
            lines.append(
                "• Восстановление продаваемого остатка: "
                f"подтверждено для {inventory_saleable}/"
                f"{inventory_candidates} return-records."
            )
        elif inventory_state_complete:
            lines.append(
                "• Recovery-state возвратов: "
                f"продаваемый остаток {inventory_saleable}/"
                f"{inventory_candidates}, "
                f"непродаваемый {inventory_non_saleable}/"
                f"{inventory_candidates}; "
                "полное saleable recovery не подтверждено."
            )
        elif inventory_available:
            lines.append(
                "• Recovery-state возвратов: "
                "explicit evidence неполный; "
                "отсутствующие подтверждения не считаются "
                "восстановленным остатком."
            )
        else:
            lines.append(
                "• Recovery-state возвратов: "
                "explicit evidence недоступен."
            )

    blockers = []
    if not saleable_confirmed:
        blockers.append(
            "продаваемый/восстановленный остаток"
        )
    if not historical_cost_confirmed:
        blockers.append(
            "историческая себестоимость"
        )
    if not sale_period_confirmed:
        blockers.append(
            "принадлежность исходной продажи "
            "выбранному периоду"
        )

    if blockers:
        limitation = (
            "остаются неподтверждёнными: "
            + ", ".join(blockers)
            + "."
        )
    else:
        limitation = (
            "sale-lineage, историческая себестоимость "
            "и saleable recovery подтверждены, но ещё "
            "не доказаны период признания recovery, "
            "количество исходной продажи и "
            "compensation accounting."
        )

    lines.append(
        "Эта сумма не прибавляется к прибыли: "
        + limitation
    )

def _append_expense_evidence(lines, title, evidence):
    source = dict(evidence or {})
    if source.get("status") != "PERIOD_PROFIT_EXPENSE_EVIDENCE_READY" or source.get("authorized_mapping_applied") is not True:
        return
    lines.extend([
        "", title + ":",
        f"• Совпавших операций: {int(source.get('matched_operation_count') or 0)}",
        f"• Сумма по mapping: {_money_abs(source.get('matched_amount'))}",
    ])
    mapping_id = source.get("authorized_mapping_id")
    if mapping_id:
        lines.append(f"• Mapping ID: {mapping_id}")
    lines.append("Эти расходы уже находятся внутри net_accrual и повторно не вычитаются.")


def _append_mapping_observability_warning(lines, observability):
    source = dict(observability or {})
    if source.get("status") != "PERIOD_PROFIT_MAPPING_OBSERVABILITY_SNAPSHOT_READY":
        return
    if source.get("registry_health_status") == "CORRUPT" or source.get("load_allowed") is not True:
        lines.extend([
            "",
            "⚠️ Mapping registry недоступен или повреждён; evidence mappings работают в fail-closed режиме.",
        ])
        return
    stale = list(source.get("stale_scopes") or [])
    if stale:
        lines.extend([
            "",
            "⚠️ Активные mapping revisions не являются последними для: " + ", ".join(stale) + ".",
            "Это предупреждение о конфигурации; формула прибыли не изменяется.",
        ])


def _money_with_revenue_share(
    value,
    revenue,
    absolute=False,
):
    amount = float(value or 0)
    display_amount = (
        abs(amount)
        if absolute
        else amount
    )
    money = _money(display_amount)

    revenue_value = float(revenue or 0)
    if revenue_value <= 0:
        return money

    share_value = (
        abs(amount)
        if absolute
        else amount
    )
    share = (
        share_value
        / revenue_value
        * 100
    )

    return (
        money
        + f" ({share:.2f}%)"
    )


def _money(value):
    return f"{float(value or 0):,.2f} ₽".replace(",", " ")


def _money_abs(value):
    return _money(abs(float(value or 0)))


def _percent(value):
    return f"{float(value or 0):.2f}%"
