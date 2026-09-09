from copy import deepcopy
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from math import isfinite

from services.period_profit_return_cogs_blocker_stage_service import (
    PeriodProfitReturnCogsBlockerStageService,
)


def compact_period_profit_result(result):
    """Return a compact Telegram presentation without changing financial facts."""
    if not isinstance(result, dict):
        return result
    if result.get("error") is not False:
        return result
    if result.get("status") != "PERIOD_PROFIT_QUERY_READY":
        return result

    summary = result.get("summary")
    if not isinstance(summary, dict):
        return result

    required = (
        "date_from",
        "date_to",
        "revenue",
        "net_accrual",
        "product_cost",
        "tax",
        "profit",
        "margin_percent",
    )
    if any(summary.get(field) is None for field in required):
        return result

    output = deepcopy(result)
    original_text = output.get("text")
    if isinstance(original_text, str) and original_text.strip():
        output["details_text"] = original_text

    displayed_profit = summary.get("profit")
    displayed_margin = summary.get("margin_percent")
    external_line = None
    external_evidence = output.get("external_expense_evidence")
    external_adjustment = output.get("external_expense_adjustment")

    if (
        isinstance(external_evidence, dict)
        and external_evidence.get("coverage_complete") is True
        and isinstance(external_adjustment, dict)
        and external_adjustment.get("profit_adjustment_complete") is True
        and external_adjustment.get("complete_profit_after_external_expenses") is not None
        and external_adjustment.get("complete_margin_percent") is not None
    ):
        displayed_profit = external_adjustment.get(
            "complete_profit_after_external_expenses"
        )
        displayed_margin = external_adjustment.get(
            "complete_margin_percent"
        )
        external_total = external_evidence.get("observed_expense_total")
        if _finite_number(external_total) is not None:
            external_line = "Внешние расходы: " + _money(external_total)

    lines = [
        "💰 Прибыль за период "
        + _period(summary.get("date_from"), summary.get("date_to")),
        "",
        "Выручка: " + _money(summary.get("revenue")),
        "Продано SKU: " + _units(summary.get("units_sold")),
        "Начисления Ozon: " + _money(summary.get("net_accrual")),
        "Себестоимость: " + _money(summary.get("product_cost")),
        "Налог: " + _money(summary.get("tax")),
    ]

    if external_line is not None:
        lines.append(external_line)

    lines.extend([
        "",
        "Прибыль: " + _money(displayed_profit),
        "Маржа: " + _percent(displayed_margin),
    ])

    comparison_line = _comparison_line(output.get("comparison"))
    if comparison_line is not None:
        lines.extend(["", comparison_line])

    warnings = _warnings(output)
    if warnings:
        lines.append("")
        lines.extend(warnings)

    output["text"] = "\n".join(lines)
    output["presentation"] = "compact"
    output["read_only"] = True
    output["executed"] = False
    return output


def _warnings(result):
    warnings = []
    external = result.get("external_expense_evidence")
    if isinstance(external, dict):
        if external.get("error") is True:
            warnings.append("⚠️ Внешние расходы недоступны и не считаются нулём.")
        elif (
            external.get("status")
            in {
                "PERIOD_PROFIT_EXTERNAL_EXPENSE_EVIDENCE_READY",
                "PERIOD_PROFIT_EXTERNAL_EXPENSE_EVIDENCE_PARTIAL",
            }
            and external.get("coverage_complete") is not True
        ):
            warnings.append("⚠️ Внешние расходы учтены не полностью.")

    return_cogs = result.get("return_cogs_recovery_evidence")
    if isinstance(return_cogs, dict):
        unresolved = _unconfirmed_return_cogs_units(return_cogs)
        if unresolved:
            warnings.append(
                "Есть "
                + str(unresolved)
                + " возврата Returns API со сменой статуса в периоде; "
                "восстановление себестоимости не подтверждено. "
                "Это не число финансовых «Возврат выручки»."
            )

        diagnostic = _return_cogs_diagnostic(return_cogs)
        if diagnostic is not None:
            warnings.append(diagnostic)

    return warnings


