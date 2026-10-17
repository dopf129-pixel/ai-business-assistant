from period_profit_completeness_view import PeriodProfitCompletenessViewService
from services.assistant_keyboard_service import AssistantKeyboardService
from services.assistant_button_handler_service import AssistantButtonHandlerService
from services.assistant_period_profit_runtime_service import (
    AssistantPeriodProfitRuntimeService,
)
from services.period_profit_operation_diagnostics import (
    PeriodProfitOperationTrace,
    activate_period_profit_trace,
    reset_period_profit_trace,
)
from services.tenant_context import (
    reset_current_tenant_user_id,
    set_current_tenant_user_id,
)


START = "2026-08-01"
END = "2026-08-31"


def _result(*, candidates=None, compensated=None, unresolved=None, **evidence_overrides):
    candidates = list(candidates or [])
    compensated = list(compensated or [])
    unresolved = list(unresolved or [])
    candidate_units = sum(row.get("quantity", 0) for row in candidates)
    compensated_units = sum(row.get("quantity", 0) for row in compensated)
    evidence = {
        "error": False,
        "status": "PERIOD_PROFIT_RETURN_COGS_RECOVERY_EVIDENCE_READY",
        "candidate_records": candidates,
        "candidate_recovery_units": candidate_units,
        "compensated_records": compensated,
        "compensated_units": compensated_units,
        "unresolved_units": sum(
            row.get("quantity", 0)
            for row in unresolved
            if isinstance(row.get("quantity"), int) and not isinstance(row.get("quantity"), bool)
        ),
        "customer_return_units": candidate_units + compensated_units + sum(
            row.get("quantity", 0)
            for row in unresolved
            if isinstance(row.get("quantity"), int) and not isinstance(row.get("quantity"), bool)
        ),
        "unresolved_records": unresolved,
        "return_sample_complete": True,
        "historical_cost_basis_confirmed": False,
        "historical_cost_candidate_record_count": len(candidates),
        "historical_cost_matched_candidate_record_count": 0,
        "candidate_value_at_historical_cost": None,
        "accounting_attribution_evidence_status": "NOT_CONFIRMED",
        "accounting_attribution_evidence_confirmed": False,
        "return_cogs_accounting_recognition_status": "NOT_CONFIRMED",
        "return_cogs_accounting_recognition_evidence_confirmed": False,
        "return_cogs_profit_application_eligibility_status": "NOT_CONFIRMED",
        "return_cogs_profit_application_eligibility_confirmed": False,
        "return_cogs_profit_application_commit_status": "NOT_CONFIRMED",
        "return_cogs_profit_application_commit_confirmed": False,
        "return_cogs_profit_applied": False,
        "return_cogs_profit_application_amount": None,
    }
    evidence.update(evidence_overrides)
    return {
        "error": False,
        "status": "PERIOD_PROFIT_QUERY_READY",
        "request": {"date_from": START, "date_to": END},
        "summary": {
            "error": False,
            "status": "PERIOD_PROFIT_SUMMARY_READY",
            "date_from": START,
            "date_to": END,
            "revenue": 1000.0,
            "net_accrual": 500.0,
            "tax": 60.0,
            "tax_base": 1000.0,
            "tax_mode": "USN_INCOME",
            "tax_rate_percent": 6.0,
            "tax_policy_applied": True,
            "profit": 340.0,
            "margin_percent": 34.0,
            "product_cost": 100.0,
            "units_sold": 3,
            "product_count": 1,
            "products": [{"sku": "12345", "units_sold": 3}],
            "account_level_ozon_accruals_included": True,
            "product_revenue_reconciled": True,
        },
        "return_evidence": {
            "error": False,
            "status": "PERIOD_PROFIT_RETURN_EVIDENCE_READY",
            "date_from": START,
            "date_to": END,
            "complete": True,
            "return_record_count_exact": True,
            "return_record_count": len(candidates) + len(compensated) + len(unresolved),
            "records": [
                {
                    "id": row.get("return_id"),
                    "posting_number": row.get("posting_number"),
                    "sku": row.get("sku"),
                    "quantity": row.get("quantity"),
                }
                for row in candidates + compensated + unresolved
            ],
        },
        "return_cogs_recovery_evidence": evidence,
        "external_expense_evidence": {
            "error": False,
            "status": "PERIOD_PROFIT_EXTERNAL_EXPENSE_EVIDENCE_PARTIAL",
            "date_from": START,
            "date_to": END,
            "coverage_complete": False,
            "coverage_gaps": [{"date_from": START, "date_to": END}],
            "observed_expense_total": 0.0,
        },
        "advertising_financial_evidence": {
            "error": False,
            "status": "PERIOD_PROFIT_EXPENSE_EVIDENCE_READY",
            "policy_configured": False,
        },
        "read_only": True,
        "executed": False,
    }


