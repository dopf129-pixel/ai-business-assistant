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
):
    source = deepcopy(dict(summary or {}))
    if source.get("status") != "PERIOD_PROFIT_SUMMARY_READY" or source.get("error") is not False:
        return {"error": True, "code": "PERIOD_PROFIT_RESPONSE_SUMMARY_REQUIRED", "status": "PERIOD_PROFIT_RESPONSE_UNAVAILABLE"}

    revenue = float(source.get("revenue") or 0)

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
            "Прибыль: "
            + _money_with_revenue_share(
                source.get("profit"),
                revenue,
            )
        ),
        f"Маржа: {_percent(source.get('margin_percent'))}",
    ])

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
                    "Показатель учитывает Ozon-начисления, "
                    "себестоимость и настроенный налог, "
                    "но ещё не является полной "
                    "бухгалтерской чистой прибылью "
                    "вне контура Ozon."
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
        (
            "Эта сумма не прибавляется к прибыли: "
            "не подтверждены продаваемый остаток, "
            "историческая себестоимость и принадлежность "
            "исходной продажи выбранному периоду."
        ),
    ])


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