def _return_cogs_diagnostic(evidence):
    """Render the single first blocker resolved by the canonical read-only stage service."""
    stage_result = PeriodProfitReturnCogsBlockerStageService.resolve(evidence)
    if not isinstance(stage_result, dict):
        return "🔒 Return COGS пока не применён: стадия доказательств недоступна."
    if stage_result.get("error") is True:
        return (
            "🔒 Return COGS пока не применён: цепочка доказательств невалидна. "
            "Текущий ответ остаётся read-only."
        )

    stage = stage_result.get("stage")
    if stage == PeriodProfitReturnCogsBlockerStageService.NONE:
        return None

    if stage == PeriodProfitReturnCogsBlockerStageService.INVENTORY:
        pending_inventory = [
            row for row in stage_result.get("records", []) if isinstance(row, dict)
        ]
        if not pending_inventory:
            return (
                "↩️ Нужен локальный факт о состоянии возврата. "
                "Статус Ozon сам по себе не доказывает SALEABLE_RESTORED."
            )
        pending_inventory.sort(key=lambda row: _return_identity_key(row) or ("", "", ""))
        shown = pending_inventory[:3]
        identities = "; ".join(_return_identity(row) for row in shown)
        extra = len(pending_inventory) - len(shown)
        suffix = f"; ещё {extra}" if extra > 0 else ""
        return (
            "↩️ Нужен локальный факт о состоянии возврата: "
            + identities
            + suffix
            + ". Подтвердите точную идентичность и состояние через «Состояние возврата». "
            "Статус Ozon сам по себе не доказывает SALEABLE_RESTORED."
        )

    if stage == PeriodProfitReturnCogsBlockerStageService.ACCOUNTING_ATTRIBUTION:
        exact = _accounting_attribution_diagnostic(evidence)
        if exact is not None:
            return exact
        return (
            "🧾 Return COGS пока не применён: бухгалтерская атрибуция периода, "
            "canonical READY status и отсутствие двойного учёта компенсации не подтверждены."
        )

    if stage == PeriodProfitReturnCogsBlockerStageService.ACCOUNTING_RECOGNITION:
        exact = _accounting_recognition_diagnostic(evidence)
        if exact is not None:
            return exact
        return (
            "🧾 Return COGS пока не применён: требуется отдельное бухгалтерское "
            "признание подтверждённой суммы с canonical READY status."
        )

    if stage == PeriodProfitReturnCogsBlockerStageService.APPLICATION_AUTHORIZATION:
        exact = _application_authorization_diagnostic(evidence)
        if exact is not None:
            return exact
        return (
            "🔒 Return COGS пока не применён: отдельная авторизация применения "
            "к прибыли с canonical READY status не подтверждена."
        )

    if stage == PeriodProfitReturnCogsBlockerStageService.APPLICATION_COMMIT:
        exact = _application_commit_diagnostic(evidence)
        if exact is not None:
            return exact
        if evidence.get("return_cogs_profit_application_commit_ready") is True:
            return (
                "🔒 Return COGS доказан до стадии commit, но exact-once commit ещё "
                "не подтверждён canonical committed status. Текущий ответ остаётся read-only."
            )
        return "🔒 Return COGS пока не применён: exact-once commit не подтверждён."

    if stage == PeriodProfitReturnCogsBlockerStageService.FINAL_APPLICATION:
        return (
            "🔒 Return COGS имеет подтверждённый exact-once commit, но ещё не отражён "
            "в seller-facing прибыли. Это отдельный final-application blocker и не "
            "разрешение повторять commit."
        )

    return "🔒 Return COGS пока не применён: неизвестная стадия доказательств."


def _accounting_attribution_diagnostic(evidence):
    accounting_records = evidence.get("accounting_attribution_evidence_records")
    candidates = evidence.get("candidate_records")
    if not isinstance(accounting_records, list) or not accounting_records:
        return None
    if not isinstance(candidates, list):
        candidates = []

    candidate_index = {}
    for row in candidates:
        identity = _return_identity_key(row)
        if identity is not None and identity not in candidate_index:
            candidate_index[identity] = row

    blocked = []
    for row in accounting_records:
        if not isinstance(row, dict):
            continue
        identity = _return_identity_key(row)
        candidate = candidate_index.get(identity, row)
        reason = _accounting_attribution_reason(row)
        if reason is None:
            continue
        blocked.append((identity or ("", "", ""), candidate, reason))

    if not blocked:
        return None

    blocked.sort(key=lambda item: item[0])
    shown = blocked[:3]
    details = "; ".join(
        _return_identity(candidate) + " — " + reason
        for _, candidate, reason in shown
    )
    extra = len(blocked) - len(shown)
    suffix = f"; ещё {extra}" if extra > 0 else ""
    return (
        "🧾 Return COGS пока не применён. Точные бухгалтерские блокеры: "
        + details
        + suffix
        + ". Эти факты не заполняются автоматически и не считаются нулём при отсутствии данных."
    )