def _candidate(**overrides):
    row = {
        "return_id": "ret-1",
        "posting_number": "post-1",
        "sku": "12345",
        "quantity": 2,
        "inventory_recovery_state": "",
        "inventory_recovery_evidence_status": "RETURN_INVENTORY_RECOVERY_MISSING",
    }
    row.update(overrides)
    return row


def test_completeness_view_separates_candidate_records_from_units_and_first_inventory_blocker():
    view = PeriodProfitCompletenessViewService().build(
        _result(candidates=[_candidate()])
    )

    assert view["status"] == "PERIOD_PROFIT_COMPLETENESS_READY"
    assert "Базовая прибыль: 340.00 ₽" in view["message"]
    assert "1 кандидатов / 2 шт." in view["message"]
    assert "первый блокер — фактическое состояние возврата" in view["message"]
    assert "return ret-1, отправление post-1, SKU 12345, 2 шт." in view["message"]
    assert "return_inventory" in view["actions"]
    assert "Налог: ПОДТВЕРЖДЕНО" in view["message"]
    assert "Внешние расходы: ЧАСТИЧНО" in view["message"]
    assert "Реклама (отдельная сверка): НЕИЗВЕСТНО" in view["message"]


def test_non_saleable_inventory_moves_to_accounting_attribution_blocker():
    candidate = _candidate(
        inventory_recovery_state="NON_SALEABLE",
        inventory_recovery_evidence_status="RETURN_INVENTORY_RECOVERY_READY",
    )
    view = PeriodProfitCompletenessViewService().build(
        _result(candidates=[candidate])
    )

    assert "первый блокер — бухгалтерская атрибуция" in view["message"]
    assert "return_inventory" not in view["actions"]
    assert "в боте пока нет подтверждённого действия для этой стадии" in view["message"]


def test_compensated_return_is_counted_separately_and_not_applied_again():
    view = PeriodProfitCompletenessViewService().build(
        _result(compensated=[{
            "return_id": "r1",
            "posting_number": "p1",
            "sku": "sku1",
            "quantity": 3,
        }])
    )

    assert "0 кандидатов / 0 шт." in view["message"]
    assert "1 компенсированных записей / 3 шт." in view["message"]
    assert "Возвраты / Return COGS: ПОДТВЕРЖДЕНО" in view["message"]
    assert "сумма не добавлялась повторно" in view["message"]


def test_missing_quantity_is_partial_and_never_confirmed():
    view = PeriodProfitCompletenessViewService().build(
        _result(unresolved=[{"return_id": "r1", "reason": "QUANTITY_INVALID"}])
    )

    assert "Возвраты / Return COGS: ЧАСТИЧНО" in view["message"]
    assert "единиц с известным количеством: 0" in view["message"]
    assert "записей без количества: 1" in view["message"]


def test_conflicting_inventory_keeps_candidate_unconfirmed_and_identity_scoped_in_view():
    candidate = _candidate(
        inventory_recovery_evidence_status="RETURN_INVENTORY_RECOVERY_IDENTITY_CONFLICT"
    )
    view = PeriodProfitCompletenessViewService().build(
        _result(candidates=[candidate])
    )

    assert "Возвраты / Return COGS: ЧАСТИЧНО" in view["message"]
    assert "return_inventory" in view["actions"]
    assert "ret-1" in view["message"]


def test_stale_return_period_is_error_not_confirmed():
    result = _result()
    result["return_evidence"]["date_from"] = "2026-07-01"
    view = PeriodProfitCompletenessViewService().build(result)

    assert "Возвраты / Return COGS: ОШИБКА" in view["message"]
    assert "период evidence возвратов не совпадает" in view["message"]


def test_candidate_unit_totals_must_reconcile_with_source_records():
    result = _result(candidates=[_candidate()])
    result["return_cogs_recovery_evidence"]["candidate_recovery_units"] = 9
    view = PeriodProfitCompletenessViewService().build(result)

    assert "Возвраты / Return COGS: ОШИБКА" in view["message"]
    assert "не сходится" in view["message"]


def test_partial_raw_return_sample_does_not_raise_confirmed_claim():
    result = _result(compensated=[{
        "return_id": "r1",
        "posting_number": "p1",
        "sku": "sku1",
        "quantity": 1,
    }])
    result["return_evidence"]["complete"] = False
    result["return_cogs_recovery_evidence"]["return_sample_complete"] = False
    view = PeriodProfitCompletenessViewService().build(result)

    assert "Возвраты / Return COGS: ЧАСТИЧНО" in view["message"]


