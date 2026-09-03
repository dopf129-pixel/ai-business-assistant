from copy import deepcopy


def build_period_profit_response(
    summary,
    comparison=None,
    return_evidence=None,
    return_financial_evidence=None,
    advertising_financial_evidence=None,
    storage_financial_evidence=None,
    mapping_observability=None,
):
    source = deepcopy(dict(summary or {}))
    if source.get("status") != "PERIOD_PROFIT_SUMMARY_READY" or source.get("error") is not False:
        return {"error": True, "code": "PERIOD_PROFIT_RESPONSE_SUMMARY_REQUIRED", "status": "PERIOD_PROFIT_RESPONSE_UNAVAILABLE"}

    lines = [
        f"💰 Прибыль за период {source.get('date_from')} — {source.get('date_to')}",
        "",
        f"Выручка: {_money(source.get('revenue'))}",
        f"Начисления Ozon после комиссий/услуг: {_money(source.get('net_accrual'))}",
    ]

    if source.get("fee_components_included") is True:
        lines.extend([
            "", "Расшифровка удержаний Ozon:",
            f"• Комиссия: {_money_abs(source.get('commission'))}",
            f"• Логистика: {_money_abs(source.get('logistics'))}",
            f"• Эквайринг: {_money_abs(source.get('acquiring'))}",
            f"• Прочие начисления/удержания: {_money_abs(source.get('other_fees'))}",
        ])

    lines.extend([
        "",
        f"Себестоимость: {_money(source.get('product_cost'))}",
        f"Налог: {_money(source.get('tax'))}",
        f"Прибыль: {_money(source.get('profit'))}",
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
        lines.extend(["", "⚠️ В текущую версию прибыли пока не включены полностью: " + ", ".join(missing) + "."])
        lines.append("Это операционная оценка в указанном составе, а не бухгалтерская чистая прибыль.")

    return {"error": False, "status": "PERIOD_PROFIT_RESPONSE_READY", "text": "\n".join(lines), "profit_scope": source.get("profit_scope")}


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


def _money(value):
    return f"{float(value or 0):,.2f} ₽".replace(",", " ")


def _money_abs(value):
    return _money(abs(float(value or 0)))


def _percent(value):
    return f"{float(value or 0):.2f}%"