def _accounting_attribution_reason(row):
    status = str(row.get("status") or "").strip().upper()
    if status == "RETURN_COGS_ACCOUNTING_ATTRIBUTION_MISSING":
        return "нет бухгалтерской атрибуции периода"
    if status == "RETURN_COGS_ACCOUNTING_ATTRIBUTION_IDENTITY_CONFLICT":
        return "конфликт точной идентичности бухгалтерского свидетельства"
    if status != "RETURN_COGS_ACCOUNTING_ATTRIBUTION_READY":
        return "бухгалтерское свидетельство недоступно или невалидно"
    if row.get("recovery_accounting_period_matches_request") is not True:
        return "дата бухгалтерского восстановления не подтверждена в выбранном периоде"
    compensation_state = str(row.get("compensation_state") or "").strip().upper()
    if compensation_state not in {
        "NO_COMPENSATION_CONFIRMED",
        "COMPENSATION_PRESENT",
    }:
        return "бухгалтерский режим компенсации не подтверждён"
    if row.get("compensation_double_count_clear") is not True:
        return "отсутствие двойного учёта компенсации не подтверждено"
    return None


def _accounting_recognition_diagnostic(evidence):
    candidates = evidence.get("candidate_records")
    recognition_records = evidence.get("return_cogs_accounting_recognition_evidence_records")
    amount_records = evidence.get("return_cogs_recovery_amount_evidence_records")
    attribution_records = evidence.get("accounting_attribution_evidence_records")
    if not isinstance(candidates, list) or not candidates:
        return None
    if not isinstance(recognition_records, list):
        recognition_records = []
    if not isinstance(amount_records, list):
        amount_records = []
    if not isinstance(attribution_records, list):
        attribution_records = []

    recognition_index = _identity_index(recognition_records)
    amount_index = _identity_index(amount_records)
    attribution_index = _identity_index(attribution_records)
    blocked = []

    for candidate in candidates:
        identity = _return_identity_key(candidate)
        if identity is None:
            continue
        record = recognition_index.get(identity)
        reason = _accounting_recognition_reason(
            record,
            amount_index.get(identity),
            attribution_index.get(identity),
        )
        if reason is not None:
            blocked.append((identity, candidate, reason))

    if not blocked:
        return None

    blocked.sort(key=lambda item: item[0])
    shown = blocked[:3]
    details = "; ".join(
        _return_identity(candidate) + " — " + reason
        for _, candidate, reason in shown
    )
    extra = len(blocked) - len(shown)
    suffix = f"; ещё {extra}" if extra > 0 else ""
    return (
        "🧾 Return COGS пока не применён. Точные блокеры бухгалтерского признания: "
        + details
        + suffix
        + ". Признание не создаётся автоматически и не подменяется расчётной суммой."
    )