def test_recognition_and_authorization_blockers_are_reported_without_actions():
    candidate = _candidate(
        inventory_recovery_state="SALEABLE_RESTORED",
        inventory_recovery_evidence_status="RETURN_INVENTORY_RECOVERY_READY",
    )
    result = _result(candidates=[candidate])
    evidence = result["return_cogs_recovery_evidence"]
    evidence["accounting_attribution_evidence_status"] = (
        "PERIOD_PROFIT_RETURN_COGS_ACCOUNTING_EVIDENCE_READY"
    )
    evidence["accounting_attribution_evidence_confirmed"] = True
    evidence["return_cogs_accounting_recognition_status"] = "STALE"
    view = PeriodProfitCompletenessViewService().build(result)

    assert "бухгалтерское признание" in view["message"]
    assert "return_inventory" not in view["actions"]
    assert "в боте пока нет подтверждённого действия" in view["message"]

    evidence["return_cogs_accounting_recognition_status"] = (
        "PERIOD_PROFIT_RETURN_COGS_ACCOUNTING_RECOGNITION_READY"
    )
    evidence["return_cogs_accounting_recognition_evidence_confirmed"] = True
    evidence["return_cogs_profit_application_eligibility_status"] = "STALE"
    second_view = PeriodProfitCompletenessViewService().build(result)
    assert "авторизация применения" in second_view["message"]
    assert "return_inventory" not in second_view["actions"]


def test_idempotent_commit_result_requires_bound_final_application_chain():
    result = _result(candidates=[_candidate(
        inventory_recovery_state="NON_SALEABLE",
        inventory_recovery_evidence_status="RETURN_INVENTORY_RECOVERY_READY",
    )])
    evidence = result["return_cogs_recovery_evidence"]
    evidence.update({
        "accounting_attribution_evidence_status": "PERIOD_PROFIT_RETURN_COGS_ACCOUNTING_EVIDENCE_READY",
        "accounting_attribution_evidence_confirmed": True,
        "return_cogs_accounting_recognition_status": "PERIOD_PROFIT_RETURN_COGS_ACCOUNTING_RECOGNITION_READY",
        "return_cogs_accounting_recognition_evidence_confirmed": True,
        "return_cogs_profit_application_eligibility_status": "PERIOD_PROFIT_RETURN_COGS_APPLICATION_ELIGIBILITY_READY",
        "return_cogs_profit_application_eligibility_confirmed": True,
        "return_cogs_profit_application_commit_status": "PERIOD_PROFIT_RETURN_COGS_APPLICATION_COMMIT_CONFIRMED",
        "return_cogs_profit_application_commit_confirmed": True,
        "return_cogs_profit_applied": True,
        "return_cogs_final_application_chain_bound": True,
        "return_cogs_profit_application_amount": 25.0,
    })
    result["summary"]["return_cogs_profit_applied"] = True
    result["summary"]["period_profit_before_return_cogs"] = 340.0
    result["summary"]["return_cogs_profit_application_amount"] = 25.0
    view = PeriodProfitCompletenessViewService().build(result)

    assert "Возвраты / Return COGS: ПОДТВЕРЖДЕНО" in view["message"]
    assert "цепочка применена и подтверждена" in view["message"]


def test_applied_flag_without_bound_chain_is_error_not_confirmed():
    result = _result()
    result["return_cogs_recovery_evidence"]["return_cogs_profit_applied"] = True
    result["summary"]["return_cogs_profit_applied"] = True
    result["summary"]["period_profit_before_return_cogs"] = 340.0
    view = PeriodProfitCompletenessViewService().build(result)

    assert "Возвраты / Return COGS: ОШИБКА" in view["message"]


def test_runtime_reopens_cached_completeness_without_network_and_scopes_by_user_and_store():
    class Query:
        def __init__(self):
            self.calls = 0

        def query(self, **_kwargs):
            self.calls += 1
            return _result()

    query = Query()
    runtime = AssistantPeriodProfitRuntimeService(
        query, keyboard_service=AssistantKeyboardService()
    )
    tenant_token = set_current_tenant_user_id("store-A")
    try:
        report = runtime.handle_text("прибыль за 28 дней", user_id="telegram-1")
        view_id = report["report_view_id"]
        detail = runtime.handle_cached_view(
            "period_profit_completeness:" + view_id,
            user_id="telegram-1",
        )
        back = runtime.handle_cached_view(
            "period_profit_report:" + view_id,
            user_id="telegram-1",
        )
        wrong_user = runtime.handle_cached_view(
            "period_profit_completeness:" + view_id,
            user_id="telegram-2",
        )
        assert detail["status"] == "PERIOD_PROFIT_COMPLETENESS_READY"
        assert back["text"] == report["text"]
        assert wrong_user["status"] == "PERIOD_PROFIT_CACHED_VIEW_EXPIRED"
        assert query.calls == 1

        reset_current_tenant_user_id(tenant_token)
        tenant_token = set_current_tenant_user_id("store-B")
        wrong_store = runtime.handle_cached_view(
            "period_profit_completeness:" + view_id,
            user_id="telegram-1",
        )
        assert wrong_store["status"] == "PERIOD_PROFIT_CACHED_VIEW_EXPIRED"
        assert query.calls == 1
    finally:
        reset_current_tenant_user_id(tenant_token)