def _accounting_recognition_reason(record, amount_record, attribution_record):
    if not isinstance(record, dict):
        return "нет отдельного бухгалтерского признания"
    if record.get("error") is True:
        return "свидетельство бухгалтерского признания недоступно"
    if record.get("error") is not False:
        return "свидетельство бухгалтерского признания невалидно"
    if str(record.get("status") or "").strip().upper() != "RETURN_COGS_ACCOUNTING_RECOGNITION_READY":
        return "бухгалтерское признание не готово"
    if record.get("accounting_recognition_confirmed") is not True:
        return "явное подтверждение бухгалтерского признания отсутствует"
    if str(record.get("recognition_state") or "").strip().upper() != "COGS_RECOVERY_RECOGNIZED":
        return "состояние COGS_RECOVERY_RECOGNIZED не подтверждено"

    recognized_amount = _money_number(record.get("recognized_amount"))
    expected_amount = None
    if isinstance(amount_record, dict):
        expected_amount = _money_number(amount_record.get("staged_recovery_amount"))
    if recognized_amount is None:
        return "признанная сумма отсутствует или невалидна"
    if expected_amount is None:
        return "ожидаемая сумма восстановления не подтверждена"
    if abs(recognized_amount - expected_amount) > 0.01:
        return "признанная сумма не совпадает с подтверждённой суммой восстановления"
    if str(record.get("currency") or "").strip().upper() != "RUB":
        return "валюта бухгалтерского признания не подтверждена как RUB"

    recognized_date = str(record.get("recovery_accounting_date") or "").strip()
    expected_date = ""
    if isinstance(attribution_record, dict):
        expected_date = str(attribution_record.get("recovery_accounting_date") or "").strip()
    if not recognized_date:
        return "дата бухгалтерского признания отсутствует"
    if not expected_date:
        return "дата бухгалтерской атрибуции не подтверждена"
    if recognized_date != expected_date:
        return "дата бухгалтерского признания не совпадает с атрибуцией периода"
    return None


def _application_authorization_diagnostic(evidence):
    candidates = evidence.get("candidate_records")
    authorization_records = evidence.get("return_cogs_profit_application_authorization_records")
    recognition_records = evidence.get("return_cogs_accounting_recognition_evidence_records")
    if not isinstance(candidates, list) or not candidates:
        return None
    if not isinstance(authorization_records, list):
        authorization_records = []
    if not isinstance(recognition_records, list):
        recognition_records = []

    authorization_index = _identity_index(authorization_records)
    recognition_index = _identity_index(recognition_records)
    blocked = []
    for candidate in candidates:
        identity = _return_identity_key(candidate)
        if identity is None:
            continue
        reason = _application_authorization_reason(
            authorization_index.get(identity),
            recognition_index.get(identity),
            identity,
        )
        if reason is not None:
            blocked.append((identity, candidate, reason))

    if not blocked:
        return None
    blocked.sort(key=lambda item: item[0])
    shown = blocked[:3]
    details = "; ".join(
        _return_identity(candidate) + " — " + reason
        for _, candidate, reason in shown
    )
    extra = len(blocked) - len(shown)
    suffix = f"; ещё {extra}" if extra > 0 else ""
    return (
        "🔒 Return COGS пока не применён. Точные блокеры авторизации: "
        + details
        + suffix
        + ". Авторизация не создаётся автоматически и не заменяет бухгалтерское признание."
    )


def _application_authorization_reason(record, recognition, identity):
    if not isinstance(record, dict):
        return "нет отдельной авторизации применения к прибыли"
    if record.get("error") is True:
        return "свидетельство авторизации недоступно"
    if record.get("error") is not False:
        return "свидетельство авторизации невалидно"
    if str(record.get("status") or "").strip().upper() != "RETURN_COGS_PROFIT_APPLICATION_AUTHORIZATION_READY":
        return "авторизация не готова"
    if record.get("application_authorization_confirmed") is not True:
        return "явная авторизация применения к прибыли отсутствует"
    if str(record.get("application_state") or "").strip().upper() != "PROFIT_APPLICATION_AUTHORIZED":
        return "состояние PROFIT_APPLICATION_AUTHORIZED не подтверждено"
    if record.get("application_already_applied") is not False:
        return "не подтверждено, что применение ещё не выполнено"
    if _return_identity_key(record) != identity:
        return "точная идентичность авторизации не совпадает с возвратом"
    if not isinstance(recognition, dict):
        return "версия бухгалтерского признания для авторизации не подтверждена"
    recognition_history_id = _positive_int_or_none(recognition.get("history_id"))
    if recognition_history_id is None:
        return "версия бухгалтерского признания отсутствует"
    if _positive_int_or_none(record.get("recognition_history_id")) != recognition_history_id:
        return "авторизация относится к другой версии бухгалтерского признания"
    authorized_amount = _money_number(record.get("authorized_amount"))
    recognized_amount = _money_number(recognition.get("recognized_amount"))
    if authorized_amount is None:
        return "авторизованная сумма отсутствует или невалидна"
    if recognized_amount is None:
        return "признанная сумма для сверки авторизации отсутствует"
    if abs(authorized_amount - recognized_amount) > 0.01:
        return "авторизованная сумма не совпадает с бухгалтерски признанной"
    if str(record.get("currency") or "").strip().upper() != "RUB":
        return "валюта авторизации не подтверждена как RUB"
    if str(record.get("recovery_accounting_date") or "").strip() != str(recognition.get("recovery_accounting_date") or "").strip():
        return "дата авторизации не совпадает с датой бухгалтерского признания"
    if str(record.get("monetary_authority_treatment") or "").strip().upper() != "EXCLUDED_FROM_ACCOUNT_NET_ACCRUAL":
        return "не подтверждено исключение из account net accrual"
    if record.get("monetary_authority_non_overlap_confirmed") is not True:
        return "не подтверждено отсутствие пересечения с денежным authority"
    if record.get("compensation_non_overlap_confirmed") is not True:
        return "не подтверждено отсутствие пересечения с компенсацией"
    return None