def test_telegram_button_handler_routes_cached_completeness_with_user_scope():
    class Query:
        def __init__(self):
            self.calls = 0

        def query(self, **_kwargs):
            self.calls += 1
            return _result()

    query = Query()
    keyboard = AssistantKeyboardService()
    runtime = AssistantPeriodProfitRuntimeService(query, keyboard_service=keyboard)
    handler = AssistantButtonHandlerService(
        assistant=None,
        keyboard_service=keyboard,
        period_profit_runtime_service=runtime,
    )
    tenant_token = set_current_tenant_user_id("store-A")
    try:
        report = runtime.handle_text("прибыль за 28 дней", user_id="telegram-1")
        detail = handler.handle(
            "period_profit_completeness:" + report["report_view_id"],
            user_id="telegram-1",
        )
        other_user = handler.handle(
            "period_profit_completeness:" + report["report_view_id"],
            user_id="telegram-2",
        )

        assert detail["status"] == "PERIOD_PROFIT_COMPLETENESS_READY"
        assert other_user["status"] == "PERIOD_PROFIT_CACHED_VIEW_EXPIRED"
        assert query.calls == 1
    finally:
        reset_current_tenant_user_id(tenant_token)


def test_diagnostic_screen_uses_exact_cached_report_without_source_calls():
    class Query:
        def __init__(self):
            self.calls = 0

        def query(self, **_kwargs):
            self.calls += 1
            return _result()

    query = Query()
    keyboard = AssistantKeyboardService()
    runtime = AssistantPeriodProfitRuntimeService(query, keyboard_service=keyboard)
    handler = AssistantButtonHandlerService(
        assistant=None,
        keyboard_service=keyboard,
        period_profit_runtime_service=runtime,
    )
    tenant_token = set_current_tenant_user_id("store-A")
    trace = PeriodProfitOperationTrace("period_profit", ozon_request_budget=4)
    trace_token = activate_period_profit_trace(trace)
    try:
        trace.record_posting("private-posting-id")
        trace.record_posting_result("completed")
        trace.reserve_ozon_request("/source")
        report = runtime.handle_text("прибыль за 28 дней", user_id="telegram-1")
    finally:
        reset_period_profit_trace(trace_token)
    try:
        diagnostic = handler.handle(
            "period_profit_diagnostics:" + report["report_view_id"],
            user_id="telegram-1",
        )
        wrong_user = handler.handle(
            "period_profit_diagnostics:" + report["report_view_id"],
            user_id="telegram-2",
        )

        assert diagnostic["status"] == "PERIOD_PROFIT_DIAGNOSTICS_READY"
        assert "HTTP-попытки 1/4" in diagnostic["text"]
        assert "1 завершено, 0 неизвестно из 1 попыток" in diagnostic["text"]
        assert "private-posting-id" not in diagnostic["text"]
        assert any(
            button["callback"] == "period_profit_completeness:" + report["report_view_id"]
            for button in diagnostic["keyboard"]["buttons"]
        )
        assert wrong_user["status"] == "PERIOD_PROFIT_CACHED_VIEW_EXPIRED"
        assert query.calls == 1
    finally:
        reset_current_tenant_user_id(tenant_token)


def test_invalid_or_mismatched_report_period_is_never_presented_as_complete():
    result = _result()
    result["request"]["date_to"] = "2026-09-01"
    view = PeriodProfitCompletenessViewService().build(result)

    assert view["status"] == "PERIOD_PROFIT_COMPLETENESS_UNAVAILABLE"


def test_assistant_button_handler_routes_cached_screen_with_user_scope():
    class Query:
        def query(self, **_kwargs):
            return _result()

    keyboard = AssistantKeyboardService()
    runtime = AssistantPeriodProfitRuntimeService(
        Query(), keyboard_service=keyboard
    )
    token = set_current_tenant_user_id("store-A")
    try:
        report = runtime.handle_text("прибыль за 28 дней", user_id="telegram-1")
        handler = AssistantButtonHandlerService(
            assistant=None,
            keyboard_service=keyboard,
            period_profit_runtime_service=runtime,
        )
        view = handler.handle(
            "period_profit_completeness:" + report["report_view_id"],
            user_id="telegram-1",
        )

        assert view["status"] == "PERIOD_PROFIT_COMPLETENESS_READY"
        assert view["keyboard"]["buttons"][-2]["callback"].startswith(
            "period_profit_report:"
        )
        assert view["read_only"] is True
        assert view["executed"] is False
    finally:
        reset_current_tenant_user_id(token)