def _application_commit_diagnostic(evidence):
    candidates = evidence.get("candidate_records")
    recognition_records = evidence.get("return_cogs_accounting_recognition_evidence_records")
    authorization_records = evidence.get("return_cogs_profit_application_authorization_records")
    commit_records = evidence.get("return_cogs_profit_application_commit_records")
    if not isinstance(candidates, list) or not candidates:
        return None
    if not isinstance(recognition_records, list):
        recognition_records = []
    if not isinstance(authorization_records, list):
        authorization_records = []
    if not isinstance(commit_records, list):
        commit_records = []

    recognition_index = _identity_index(recognition_records)
    authorization_index = _identity_index(authorization_records)
    commit_index = _identity_index(commit_records)
    blocked = []
    for candidate in candidates:
        identity = _return_identity_key(candidate)
        if identity is None:
            continue
        reason = _application_commit_reason(
            commit_index.get(identity),
            recognition_index.get(identity),
            authorization_index.get(identity),
            evidence.get("return_cogs_profit_application_commit_ready") is True,
        )
        if reason is not None:
            blocked.append((identity, candidate, reason))

    if not blocked:
        return None
    blocked.sort(key=lambda item: item[0])
    shown = blocked[:3]
    details = "; ".join(
        _return_identity(candidate) + " — " + reason
        for _, candidate, reason in shown
    )
    extra = len(blocked) - len(shown)
    suffix = f"; ещё {extra}" if extra > 0 else ""
    return (
        "🔒 Return COGS пока не применён. Точные блокеры exact-once commit: "
        + details
        + suffix
        + ". Текущий ответ остаётся read-only; наличие готовности не считается выполненным commit."
    )


def _application_commit_reason(record, recognition, authorization, commit_ready):
    if not isinstance(recognition, dict):
        return "версия бухгалтерского признания для commit отсутствует"
    history_id = _positive_int_or_none(recognition.get("history_id"))
    if history_id is None:
        return "версия бухгалтерского признания для commit невалидна"
    if not isinstance(authorization, dict):
        return "версия авторизации для commit отсутствует"
    authorization_history_id = _positive_int_or_none(authorization.get("history_id"))
    if authorization_history_id is None:
        return "версия авторизации для commit невалидна"
    if not isinstance(record, dict):
        if commit_ready:
            return "готов к exact-once commit, но запись commit ещё отсутствует"
        return "запись exact-once commit отсутствует"
    if record.get("error") is True:
        return "свидетельство commit недоступно"
    if record.get("error") is not False:
        return "свидетельство commit невалидно"
    if record.get("application_commit_confirmed") is not True:
        return "commit ещё не подтверждён"
    if _positive_int_or_none(record.get("recognition_history_id")) != history_id:
        return "commit относится к другой версии бухгалтерского признания"
    if _return_identity_key(record) != _return_identity_key(recognition):
        return "точная идентичность commit не совпадает с признанием"
    if str(record.get("recovery_accounting_date") or "").strip() != str(recognition.get("recovery_accounting_date") or "").strip():
        return "дата commit не совпадает с датой бухгалтерского признания"
    committed_amount = _money_number(record.get("committed_amount"))
    recognized_amount = _money_number(recognition.get("recognized_amount"))
    if committed_amount is None:
        return "сумма commit отсутствует или невалидна"
    if recognized_amount is None:
        return "признанная сумма для сверки commit отсутствует"
    if abs(committed_amount - recognized_amount) > 0.01:
        return "сумма commit не совпадает с бухгалтерски признанной"
    if str(record.get("currency") or "").strip().upper() != "RUB":
        return "валюта commit не подтверждена как RUB"
    if _positive_int_or_none(record.get("authorization_history_id")) != authorization_history_id:
        return "commit относится к другой версии авторизации"
    return None


def _identity_index(records):
    result = {}
    for row in records:
        identity = _return_identity_key(row)
        if identity is not None and identity not in result:
            result[identity] = row
    return result


def _return_identity_key(row):
    if not isinstance(row, dict):
        return None
    values = tuple(
        str(row.get(key) or "").strip()
        for key in ("return_id", "posting_number", "sku")
    )
    return values if all(values) else None


def _return_identity(row):
    return_id = _text_or_unknown(row.get("return_id"))
    posting = _text_or_unknown(row.get("posting_number"))
    sku = _text_or_unknown(row.get("sku"))
    quantity = _positive_int_or_none(row.get("quantity"))
    quantity_text = str(quantity) if quantity is not None else "неизвестно"
    return (
        "return_id="
        + return_id
        + ", posting="
        + posting
        + ", SKU="
        + sku
        + ", кол-во="
        + quantity_text
    )


def _text_or_unknown(value):
    text = str(value or "").strip()
    return text if text else "неизвестно"


def _positive_int_or_none(value):
    if isinstance(value, bool):
        return None
    try:
        number = int(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if number > 0 else None


def _money_number(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if not isfinite(number) or number < 0.0:
        return None
    return round(number, 2)


def _unconfirmed_return_cogs_units(evidence):
    unresolved = _non_negative_int(evidence.get("unresolved_units"))
    if evidence.get("period_cogs_recovery_confirmed") is True:
        return unresolved

    candidate_units = 0
    records = evidence.get("candidate_records")
    if not isinstance(records, list):
        return unresolved

    for row in records:
        if not isinstance(row, dict):
            continue
        state = str(row.get("inventory_recovery_state") or "").strip().upper()
        status = str(row.get("inventory_recovery_evidence_status") or "").strip().upper()
        if status == "RETURN_INVENTORY_RECOVERY_READY" and state == "NON_SALEABLE":
            continue
        quantity = _non_negative_int(row.get("quantity"))
        candidate_units += quantity

    return unresolved + candidate_units


def _comparison_line(comparison):
    if not isinstance(comparison, dict):
        return None
    if comparison.get("status") != "PERIOD_PROFIT_COMPARISON_READY":
        return None

    value = _finite_number(comparison.get("profit_change"))
    if value is None:
        return None

    if value > 0:
        icon = "📈"
        sign = "+"
    elif value < 0:
        icon = "📉"
        sign = "−"
    else:
        icon = "➡️"
        sign = ""

    return icon + " К прошлому периоду: " + sign + _money(abs(value))


def _period(date_from, date_to):
    start = _date(date_from)
    end = _date(date_to)
    if start is None or end is None:
        return f"{date_from} — {date_to}"
    if start.year == end.year:
        return f"{start:%d.%m}–{end:%d.%m}"
    return f"{start:%d.%m.%Y}–{end:%d.%m.%Y}"


def _date(value):
    try:
        return datetime.strptime(str(value), "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


def _money(value):
    number = _finite_number(value)
    if number is None:
        return "—"
    try:
        rounded = Decimal(str(number)).quantize(
            Decimal("1"),
            rounding=ROUND_HALF_UP,
        )
    except (InvalidOperation, ValueError):
        return "—"
    integer = int(rounded)
    return f"{integer:,}".replace(",", " ") + " ₽"


def _units(value):
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return "—"
    return f"{value:,}".replace(",", " ") + " шт."


def _percent(value):
    number = _finite_number(value)
    if number is None:
        return "—"
    return f"{number:.2f}%".replace(".", ",")


def _finite_number(value):
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if isfinite(number) else None


def _non_negative_int(value):
    if isinstance(value, bool):
        return 0
    try:
        number = int(value)
    except (TypeError, ValueError, OverflowError):
        return 0
    return number if number > 0 else 0
