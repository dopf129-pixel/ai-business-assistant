from concurrent.futures import ThreadPoolExecutor
from threading import Event

from api.base_ozon_client import OzonClient as BaseOzonClient
from services.assistant_button_handler_service import AssistantButtonHandlerService
from services.assistant_keyboard_service import AssistantKeyboardService
from services.experimental_store_economics_runtime_service import (
    ExperimentalStoreEconomicsRuntimeService,
)
from services.finance_service import FinanceService
from services.period_profit_cost_exclusion_context import cost_excluded
from telegram_app_layer.assistant_telegram_adapter import AssistantTelegramAdapter
from telegram_app_layer.telegram_bot_service import TelegramBotService
from telegram_app_layer.telegram_command_service import TelegramCommandService
from telegram_app_layer.telegram_response_formatter import TelegramResponseFormatter


class _Summary:
    def __init__(self):
        self.calls = []

    def calculate(self, date_from, date_to, products):
        self.calls.append((date_from, date_to, products, cost_excluded()))
        assert cost_excluded() is True
        return {
            "error": False,
            "status": "PERIOD_PROFIT_SUMMARY_READY",
            "date_from": date_from,
            "date_to": date_to,
            "revenue": 100000.0,
            "revenue_tax_base": 92000.0,
            "discount_points": 8000.0,
            "net_accrual": 18520.0,
            "tax": 5520.0,
            "profit": 13000.0,
            "acquiring": -1500.0,
            "commission": -22000.0,
            "logistics": -18000.0,
            "other_fees": -3600.0,
            "products": [{"sku": "9001"}],
            "fee_breakdown": {
                "Доставка до места выдачи": -8000.0,
            "Выдача товара": -500.0,
                "Услуги кросс-докинга": -1200.0,
                "Плата за вынужденное размещение на складе": -350.0,
                "PayPerClick CPC": -3000.0,
                "Оплата за заказ CPO": -400.0,
                "Услуги комплектации": -200.0,
                "Обратная логистика": -4482.24,
                "Обработка товара": -1650.0,
                "Размещение": -1.74,
            },
        }


class _CommissionSummary(_Summary):
    def calculate(self, date_from, date_to, products):
        result = super().calculate(date_from, date_to, products)
        result.update(
            {
                "revenue": 489721.93,
                "revenue_tax_base": 365690.33,
                "discount_points": 124031.60,
                "net_accrual": 177282.17,
                "tax": 21941.42,
                "profit": 155340.75,
                "acquiring": -6176.40,
                "commission": -69163.97,
                "logistics": -131128.88,
                "other_fees": -105970.51,
            }
        )
        result["fee_breakdown"].pop("Размещение", None)
        result["accrual_type_breakdown"] = {
            "501": {
                "name": "SaleCommission",
                "description": "Вознаграждение за продажу",
                "amount": -69193.10,
            },
            "502": {
                "name": "CommissionRefund",
                "description": "Возврат вознаграждения",
                "amount": 25.20,
            },
            "503": {
                "name": "WarehousePlacement",
                "description": "Размещение на складе",
                "amount": -1.74,
            },
        }
        return result


class _FinanceBackedCommissionSummary:
    """Use FinanceService's real accrual parser with stable API fixtures."""

    def __init__(self):
        self.finance = FinanceService()
        self.finance_service = self.finance
        self.finance.accrual_types = {
            1: {"name": "Acquiring", "description": "Эквайринг"},
            29: {"name": "Logistics", "description": "Логистика"},
            46: {
                "name": "Placements",
                "description": "Размещение на складе",
            },
            69: {
                "name": "SaleCommission",
                "description": "Вознаграждение за продажу",
            },
            70: {
                "name": "CommissionRefund",
                "description": "Возврат вознаграждения",
            },
        }
        self.finance._get_accruals_by_day = lambda _day: {
            "error": False,
            "accruals": [
                {
                    "accrual_id": 9000001,
                    "accrued_category": "POSTING",
                    "unit_number": "fixture-posting-1",
                    "total_amount": {"amount": "177282.17"},
                    "posting": {
                        "products": [
                            {
                                "sku": "fixture-sku",
                                "commission": {
                                    "sale_amount": {"amount": "489721.93"},
                                    "bonus": {"amount": "124031.60"},
                                    "sale_commission": {"amount": "-69163.97"},
                                },
                                "delivery": {
                                    "services": [
                                        {
                                            "type_id": 1,
                                            "accrued": {"amount": "-6176.40"},
                                        },
                                        {
                                            "type_id": 29,
                                            "accrued": {"amount": "-131128.88"},
                                        },
                                    ]
                                },
                            }
                        ]
                    },
                },
            ],
        }

    def calculate(self, date_from, date_to, products):
        daily = self.finance.get_daily_account_finance("2026-08-15")
        revenue = daily["gross_sales"]
        discount_points = daily["discount_points"]
        tax = 21941.42
        return {
            "error": False,
            "status": "PERIOD_PROFIT_SUMMARY_READY",
            "revenue": revenue,
            "revenue_tax_base": round(revenue - discount_points, 2),
            "discount_points": discount_points,
            "net_accrual": daily["net_accrual"],
            "tax": tax,
            "profit": round(daily["net_accrual"] - tax, 2),
            "acquiring": daily["acquiring"],
            "commission": daily["commission"],
            "logistics": daily["logistics"],
            "other_fees": daily["other_fees"],
            "products": products,
            "fee_breakdown": daily["fee_breakdown"],
            "accrual_type_breakdown": daily["accrual_type_breakdown"],
        }


class _FinanceAccrualPostings:
    def __init__(self, result=None):
        self.calls = []
        self.result = result or {
            "error": False,
            "posting_accruals": [
                {
                    "posting_number": "fixture-posting-1",
                    "accruals": [
                        {
                            "type_id": 69,
                            "accrued": {"amount": "-69193.10"},
                        },
                        {
                            "type_id": 70,
                            "accrued": {"amount": "25.20"},
                        },
                        *[
                            {
                                "type_id": 46,
                                "accrued": {"amount": "-0.58"},
                            }
                            for _ in range(3)
                        ],
                    ],
                }
            ],
        }

    def get_accruals_by_postings(self, posting_numbers):
        self.calls.append(list(posting_numbers))
        return self.result


class _Query:
    def __init__(self):
        self.summary_service = _Summary()
        self.product_provider = lambda: [{"sku": "1001"}, {"sku": "2002"}]


class _Advertising:
    def __init__(self, result=None):
        self.result = result or {
            "error": False,
            "configured": True,
            "complete": True,
            "expense": 345.67,
            "campaign_count": 2,
        }
        self.calls = []

    def load(self, date_from, date_to, accepted_skus):
        self.calls.append((date_from, date_to, set(accepted_skus)))
        return self.result


class _Analytics:
    def __init__(self, result=None):
        self.result = result or {
            "error": False,
            "result": {
                "data": [
                    {"metrics": [12, 2, 1]},
                    {"metrics": [5, 1, 0]},
                ]
            },
        }
        self.calls = []

    def get_analytics_data(self, date_from, date_to, **kwargs):
        self.calls.append((date_from, date_to, kwargs))
        return self.result


class _Profile:
    def create_user(self, user_id):
        return {"error": False, "user": {"user_id": user_id}}


class _Assistant:
    def __init__(self):
        self.calls = []

    def ask(self, text, user_id=None):
        self.calls.append((text, user_id))
        return {"error": False, "message": "unused assistant"}


def _service(advertising=None, analytics=None):
    query = _Query()
    runtime = ExperimentalStoreEconomicsRuntimeService(
        query,
        advertising_service=advertising or _Advertising(),
        analytics_client=analytics or _Analytics(),
    )
    return query, runtime


def _bot(runtime):
    keyboard = AssistantKeyboardService()
    assistant = _Assistant()
    handler = AssistantButtonHandlerService(
        assistant,
        keyboard_service=keyboard,
        experimental_store_economics_runtime_service=runtime,
    )
    adapter = AssistantTelegramAdapter(
        assistant,
        keyboard,
        handler,
        _Profile(),
    )
    bot = TelegramBotService(
        adapter,
        TelegramCommandService(adapter),
    )
    return bot, assistant


def _report_text(result):
    return "\n".join(
        value
        for value in (result.get("text"), result.get("details_text"))
        if isinstance(value, str)
    )


def test_store_economics_uses_existing_pre_cogs_profit_and_adds_only_confirmed_values():
    query = _Query()
    ads = _Advertising()
    analytics = _Analytics()
    runtime = ExperimentalStoreEconomicsRuntimeService(
        query,
        advertising_service=ads,
        analytics_client=analytics,
    )

    result = runtime.handle_callback(
        "experimental_store_economics:7D",
        today="2026-10-05",
    )

    assert result["error"] is False
    assert result["cost_excluded"] is True
    assert result["profit_complete"] is False
    assert result["metrics"]["profit"] == 13000.0
    assert result["metrics"]["advertising"]["cpc"] == 345.67
    assert result["metrics"]["analytics"]["ordered_units"] == 17
    assert result["metrics"]["analytics"]["cancellations"] == 3
    assert result["metrics"]["analytics"]["returns"] == 1
    assert result["metrics"]["fee_subcategories"] == {
        "last_mile": -8500.0,
        "cross_docking": -1200.0,
        "paid_storage": -351.74,
        "reverse_logistics": -4482.24,
    }
    assert result["metrics"]["finance_advertising"]["groups"]["CPC"]["amount"] == -3000.0
    assert result["metrics"]["finance_advertising"]["groups"]["CPO"]["amount"] == -400.0
    assert result["metrics"]["accrual_diagnostics"] == {
        "fee_type_count": 10,
        "commission_matches": 0,
        "storage_matches": 2,
    }
    assert "Начисления по отправлениям недоступны (OZON_FINANCE_POSTING_CLIENT_UNAVAILABLE)." in result["details_text"]
    assert "Справочник типов начислений: 10 типов, явные совпадения комиссии 0, размещения 2." in result["details_text"]
    assert "9001" not in result["details_text"]
    assert "501" not in result["details_text"]
    assert "1. Выручка общая (100%): 100 000.00 ₽" in _report_text(result)
    assert "2. Выручка ФНС (выручка − баллы): 92 000.00 ₽ (92,00% от общей выручки)" in _report_text(result)
    assert "3. Баллы за скидки: 8 000.00 ₽ (8,00% от общей выручки)" in _report_text(result)
    assert "4. Начисления Ozon нетто: 18 520.00 ₽ (18,52% от общей выручки)" in _report_text(result)
    assert "5. Налог: 5 520.00 ₽ (5,52% от общей выручки)" in _report_text(result)
    assert "6. Прибыль без себестоимости: 13 000.00 ₽ (13,00% от общей выручки)" in _report_text(result)
    assert "7. Реклама по начислениям Ozon:" in result["text"]
    assert "CPC: -3 000.00 ₽ (-3,00% от общей выручки)" in result["text"]
    assert "CPO: -400.00 ₽ (-0,40% от общей выручки)" in result["text"]
    assert "Performance CPC для сверки, не входит в сумму: 345.67 ₽ (0,35% от общей выручки) (2 камп.)" in result["text"]
    assert "8. Эквайринг: -1 500.00 ₽ (-1,50% от общей выручки)" in _report_text(result)
    assert "9. Комиссия Ozon (предварительно; возвратная не подтверждена): -22 000.00 ₽ (-22,00% от общей выручки)" in result["text"]
    assert "10. Логистика доставки: -18 000.00 ₽ (-18,00% от общей выручки)" in result["text"]
    assert "До места выдачи и выдача товара, уже в логистике: -8 500.00 ₽ (-8,50% от общей выручки)" in result["text"]
    assert "11. Обратная логистика: -4 482.24 ₽ (-4,48% от общей выручки)" in result["text"]
    assert "12. Кросс-докинг: -1 200.00 ₽ (-1,20% от общей выручки)" in result["text"]
    assert "13. Размещение и хранение: -351.74 ₽ (-0,35% от общей выручки)" in result["text"]
    assert "14. Остальные услуги по явным типам: -1 850.00 ₽ (-1,85% от общей выручки)" in result["text"]
    assert "15. Неразнесённая сверочная разница (баланс, не отдельное начисление):" in result["text"]
    assert "а не самостоятельное удержание" in result["details_text"]
    assert "Обратная логистика" in result["details_text"]
    assert "Обработка товара" in result["details_text"]
    assert "16. Заказанные единицы (Analytics): 17 шт. (100% базы для долей)" in result["text"]
    assert "17. Отменённые единицы (Analytics): 3 шт. (доля не показана:" in result["text"]
    assert "18. Возвраты (Analytics): 1 шт. (доля не показана:" in result["text"]
    assert sum(2 if ord(char) > 0xFFFF else 1 for char in result["text"]) <= 3500
    breakdown = result["metrics"]["expense_breakdown"]
    assert breakdown["period"] == {
        "date_from": "2026-09-29",
        "date_to": "2026-10-05",
    }
    assert breakdown["categories"]["advertising"]["CPC"]["amount"] == -3000.0
    assert breakdown["categories"]["reverse_logistics"]["amount"] == -4482.24
    assert breakdown["categories"]["cross_docking"]["amount"] == -1200.0
    assert breakdown["last_mile"]["additive"] is False
    assert breakdown["performance_cpc_additive"] is False
    assert round(
        result["metrics"]["revenue"]
        + result["metrics"]["acquiring"]
        + result["metrics"]["commission"]
        + result["metrics"]["logistics"]
        + breakdown["classified_other_fees"]
        + breakdown["unallocated_adjustment"]["amount"],
        2,
    ) == result["metrics"]["net_accrual"]
    assert query.summary_service.calls[0][3] is True
    assert cost_excluded() is False
    assert ads.calls[0][2] == {"1001", "2002", "9001"}
    assert analytics.calls[0][2]["metrics"] == ["ordered_units", "cancellations", "returns"]


def test_commission_uses_explicit_accrual_types_and_reconciles_through_telegram():
    query = _Query()
    query.summary_service = _CommissionSummary()
    runtime = ExperimentalStoreEconomicsRuntimeService(
        query,
        advertising_service=_Advertising(),
        analytics_client=_Analytics(),
    )
    bot, _ = _bot(runtime)

    result = bot.on_callback("seller-a", "experimental_store_economics:7D")
    telegram_text = _report_text(result)

    assert result["metrics"]["commission"] == -69167.90
    assert result["metrics"]["other_fees"] == -105966.58
    assert round(
        result["metrics"]["revenue"]
        + result["metrics"]["acquiring"]
        + result["metrics"]["commission"]
        + result["metrics"]["logistics"]
        + result["metrics"]["other_fees"],
        2,
    ) == result["metrics"]["net_accrual"]
    assert "9. Комиссия Ozon (типы финансовых начислений): -69 167.90 ₽ (-14,12% от общей выручки)" in telegram_text
    assert "13. Размещение и хранение: -1.74 ₽" in telegram_text
    assert "Неразнесённая сверочная разница" in telegram_text
    assert "Тип Ozon «Вознаграждение за продажу»" not in telegram_text
    assert "Месячный отчёт реализации не подтвердил комиссию" in telegram_text
    assert result["metrics"]["accrual_diagnostics"] == {
        "fee_type_count": 3,
        "commission_matches": 2,
        "storage_matches": 1,
    }
    assert "Диагностика начислений (" not in telegram_text


def test_unique_accrual_ids_do_not_hide_commission_or_storage_in_telegram():
    query = _Query()
    query.summary_service = _FinanceBackedCommissionSummary()
    transactions = _FinanceAccrualPostings()
    runtime = ExperimentalStoreEconomicsRuntimeService(
        query,
        advertising_service=_Advertising(),
        analytics_client=_Analytics(),
        finance_transaction_client=transactions,
    )
    bot, _ = _bot(runtime)

    result = bot.on_callback("seller-a", "experimental_store_economics:7D")
    telegram_text = _report_text(result)

    assert result["metrics"]["commission"] == -69167.90
    assert result["metrics"]["other_fees"] == -105966.58
    assert "9. Комиссия Ozon (начисления по отправлениям): -69 167.90 ₽" in telegram_text
    assert "13. Размещение и хранение: -1.74 ₽" in telegram_text
    assert "Неразнесённая сверочная разница" in telegram_text
    assert result["metrics"]["commission_source"] == "FINANCE_ACCRUAL_POSTINGS"
    assert result["metrics"]["accrual_diagnostics"] == {
        "fee_type_count": 2,
        "commission_matches": 0,
        "storage_matches": 0,
    }
    assert result["metrics"]["accrual_posting_category_diagnostics"] == {
        "available": True,
        "failure_code": None,
        "posting_count": 1,
        "operation_count": 5,
        "commission_operation_count": 2,
        "commission_sale_operation_count": 1,
        "commission_sale_amount": -69193.10,
        "commission_refund_operation_count": 1,
        "commission_refund_amount": 25.20,
        "commission_other_operation_count": 0,
        "commission_other_amount": None,
        "unmapped_type_count": 0,
        "unmapped_type_amount": None,
        "storage_service_count": 3,
        "paid_storage": -1.74,
    }
    assert transactions.calls == [["fixture-posting-1"]]
    assert "fixture-posting-1" not in telegram_text
    assert "fixture-sku" not in telegram_text
    assert (
        "Список начислений по отправлениям: записей 1, строк начислений 5; "
        "комиссия продажи — строк 1 / -69 193.10 ₽; возврат — строк 1 / "
        "25.20 ₽; размещение — строк 3 / -1.74 ₽; "
        "без типа в справочнике 0 строк."
    ) in telegram_text


def test_commission_posting_diagnostic_exposes_safe_subtotals_and_unmapped_rows():
    query = _Query()
    query.summary_service = _FinanceBackedCommissionSummary()
    transactions = _FinanceAccrualPostings()
    transactions.result["posting_accruals"][0]["accruals"] = [
        {"type_id": 69, "accrued": {"amount": "-69185.11"}},
        {"type_id": 70, "accrued": {"amount": "25.20"}},
        *[
            {"type_id": 46, "accrued": {"amount": "-0.58"}}
            for _ in range(3)
        ],
        {"type_id": 999, "accrued": {"amount": "-7.99"}},
    ]
    runtime = ExperimentalStoreEconomicsRuntimeService(
        query,
        advertising_service=_Advertising(),
        analytics_client=_Analytics(),
        finance_transaction_client=transactions,
    )
    bot, _ = _bot(runtime)

    result = bot.on_callback("seller-a", "experimental_store_economics:7D")
    telegram_text = _report_text(result)

    assert result["metrics"]["commission"] == -69159.91
    assert result["metrics"]["other_fees"] == -105974.57
    assert result["metrics"]["accrual_posting_category_diagnostics"][
        "commission_sale_amount"
    ] == -69185.11
    assert result["metrics"]["accrual_posting_category_diagnostics"][
        "commission_refund_amount"
    ] == 25.20
    assert result["metrics"]["accrual_posting_category_diagnostics"][
        "unmapped_type_amount"
    ] == -7.99
    assert (
        "Список начислений по отправлениям: записей 1, строк начислений 6; "
        "комиссия продажи — строк 1 / -69 185.11 ₽; возврат — строк 1 / "
        "25.20 ₽; размещение — строк 3 / -1.74 ₽; "
        "без типа в справочнике 1 строк / -7.99 ₽."
    ) in telegram_text
    assert "fixture-posting-1" not in telegram_text
    assert "fixture-sku" not in telegram_text
    assert "private" not in telegram_text


def test_monthly_realization_api_uses_supported_v2_report_endpoint():
    client = object.__new__(BaseOzonClient)
    calls = []
    client._post = lambda endpoint, payload, **kwargs: calls.append(
        (endpoint, payload, kwargs)
    ) or {"error": False, "result": {"rows": []}}

    response = client.get_monthly_realization_report(2026, 8)

    assert response == {"error": False, "result": {"rows": []}}
    assert calls == [
        (
            "/v2/finance/realization",
            {"month": 8, "year": 2026},
            {"timeout": 30, "max_attempts": 3},
        )
    ]


def test_full_month_realization_commission_reaches_telegram_with_sales_and_returns():
    query = _Query()
    query.summary_service = _FinanceBackedCommissionSummary()
    realization_calls = []

    def get_monthly_realization_report(year, month):
        realization_calls.append((year, month))
        return {
            "error": False,
            "result": {
                "rows": [
                    {
                        "order": {"posting_number": "private-order-number"},
                        "item": {"name": "private product", "sku": 918273},
                        # Ozon's monthly report may return commission=0 while
                        # carrying the actual base fee in standard_fee.
                        "delivery_commission": {
                            "commission": 0,
                            "standard_fee": 69193.10,
                        },
                        "return_commission": {
                            "commission": 0,
                            "standard_fee": 25.20,
                        },
                    }
                ]
            },
        }

    query.summary_service.finance.ozon.get_monthly_realization_report = (
        get_monthly_realization_report
    )
    transactions = _FinanceAccrualPostings()
    transactions.result["posting_accruals"][0]["accruals"] = [
        {"type_id": 69, "accrued": {"amount": "-69159.91"}},
    ]
    runtime = ExperimentalStoreEconomicsRuntimeService(
        query,
        advertising_service=_Advertising(),
        analytics_client=_Analytics(),
        finance_transaction_client=transactions,
    )
    bot, _ = _bot(runtime)

    bot.on_callback("seller-a", "experimental_store_economics:custom")
    result = bot.on_message("seller-a", "01.08.2026 - 31.08.2026")
    telegram_text = _report_text(result)

    assert result["error"] is False
    assert result["metrics"]["commission"] == -69167.90
    assert result["metrics"]["other_fees"] == -105966.58
    assert result["metrics"]["commission_source"] == "FINANCE_REALIZATION_REPORT"
    assert result["metrics"]["realization_commission_diagnostics"] == {
        "available": True,
        "failure_code": None,
        "month_count": 1,
        "row_count": 1,
        "delivery_commission_row_count": 1,
        "return_commission_row_count": 1,
        "delivery_commission_missing_row_count": 0,
        "return_commission_missing_row_count": 0,
        "sale_fee_row_count": 1,
        "sale_commission_amount": -69193.10,
        "return_fee_row_count": 1,
        "return_commission_amount": 25.20,
        "commission": -69167.90,
    }
    assert "9. Комиссия Ozon (отчёт реализации): -69 167.90 ₽" in telegram_text
    assert "15. Неразнесённая сверочная разница" in telegram_text
    assert "Источник — месячный отчёт реализации Ozon (/v2/finance/realization)" in telegram_text
    assert realization_calls == [(2026, 8)]
    assert "private-order-number" not in telegram_text
    assert "private product" not in telegram_text
    assert "918273" not in telegram_text


def test_full_month_realization_commission_sums_sparse_sale_and_return_rows_to_telegram():
    query = _Query()
    query.summary_service = _FinanceBackedCommissionSummary()
    realization_calls = []

    def get_monthly_realization_report(year, month):
        realization_calls.append((year, month))
        return {
            "error": False,
            "result": {
                "rows": [
                    {
                        "order": {"posting_number": "private-sale-order"},
                        "delivery_commission": {
                            "commission": 0,
                            "standard_fee": 69193.10,
                        },
                    },
                    {
                        "order": {"posting_number": "private-return-order"},
                        "item": {"name": "private product", "sku": 918273},
                        "return_commission": {
                            "commission": 0,
                            "standard_fee": 25.20,
                        },
                    },
                ]
            },
        }

    query.summary_service.finance.ozon.get_monthly_realization_report = (
        get_monthly_realization_report
    )
    transactions = _FinanceAccrualPostings()
    transactions.result["posting_accruals"][0]["accruals"] = [
        {"type_id": 69, "accrued": {"amount": "-69159.91"}},
    ]
    runtime = ExperimentalStoreEconomicsRuntimeService(
        query,
        advertising_service=_Advertising(),
        analytics_client=_Analytics(),
        finance_transaction_client=transactions,
    )
    bot, _ = _bot(runtime)

    bot.on_callback("seller-a", "experimental_store_economics:custom")
    result = bot.on_message("seller-a", "01.08.2026 - 31.08.2026")
    telegram_text = _report_text(result)
    diagnostics = result["metrics"]["realization_commission_diagnostics"]

    assert result["error"] is False
    assert result["metrics"]["commission"] == -69167.90
    assert result["metrics"]["other_fees"] == -105966.58
    assert result["metrics"]["commission_source"] == "FINANCE_REALIZATION_REPORT"
    assert diagnostics["available"] is True
    assert diagnostics["row_count"] == 2
    assert diagnostics["delivery_commission_row_count"] == 1
    assert diagnostics["return_commission_row_count"] == 1
    assert diagnostics["delivery_commission_missing_row_count"] == 1
    assert diagnostics["return_commission_missing_row_count"] == 1
    assert diagnostics["sale_fee_row_count"] == 1
    assert diagnostics["sale_commission_amount"] == -69193.10
    assert diagnostics["return_fee_row_count"] == 1
    assert diagnostics["return_commission_amount"] == 25.20
    assert diagnostics["commission"] == -69167.90
    assert "9. Комиссия Ozon (отчёт реализации): -69 167.90 ₽" in telegram_text
    assert "15. Неразнесённая сверочная разница" in telegram_text
    assert (
        "полных месяцев 1, строк отчёта 2."
        in telegram_text
    )
    assert (
        "Комиссия продажи: 1 строк с суммой -69 193.10 ₽; возврат: "
        "1 строк с суммой 25.20 ₽."
    ) in telegram_text
    assert "Число строк отчёта не является числом продаж или заказанных единиц." in telegram_text
    assert "продажа — операций" not in telegram_text
    assert "возврат — операций" not in telegram_text
    assert realization_calls == [(2026, 8)]
    assert "private-sale-order" not in telegram_text
    assert "private-return-order" not in telegram_text
    assert "private product" not in telegram_text
    assert "918273" not in telegram_text


def test_zero_monthly_realization_commission_is_rejected_and_falls_back_as_preliminary():
    query = _Query()
    query.summary_service = _FinanceBackedCommissionSummary()
    query.summary_service.finance.ozon.get_monthly_realization_report = (
        lambda _year, _month: {
            "error": False,
            "result": {
                "rows": [
                    {
                        "delivery_commission": {
                            "commission": 0,
                            "standard_fee": 0,
                        },
                        "return_commission": {
                            "commission": 0,
                            "standard_fee": 0,
                        },
                    }
                ]
            },
        }
    )
    transactions = _FinanceAccrualPostings(
        {"error": True, "code": "OZON_RATE_LIMITED"}
    )
    runtime = ExperimentalStoreEconomicsRuntimeService(
        query,
        advertising_service=_Advertising(),
        analytics_client=_Analytics(),
        finance_transaction_client=transactions,
    )
    bot, _ = _bot(runtime)

    bot.on_callback("seller-a", "experimental_store_economics:custom")
    result = bot.on_message("seller-a", "01.08.2026 - 31.08.2026")
    telegram_text = _report_text(result)

    assert result["error"] is False
    assert result["metrics"]["commission"] == -69163.97
    assert result["metrics"]["commission_source"] == "POSTING_SALE_COMMISSION"
    assert result["metrics"]["realization_commission_diagnostics"][
        "available"
    ] is False
    assert result["metrics"]["realization_commission_diagnostics"][
        "failure_code"
    ] == "OZON_FINANCE_REALIZATION_COMMISSION_ZERO"
    assert "0.00 ₽ (0,00% от общей выручки)" not in telegram_text
    assert (
        "Комиссия Ozon (предварительно; возвратная не подтверждена)"
        in telegram_text
    )
    assert "OZON_FINANCE_REALIZATION_COMMISSION_ZERO" in telegram_text


def test_realization_sale_only_rows_with_known_returns_keep_commission_preliminary():
    query = _Query()
    query.summary_service = _FinanceBackedCommissionSummary()
    query.summary_service.finance.ozon.get_monthly_realization_report = lambda _year, _month: {
        "error": False,
        "result": {
            "rows": [
                {
                    "order": {"posting_number": "private-order-number"},
                    "delivery_commission": {
                        "commission": 0,
                        "standard_fee": 69193.10,
                    },
                }
            ]
        },
    }
    transactions = _FinanceAccrualPostings()
    transactions.result["posting_accruals"][0]["accruals"] = [
        {"type_id": 69, "accrued": {"amount": "-69159.91"}},
    ]
    runtime = ExperimentalStoreEconomicsRuntimeService(
        query,
        advertising_service=_Advertising(),
        analytics_client=_Analytics(),
        finance_transaction_client=transactions,
    )
    bot, _ = _bot(runtime)

    bot.on_callback("seller-a", "experimental_store_economics:custom")
    result = bot.on_message("seller-a", "01.08.2026 - 31.08.2026")
    telegram_text = _report_text(result)
    diagnostics = result["metrics"]["realization_commission_diagnostics"]

    assert result["metrics"]["analytics"]["returns"] == 1
    assert result["metrics"]["commission"] == -69159.91
    assert result["metrics"]["commission_source"] == "POSTING_SALE_COMMISSION"
    assert diagnostics["available"] is False
    assert diagnostics["failure_code"] == "OZON_FINANCE_REALIZATION_COMMISSION_MISSING"
    assert diagnostics["return_commission_row_count"] == 0
    assert (
        "9. Комиссия Ozon (предварительно; возвратная не подтверждена)"
        in telegram_text
    )
    assert "private-order-number" not in telegram_text


def test_realization_row_without_either_commission_fails_closed_in_telegram():
    query = _Query()
    query.summary_service = _FinanceBackedCommissionSummary()
    query.summary_service.finance.ozon.get_monthly_realization_report = lambda _year, _month: {
        "error": False,
        "result": {
            "rows": [
                {
                    "order": {"posting_number": "private-order-number"},
                    "item": {"name": "private product", "sku": 918273},
                }
            ]
        },
    }
    transactions = _FinanceAccrualPostings()
    transactions.result["posting_accruals"][0]["accruals"] = [
        {"type_id": 69, "accrued": {"amount": "-69159.91"}},
    ]
    runtime = ExperimentalStoreEconomicsRuntimeService(
        query,
        advertising_service=_Advertising(),
        analytics_client=_Analytics(),
        finance_transaction_client=transactions,
    )
    bot, _ = _bot(runtime)

    bot.on_callback("seller-a", "experimental_store_economics:custom")
    result = bot.on_message("seller-a", "01.08.2026 - 31.08.2026")
    telegram_text = _report_text(result)

    assert result["error"] is False
    assert result["metrics"]["commission"] == -69159.91
    assert result["metrics"]["commission_source"] == "POSTING_SALE_COMMISSION"
    assert result["metrics"]["realization_commission_diagnostics"]["available"] is False
    assert (
        result["metrics"]["realization_commission_diagnostics"]["failure_code"]
        == "OZON_FINANCE_REALIZATION_COMMISSION_MISSING"
    )
    assert (
        "Месячный отчёт реализации не подтвердил комиссию "
        "(OZON_FINANCE_REALIZATION_COMMISSION_MISSING); использован источник "
        "POSTING_SALE_COMMISSION, предварительная сумма может не включать "
        "возвратную комиссию."
    ) in telegram_text
    assert "private-order-number" not in telegram_text
    assert "private product" not in telegram_text
    assert "918273" not in telegram_text


def test_realization_http_failure_reaches_telegram_as_safe_commission_diagnostic():
    query = _Query()
    query.summary_service = _FinanceBackedCommissionSummary()
    query.summary_service.finance.ozon.get_monthly_realization_report = lambda _year, _month: {
        "error": True,
        "code": "OZON_HTTP_ERROR",
        "status_code": 404,
        "message": "private Ozon response with seller and order details",
    }
    transactions = _FinanceAccrualPostings()
    transactions.result["posting_accruals"][0]["accruals"] = [
        {"type_id": 69, "accrued": {"amount": "-69159.91"}},
    ]
    runtime = ExperimentalStoreEconomicsRuntimeService(
        query,
        advertising_service=_Advertising(),
        analytics_client=_Analytics(),
        finance_transaction_client=transactions,
    )
    bot, _ = _bot(runtime)

    bot.on_callback("seller-a", "experimental_store_economics:custom")
    result = bot.on_message("seller-a", "01.08.2026 - 31.08.2026")
    telegram_text = _report_text(result)

    assert result["error"] is False
    assert result["metrics"]["commission"] == -69159.91
    assert result["metrics"]["commission_source"] == "POSTING_SALE_COMMISSION"
    assert (
        result["metrics"]["realization_commission_diagnostics"]["failure_code"]
        == "OZON_HTTP_404"
    )
    assert (
        "Месячный отчёт реализации не подтвердил комиссию (OZON_HTTP_404); "
        "использован источник POSTING_SALE_COMMISSION, предварительная сумма "
        "может не включать возвратную комиссию."
    ) in telegram_text
    assert "9. Комиссия Ozon (предварительно; возвратная не подтверждена)" in telegram_text
    assert "Список начислений по отправлениям:" in telegram_text
    assert "private Ozon response with seller and order details" not in telegram_text
    assert "fixture-posting-1" not in telegram_text
    assert "fixture-sku" not in telegram_text


def test_partial_month_without_refund_commission_is_labeled_preliminary():
    query = _Query()
    query.summary_service = _FinanceBackedCommissionSummary()
    realization_calls = []
    query.summary_service.finance.ozon.get_monthly_realization_report = (
        lambda year, month: realization_calls.append((year, month))
    )
    transactions = _FinanceAccrualPostings()
    transactions.result["posting_accruals"][0]["accruals"] = [
        {"type_id": 69, "accrued": {"amount": "-69159.91"}},
    ]
    runtime = ExperimentalStoreEconomicsRuntimeService(
        query,
        advertising_service=_Advertising(),
        analytics_client=_Analytics(),
        finance_transaction_client=transactions,
    )

    result = runtime.calculate("2026-08-01", "2026-08-30")

    assert result["error"] is False
    assert result["metrics"]["commission"] == -69159.91
    assert result["metrics"]["commission_source"] == "POSTING_SALE_COMMISSION"
    assert "9. Комиссия Ozon (предварительно; возвратная не подтверждена)" in _report_text(result)
    assert realization_calls == []


def test_accrual_posting_categories_batch_postings_without_overlap():
    from services.experimental_store_economics_runtime_service import (
        ExperimentalStoreEconomicsRuntimeService,
    )

    class Finance:
        accrual_types = {
            46: {"name": "WarehousePlacement", "description": "Размещение на складе"}
        }

        @staticmethod
        def get_period_posting_numbers(_date_from, _date_to):
            return {
                "error": False,
                "posting_numbers": [f"fixture-{index}" for index in range(205)],
            }

    class Client:
        def __init__(self):
            self.calls = []

        def get_accruals_by_postings(self, posting_numbers):
            self.calls.append(list(posting_numbers))
            return {
                "error": False,
                "posting_accruals": [
                    {"posting_number": value, "accruals": []}
                    for value in posting_numbers
                ],
            }

    client = Client()
    runtime = ExperimentalStoreEconomicsRuntimeService(
        _Query(),
        finance_transaction_client=client,
    )

    result = runtime._load_finance_accrual_posting_categories(
        "2026-08-01",
        "2026-08-31",
        finance_service=Finance(),
    )

    assert sorted(len(batch) for batch in client.calls) == [5, 100, 100]
    assert len({value for batch in client.calls for value in batch}) == 205
    assert result["available"] is True
    assert result["operation_count"] == 0
    assert result["posting_count"] == 205


def test_unmatched_accrual_diagnostic_reaches_telegram_without_raw_identifiers():
    query, runtime = _service()
    bot, _ = _bot(runtime)

    result = bot.on_callback("seller-a", "experimental_store_economics:7D")
    telegram_text = _report_text(result)

    assert "Начисления по отправлениям недоступны (OZON_FINANCE_POSTING_CLIENT_UNAVAILABLE)." in telegram_text
    assert "Справочник типов начислений: 10 типов, явные совпадения комиссии 0, размещения 2." in telegram_text
    assert "9001" not in telegram_text
    assert "501" not in telegram_text


def test_accrual_posting_http_failure_reaches_telegram_without_api_message():
    query = _Query()
    query.summary_service = _FinanceBackedCommissionSummary()
    transactions = _FinanceAccrualPostings(
        {
            "error": True,
            "code": "OZON_HTTP_403",
            "message": "private Ozon response detail",
        }
    )
    runtime = ExperimentalStoreEconomicsRuntimeService(
        query,
        advertising_service=_Advertising(),
        analytics_client=_Analytics(),
        finance_transaction_client=transactions,
    )
    bot, _ = _bot(runtime)

    result = bot.on_callback("seller-a", "experimental_store_economics:7D")
    telegram_text = _report_text(result)

    assert result["metrics"]["accrual_posting_category_diagnostics"]["failure_code"] == "OZON_HTTP_403"
    assert "Начисления по отправлениям недоступны (OZON_HTTP_403)." in telegram_text
    assert "private Ozon response detail" not in telegram_text
    assert "fixture-posting-1" not in telegram_text
    assert "fixture-sku" not in telegram_text
    assert "9. Комиссия Ozon (предварительно; возвратная не подтверждена)" in telegram_text


def test_unconfirmed_expenses_and_unavailable_analytics_are_never_shown_as_zero():
    query = _Query()
    query.summary_service.calculate = lambda date_from, date_to, products: {
        "error": False,
        "status": "PERIOD_PROFIT_SUMMARY_READY",
        "date_from": date_from,
        "date_to": date_to,
        "revenue": 100.0,
        "revenue_tax_base": 90.0,
        "discount_points": 10.0,
        "net_accrual": 17.4,
        "tax": 5.4,
        "profit": 12.0,
        "acquiring": 0.0,
        "commission": 0.0,
        "logistics": 0.0,
        "other_fees": 0.0,
        "products": [],
        "fee_breakdown": {},
    }
    ads = _Advertising({"error": False, "configured": False, "complete": False})
    analytics = _Analytics({"error": True, "code": "OZON_ANALYTICS_DEPENDENCY_UNAVAILABLE"})
    runtime = ExperimentalStoreEconomicsRuntimeService(
        query,
        advertising_service=ads,
        analytics_client=analytics,
    )

    result = runtime.calculate("2026-10-01", "2026-10-02")

    assert result["error"] is False
    assert result["metrics"]["advertising"]["cpc"] is None
    assert result["metrics"]["analytics"]["ordered_units"] is None
    assert result["metrics"]["analytics"]["cancellations"] is None
    assert "Performance CPC для сверки, не входит в сумму: Performance не подключён" in _report_text(result)
    assert "показатель «заказанных единиц» недоступен в Ozon Analytics" in _report_text(result)
    assert "показатель «отменённых единиц» недоступен в Ozon Analytics" in _report_text(result)
    assert "показатель «возвратов» недоступен в Ozon Analytics" in _report_text(result)
    assert "До места выдачи и выдача товара, уже в логистике: нет подтверждённой детализации" in _report_text(result)
    assert "12. Кросс-докинг: нет подтверждённых начислений" in _report_text(result)
    assert "13. Размещение и хранение: нет подтверждённых начислений" in _report_text(result)
    assert "Плату за размещение можно сверить в Ozon Seller → Экономика магазина → Стоимость размещения на складе Ozon → Всего за период." in _report_text(result)


def test_unknown_historical_campaign_count_is_not_rendered_as_zero():
    query, runtime = _service(
        advertising=_Advertising({
            "error": False,
            "configured": True,
            "complete": True,
            "expense": 84467.35,
            "campaign_count": 0,
        })
    )

    result = runtime.calculate("2026-08-01", "2026-08-31")

    assert result["metrics"]["advertising"]["cpc"] == 84467.35
    assert result["metrics"]["advertising"]["campaign_count"] is None
    assert "84 467.35 ₽" in _report_text(result)
    assert "0 камп." not in _report_text(result)


def test_one_missing_analytics_metric_keeps_the_other_and_reaches_telegram():
    query = _Query()
    analytics = _Analytics({
        "error": False,
        "result": {
            "data": [
                {"metrics": [12, None]},
                {"metrics": [5, None]},
            ],
        },
    })
    runtime = ExperimentalStoreEconomicsRuntimeService(
        query,
        advertising_service=_Advertising(),
        analytics_client=analytics,
    )
    bot, _ = _bot(runtime)

    result = bot.on_callback("seller-a", "experimental_store_economics:7D")
    text = TelegramResponseFormatter().format(result)

    assert result["metrics"]["analytics"]["status"] == "PARTIAL"
    assert result["metrics"]["analytics"]["ordered_units"] == 17
    assert result["metrics"]["analytics"]["cancellations"] is None
    assert result["metrics"]["analytics"]["cancellations_status"] == "UNAVAILABLE"
    assert result["metrics"]["analytics"]["cancellations_diagnostic"] == (
        "CANCELLATIONS_VALUE_MISSING"
    )
    assert "Заказанные единицы (Analytics): 17" in text
    assert "Отменённые единицы (Analytics): Ozon Analytics не вернул показатель «отменённых единиц»" in text


def test_analytics_totals_are_used_and_fractional_units_are_preserved():
    query, runtime = _service(
        analytics=_Analytics({
            "error": False,
            "result": {
                "data": [{"metrics": [10, 8]}],
                "totals": [2.5, 1],
            },
        })
    )

    result = runtime.calculate("2026-10-01", "2026-10-02")

    assert result["metrics"]["analytics"]["ordered_units"] == 2.5
    assert result["metrics"]["analytics"]["cancellations"] == 1
    assert "Заказанные единицы (Analytics): 2,5" in _report_text(result)
    assert "Отменённые единицы (Analytics): 1" in _report_text(result)


def test_generic_storage_label_is_not_reported_as_paid_storage():
    result = ExperimentalStoreEconomicsRuntimeService._fee_subcategories(
        {"fee_breakdown": {"Хранение товара": -350.0, "Storage": -125.0}}
    )

    assert result["paid_storage"] is None


def test_ozon_names_for_delivery_to_pickup_and_placement_are_recognized():
    result = ExperimentalStoreEconomicsRuntimeService._fee_subcategories(
        {
            "fee_breakdown": {
                "Доставка до места выдачи партнёрами": -27.5,
                "Выдача товара": -9.0,
                "Стоимость размещения на складе Ozon": -410.0,
                "Услуги FBO → Размещение": -1.74,
            }
        }
    )

    assert result["last_mile"] == -36.5
    assert result["paid_storage"] == -411.74


class _SellerApiFallback(_Analytics):
    def get_fbo_postings(self, **kwargs):
        self.fbo_calls = getattr(self, "fbo_calls", []) + [kwargs]
        return {
            "error": False,
            "result": {
                "postings": [{
                    "posting_number": "fbo-cancel-1",
                    "status": "cancelled",
                    "products": [{"quantity": 2}],
                }]
            },
            "has_next": False,
        }

    def get_fbs_postings(self, **kwargs):
        self.fbs_calls = getattr(self, "fbs_calls", []) + [kwargs]
        return {
            "error": False,
            "postings": [{
                "posting_number": "fbs-cancel-1",
                "status": "cancelled",
                "products": [{"quantity": 3}],
            }],
            "complete": True,
        }

    def get_returns(self, **kwargs):
        self.return_calls = getattr(self, "return_calls", []) + [kwargs]
        rows = ([
            {"id": 12, "type": "ClientReturn", "product": {"quantity": 1}},
            {"id": 13, "type": "Cancellation", "product": {"quantity": 99}},
        ] if kwargs["return_schema"] == "FBO" else [])
        return {"error": False, "returns": rows, "has_next": False}


def test_missing_analytics_cancellations_and_returns_use_complete_seller_api_data():
    query = _Query()
    analytics = _SellerApiFallback({
        "error": False,
        "result": {
            "data": [{"metrics": [17, None, None]}],
        },
    })
    runtime = ExperimentalStoreEconomicsRuntimeService(
        query,
        advertising_service=_Advertising(),
        analytics_client=analytics,
    )
    bot, _ = _bot(runtime)

    result = bot.on_callback(
        "seller-a", "experimental_store_economics:7D"
    )
    telegram_text = _report_text(result)

    assert result["metrics"]["analytics"]["cancellations"] == 5
    assert result["metrics"]["analytics"]["cancellations_source"] == "SELLER_POSTINGS"
    assert result["metrics"]["analytics"]["returns"] == 1
    assert result["metrics"]["analytics"]["returns_source"] == "SELLER_RETURNS"
    assert "17. Отменённые единицы (FBO/FBS, заказы периода): 5 шт. (доля не показана:" in telegram_text
    assert "18. Клиентские возвраты FBO/FBS (тип ClientReturn; статус изменён в периоде): 1 шт. (доля не показана:" in telegram_text
    assert analytics.fbo_calls[0]["status"] == "cancelled"
    assert analytics.fbs_calls[0]["status"] == "cancelled"
    assert {call["return_schema"] for call in analytics.return_calls} == {"FBO", "FBS"}


def test_incomplete_seller_api_fallback_keeps_missing_cancellations_unknown():
    query = _Query()
    analytics = _SellerApiFallback({
        "error": False,
        "result": {"data": [{"metrics": [17, None, None]}]},
    })
    analytics.get_fbo_postings = lambda **_kwargs: {
        "error": False,
        "result": {"postings": [{"status": "cancelled", "products": [{"quantity": 2}]}]},
        "has_next": True,
    }
    runtime = ExperimentalStoreEconomicsRuntimeService(
        query,
        advertising_service=_Advertising(),
        analytics_client=analytics,
    )

    result = runtime.calculate("2026-10-01", "2026-10-02")

    assert result["metrics"]["analytics"]["cancellations"] is None
    assert result["metrics"]["analytics"]["returns"] == 1
    assert "17. Отменённые единицы (Analytics): Ozon Analytics не вернул показатель" in _report_text(result)


def test_analytics_paginates_until_a_short_terminal_page_and_sums_rows():
    class PagedAnalytics:
        def __init__(self):
            self.offsets = []

        def get_analytics_data(self, _date_from, _date_to, **kwargs):
            self.offsets.append(kwargs["offset"])
            if kwargs["offset"] == 0:
                return {
                    "error": False,
                    "result": {
                        "data": [
                            {"metrics": [1, 0, 0]},
                            {"metrics": [2, 0, 1]},
                        ]
                    },
                }
            return {
                "error": False,
                "result": {"data": [{"metrics": [3, 1, 0]}]},
            }

    analytics = PagedAnalytics()
    _query, runtime = _service(analytics=analytics)
    runtime.ANALYTICS_PAGE_SIZE = 2
    runtime.ANALYTICS_MAX_PAGES = 3

    result = runtime._load_analytics("2026-08-01", "2026-08-31")

    assert analytics.offsets == [0, 2]
    assert result["status"] == "READY"
    assert result["ordered_units"] == 6
    assert result["cancellations"] == 1
    assert result["returns"] == 1


def test_analytics_exhausted_page_budget_does_not_publish_partial_totals():
    analytics = _Analytics({
        "error": False,
        "result": {"data": [{"metrics": [1, 0, 0]}, {"metrics": [2, 0, 0]}]},
    })
    offsets = []
    original = analytics.get_analytics_data

    def get_page(date_from, date_to, **kwargs):
        offsets.append(kwargs["offset"])
        return original(date_from, date_to, **kwargs)

    analytics.get_analytics_data = get_page
    _query, runtime = _service(analytics=analytics)
    runtime.ANALYTICS_PAGE_SIZE = 2
    runtime.ANALYTICS_MAX_PAGES = 2

    result = runtime._load_analytics("2026-08-01", "2026-08-31")

    assert offsets == [0, 2]
    assert result["status"] == "INCOMPLETE"
    assert result["ordered_units"] is None
    assert result["ordered_units_diagnostic"] == "ANALYTICS_PAGE_LIMIT_REACHED"


def test_analytics_access_and_rate_limit_failures_have_distinct_diagnostics():
    for response, expected in (
        ({"error": True, "code": "OZON_HTTP_403", "status_code": 403}, "ANALYTICS_ACCESS_DENIED"),
        ({"error": True, "code": "OZON_RATE_LIMITED", "status_code": 429}, "ANALYTICS_RATE_LIMITED"),
    ):
        _query, runtime = _service(analytics=_Analytics(response))
        result = runtime._load_analytics("2026-08-01", "2026-08-31")
        assert result["ordered_units"] is None
        assert result["ordered_units_diagnostic"] == expected


def test_seller_api_duplicate_cancelled_postings_are_counted_once():
    class DuplicatePostingClient:
        def get_fbo_postings(self, **_kwargs):
            posting = {
                "posting_number": "same-fbo-posting",
                "status": "cancelled",
                "products": [{"sku": 11, "quantity": 2}],
            }
            return {
                "error": False,
                "result": {"postings": [posting, dict(posting)]},
                "has_next": False,
            }

        def get_fbs_postings(self, **_kwargs):
            return {"error": False, "postings": [], "complete": True}

    _query, runtime = _service(analytics=DuplicatePostingClient())
    assert runtime._load_cancelled_posting_units("2026-08-01", "2026-08-31") == 2


def test_seller_api_duplicate_return_records_are_counted_once_and_conflicts_fail_closed():
    class DuplicateReturnClient:
        def __init__(self, quantity=1):
            self.quantity = quantity

        def get_returns(self, **kwargs):
            if kwargs["return_schema"] == "FBS":
                return {"error": False, "returns": [], "has_next": False}
            first = {
                "id": 41,
                "type": "ClientReturn",
                "status": "AcceptedFromCustomer",
                "visual_status_change_moment": "2026-08-03T10:00:00Z",
                "product": {"offer_id": "same-product", "quantity": self.quantity},
            }
            duplicate = dict(first)
            duplicate["product"] = {
                "offer_id": "same-product",
                "quantity": self.quantity,
            }
            return {"error": False, "returns": [first, duplicate], "has_next": False}

    _query, runtime = _service(analytics=DuplicateReturnClient())
    assert runtime._load_return_units("2026-08-01", "2026-08-31") == 1

    _query, conflicting_runtime = _service(analytics=DuplicateReturnClient(quantity=2))

    class ConflictingPageClient(DuplicateReturnClient):
        def get_returns(self, **kwargs):
            response = super().get_returns(**kwargs)
            if kwargs["return_schema"] == "FBO":
                response["returns"][1]["product"]["quantity"] = 3
            return response

    conflicting_runtime.analytics_client = ConflictingPageClient()
    assert conflicting_runtime._load_return_units("2026-08-01", "2026-08-31") is None

    class ConflictingProductClient(DuplicateReturnClient):
        def get_returns(self, **kwargs):
            response = super().get_returns(**kwargs)
            if kwargs["return_schema"] == "FBO":
                response["returns"][1]["product"]["offer_id"] = "different-product"
            return response

    _query, conflicting_product_runtime = _service(
        analytics=ConflictingProductClient()
    )
    assert conflicting_product_runtime._load_return_units(
        "2026-08-01", "2026-08-31"
    ) is None


def test_returns_api_diagnostic_is_user_triggered_bounded_and_anonymized():
    class DiagnosticClient(_Analytics):
        def __init__(self):
            super().__init__()
            self.return_calls = []

        def get_returns(self, **kwargs):
            self.return_calls.append(dict(kwargs))
            observer = kwargs.get("request_attempt_observer")
            if callable(observer):
                observer("/v1/returns/list")
            rows = (
                [
                    {
                        "id": 990001,
                        "type": "ClientReturn",
                        "schema": "FBO",
                        "posting_number": "private-posting",
                        "product": {
                            "sku": "private-sku",
                            "offer_id": "private-offer",
                            "name": "private-product-name",
                            "quantity": 2,
                        },
                        "visual": {
                            "change_moment": "2026-08-12T09:10:11Z",
                            "status": {
                                "sys_name": "AcceptedFromCustomer",
                                "display_name": "private-status-label",
                            },
                        },
                    },
                    {
                        "id": 990002,
                        "type": "FullReturn",
                        "schema": "FBO",
                        "product": {"quantity": 1},
                        "visual": {
                            "change_moment": "2026-08-15T09:10:11Z",
                            "status": {"sys_name": "ArrivedAtReturnPlace"},
                        },
                    },
                ]
                if kwargs["return_schema"] == "FBO"
                else []
            )
            return {"error": False, "returns": rows, "has_next": False}

    analytics = DiagnosticClient()
    query, runtime = _service(analytics=analytics)
    runtime.calculate("2026-08-01", "2026-08-31", user_id="seller-a")
    bot, _assistant = _bot(runtime)

    result = bot.on_callback(
        "seller-a", "experimental_returns_api_diagnostic"
    )
    message = result["message"]

    assert result["status"] == "EXPERIMENTAL_RETURNS_API_DIAGNOSTIC_READY"
    assert "API возвратов за 2026-08-01 — 2026-08-31" in message
    assert "FBO: страниц 1, строк API 2, уникальных ID 2 (полностью прочитан)" in message
    assert "ClientReturn: строк 1, quantity 2" in message
    assert "FullReturn: строк 1, quantity 1" in message
    assert "AcceptedFromCustomer: 1" in message
    assert "Фактических HTTP-попыток: 2" in message
    for private_value in (
        "990001",
        "private-posting",
        "private-sku",
        "private-offer",
        "private-product-name",
        "private-status-label",
    ):
        assert private_value not in message
    assert [call["return_schema"] for call in analytics.return_calls] == [
        "FBO",
        "FBS",
    ]
    assert all(call["since"] == "2026-08-01" for call in analytics.return_calls)
    assert all(call["to"] == "2026-08-31" for call in analytics.return_calls)
    assert all(call["limit"] == 500 for call in analytics.return_calls)
    assert all(call["max_attempts"] == 2 for call in analytics.return_calls)
    assert len(query.summary_service.calls) == 1

    foreign_user = bot.on_callback(
        "seller-b", "experimental_returns_api_diagnostic"
    )
    assert foreign_user["status"] == "EXPERIMENTAL_RETURNS_API_DIAGNOSTIC_UNAVAILABLE"
    assert len(analytics.return_calls) == 2


def test_returns_api_diagnostic_stops_at_two_pages_and_marks_partial_result():
    class PagedDiagnosticClient(_Analytics):
        def __init__(self):
            super().__init__()
            self.return_calls = []

        def get_returns(self, **kwargs):
            self.return_calls.append(dict(kwargs))
            observer = kwargs.get("request_attempt_observer")
            if callable(observer):
                observer("/v1/returns/list")
            if kwargs["return_schema"] == "FBS":
                return {"error": False, "returns": [], "has_next": False}
            return {
                "error": False,
                "returns": [
                    {
                        "id": kwargs["last_id"] + 1,
                        "type": "FullReturn",
                        "schema": "FBO",
                        "product": {"quantity": 1},
                    }
                ],
                "has_next": True,
            }

    analytics = PagedDiagnosticClient()
    _query, runtime = _service(analytics=analytics)
    runtime.calculate("2026-08-01", "2026-08-31", user_id="seller-a")

    result = runtime.handle_returns_api_diagnostic(user_id="seller-a")

    assert "FBO: страниц 2, строк API 2, уникальных ID 2 (неполная страница)" in result["message"]
    assert "Полная выборка FBO/FBS: нет; не считайте итог полным." in result["message"]
    fbo_calls = [
        call for call in analytics.return_calls
        if call["return_schema"] == "FBO"
    ]
    assert [call["last_id"] for call in fbo_calls] == [0, 1]
    assert len(analytics.return_calls) == 3


def test_returns_api_diagnostic_keeps_telegram_message_under_limit():
    _query, runtime = _service()
    long_label = "Операция_" + ("x" * 54)
    groups = {
        f"{long_label}{index}": {
            "rows": 999999,
            "quantity": 999999,
            "quantity_missing": 999999,
        }
        for index in range(20)
    }
    states = [
        {
            "schema": schema,
            "page_count": 2,
            "api_row_count": 1000,
            "unique_count": 1000,
            "complete": False,
            "types": groups,
            "statuses": {label: 1000 for label in groups},
            "change_moments": ["2026-08-01T00:00:00Z", "2026-08-31T23:59:59Z"],
        }
        for schema in ("FBO", "FBS")
    ]

    message = runtime._render_returns_api_diagnostic(
        "2026-08-01",
        "2026-08-31",
        states,
        ["id=int", "type=string", "schema=string"],
        8,
        None,
    )

    assert len(message) < 4096
    assert "Полная выборка FBO/FBS: нет" in message
    assert "Фактических HTTP-попыток: 8" in message


def test_analytics_api_diagnostic_is_bounded_anonymized_and_tenant_scoped():
    class DiagnosticClient(_Analytics):
        def __init__(self):
            super().__init__()
            self.analytics_calls = []

        def get_analytics_data(self, date_from, date_to, **kwargs):
            self.analytics_calls.append((date_from, date_to, dict(kwargs)))
            observer = kwargs.get("request_attempt_observer")
            if callable(observer):
                observer("/v1/analytics/data")
            return {
                "error": False,
                "result": {
                    "totals": [5, 1, 1],
                    "data": [
                        {
                            "dimensions": [
                                {
                                    "id": "2026-08-01",
                                    "name": "Private Product Name",
                                }
                            ],
                            "metrics": [2, 1, 0],
                        },
                        {
                            "dimensions": [
                                {
                                    "id": "2026-08-02",
                                    "name": "Private Product Name",
                                }
                            ],
                            "metrics": [3, 0, 1],
                        },
                    ],
                },
            }

    analytics = DiagnosticClient()
    _query, runtime = _service(analytics=analytics)
    runtime.calculate("2026-08-01", "2026-08-31", user_id="seller-a")
    bot, _assistant = _bot(runtime)

    result = bot.on_callback(
        "seller-a", "experimental_analytics_api_diagnostic"
    )
    message = result["message"]

    assert result["status"] == "EXPERIMENTAL_ANALYTICS_API_DIAGNOSTIC_READY"
    assert "Ozon Analytics за 2026-08-01 — 2026-08-31" in message
    assert "Строк дневных данных: 2; выборка до 1000 строк: полная." in message
    assert "ordered_units: totals=5; сумма строк=5." in message
    assert "cancellations: totals=1; сумма строк=1." in message
    assert "returns: totals=1; сумма строк=1." in message
    assert "Даты в строках: 2026-08-01 — 2026-08-02." in message
    assert "HTTP-попыток: 1; максимум 2; одна страница." in message
    assert "Private Product Name" not in message
    diagnostic_call = analytics.analytics_calls[-1]
    assert diagnostic_call[0:2] == ("2026-08-01", "2026-08-31")
    assert diagnostic_call[2]["metrics"] == [
        "ordered_units",
        "cancellations",
        "returns",
    ]
    assert diagnostic_call[2]["dimension"] == ["day"]
    assert diagnostic_call[2]["limit"] == 1000
    assert diagnostic_call[2]["offset"] == 0
    assert diagnostic_call[2]["max_attempts"] == 2

    foreign_user = bot.on_callback(
        "seller-b", "experimental_analytics_api_diagnostic"
    )
    assert (
        foreign_user["status"]
        == "EXPERIMENTAL_ANALYTICS_API_DIAGNOSTIC_UNAVAILABLE"
    )
    assert len(analytics.analytics_calls) == 2


def test_analytics_api_diagnostic_does_not_treat_missing_metrics_as_zero():
    class MissingMetricsClient:
        def get_analytics_data(self, _date_from, _date_to, **kwargs):
            observer = kwargs.get("request_attempt_observer")
            if callable(observer):
                observer("/v1/analytics/data")
            return {
                "error": False,
                "result": {
                    "totals": [6117, None, None],
                    "data": [
                        {
                            "dimensions": [{"id": "2026-08-01"}],
                            "metrics": [6117, None, None],
                        }
                    ],
                },
            }

    _query, runtime = _service(analytics=MissingMetricsClient())
    runtime._save_report_views(
        "seller-a",
        "summary",
        "details",
        date_from="2026-08-01",
        date_to="2026-08-31",
    )

    result = runtime.handle_analytics_api_diagnostic(user_id="seller-a")

    assert "ordered_units: totals=6117; сумма строк=6117." in result["message"]
    assert (
        "cancellations: totals=нет в totals; "
        "сумма строк=неполная (1 строк без значения)."
    ) in result["message"]
    assert (
        "returns: totals=нет в totals; "
        "сумма строк=неполная (1 строк без значения)."
    ) in result["message"]
    assert "cancellations: totals=0" not in result["message"]


def test_custom_period_is_user_scoped_and_traverses_telegram_to_result():
    query, runtime = _service()
    bot, assistant = _bot(runtime)

    experiments = bot.on_callback("seller-a", "experimental_calculations")
    period_menu = bot.on_callback(
        "seller-a",
        experiments["keyboard"]["buttons"][0]["callback"],
    )
    prompt = bot.on_callback(
        "seller-a",
        "experimental_store_economics:custom",
    )
    other_user_text = bot.on_message("seller-b", "01.10.2026 - 02.10.2026")
    result = bot.on_message("seller-a", "01.10.2026 - 02.10.2026")

    assert period_menu["error"] is False
    assert prompt["status"] == "EXPERIMENTAL_STORE_ECONOMICS_CUSTOM_PERIOD_INPUT_REQUIRED"
    assert other_user_text["message"] == "unused assistant"
    assert result["error"] is False
    assert result["status"] == "EXPERIMENTAL_STORE_ECONOMICS_READY"
    assert result["date_from"] == "2026-10-01"
    assert result["date_to"] == "2026-10-02"
    assert "Экономика магазина за период 2026-10-01 — 2026-10-02" in _report_text(result)
    assert TelegramResponseFormatter().format(result) == result["text"]
    assert result["read_only"] is True
    assert result["executed"] is False
    assert [button["callback"] for button in result["keyboard"]["buttons"]] == [
        "experimental_analytics_api_diagnostic:" + result["report_view_id"],
        "experimental_returns_api_diagnostic:" + result["report_view_id"],
        "experimental_store_economics_details:" + result["report_view_id"],
        "experimental_calculations",
        "main_menu",
    ]
    assert all(
        "Выбрать другой период" not in button["text"]
        for button in result["keyboard"]["buttons"]
    )
    assert assistant.calls == [("01.10.2026 - 02.10.2026", "seller-b")]
    assert query.summary_service.calls[0][:2] == ("2026-10-01", "2026-10-02")

    foreign_details = bot.on_callback(
        "seller-b", "experimental_store_economics_details"
    )
    assert foreign_details["status"] == "EXPERIMENTAL_STORE_ECONOMICS_VIEW_EXPIRED"

    details = bot.on_callback(
        "seller-a", "experimental_store_economics_details"
    )
    assert details["status"] == "EXPERIMENTAL_STORE_ECONOMICS_DETAILS_READY"
    assert "Подробности экономики магазина" in TelegramResponseFormatter().format(details)
    assert [button["callback"] for button in details["keyboard"]["buttons"]][0] == (
        "experimental_store_economics_summary:" + result["report_view_id"]
    )
    summary = bot.on_callback(
        "seller-a", "experimental_store_economics_summary"
    )
    assert TelegramResponseFormatter().format(summary) == result["text"]
    assert len(query.summary_service.calls) == 1
    assert len(runtime.analytics_client.calls) == 1


def test_duplicate_custom_period_text_does_not_start_two_economics_calculations():
    query, runtime = _service()
    original_calculate = query.summary_service.calculate
    started = Event()
    release = Event()

    def blocking_calculate(date_from, date_to, products):
        started.set()
        if not release.wait(timeout=3):
            raise TimeoutError("test calculation was not released")
        return original_calculate(date_from, date_to, products)

    query.summary_service.calculate = blocking_calculate
    runtime.begin_custom_period("seller-a")

    with ThreadPoolExecutor(max_workers=1) as pool:
        first = pool.submit(
            runtime.handle_text,
            "01.10.2026 - 02.10.2026",
            user_id="seller-a",
        )
        assert started.wait(timeout=1)

        duplicate = runtime.handle_text(
            "01.10.2026 - 02.10.2026",
            user_id="seller-a",
        )
        assert duplicate["status"] == "EXPERIMENTAL_STORE_ECONOMICS_ALREADY_RUNNING"
        assert len(query.summary_service.calls) == 0

        release.set()
        result = first.result(timeout=2)

    assert result["status"] == "EXPERIMENTAL_STORE_ECONOMICS_READY"
    assert len(query.summary_service.calls) == 1
    assert not runtime._calculation_inflight


def test_parallel_period_results_keep_their_own_details_and_diagnostic_scope():
    query, runtime = _service()
    original_calculate = query.summary_service.calculate
    older_started = Event()
    newer_started = Event()
    release_older = Event()
    release_newer = Event()

    def blocking_calculate(date_from, date_to, products):
        if date_from == "2026-10-01":
            older_started.set()
            if not release_older.wait(timeout=3):
                raise TimeoutError("older test calculation was not released")
        elif date_from == "2026-10-03":
            newer_started.set()
            if not release_newer.wait(timeout=3):
                raise TimeoutError("newer test calculation was not released")
        return original_calculate(date_from, date_to, products)

    query.summary_service.calculate = blocking_calculate
    bot, _ = _bot(runtime)

    with ThreadPoolExecutor(max_workers=2) as pool:
        runtime.begin_custom_period("seller-a")
        older = pool.submit(
            runtime.handle_text,
            "01.10.2026 - 02.10.2026",
            user_id="seller-a",
        )
        assert older_started.wait(timeout=1)

        runtime.begin_custom_period("seller-a")
        newer = pool.submit(
            runtime.handle_text,
            "03.10.2026 - 04.10.2026",
            user_id="seller-a",
        )
        assert newer_started.wait(timeout=1)

        release_newer.set()
        newer_result = newer.result(timeout=2)
        release_older.set()
        older_result = older.result(timeout=2)

    assert newer_result["report_view_id"] != older_result["report_view_id"]
    old_id = older_result["report_view_id"]
    new_id = newer_result["report_view_id"]

    old_details = bot.on_callback(
        "seller-a", "experimental_store_economics_details:" + old_id
    )
    new_details = bot.on_callback(
        "seller-a", "experimental_store_economics_details:" + new_id
    )
    assert "2026-10-01 — 2026-10-02" in old_details["message"]
    assert "2026-10-03 — 2026-10-04" in new_details["message"]
    assert new_details["keyboard"]["buttons"][0]["callback"] == (
        "experimental_store_economics_summary:" + new_id
    )

    old_analytics = bot.on_callback(
        "seller-a", "experimental_analytics_api_diagnostic:" + old_id
    )
    assert "2026-10-01 — 2026-10-02" in old_analytics["message"]
    assert old_analytics["report_view_id"] == old_id


def test_invalid_analytics_metric_does_not_discard_a_valid_other_metric():
    query = _Query()
    analytics = _Analytics({
        "error": False,
        "result": {"data": [{"metrics": [10, "not-a-number"]}]},
    })
    runtime = ExperimentalStoreEconomicsRuntimeService(
        query,
        advertising_service=_Advertising(),
        analytics_client=analytics,
    )

    result = runtime.calculate("2026-10-01", "2026-10-02")

    analytics_result = result["metrics"]["analytics"]
    assert analytics_result["status"] == "PARTIAL"
    assert analytics_result["ordered_units"] == 10
    assert analytics_result["cancellations"] is None
    assert analytics_result["cancellations_diagnostic"] == (
        "CANCELLATIONS_VALUE_INVALID"
    )
    assert "Заказанные единицы (Analytics): 10" in _report_text(result)
    assert "Отменённые единицы (Analytics): данные по показателю «отменённых единиц» не прошли проверку" in _report_text(result)


def test_expense_categories_partition_balance_without_readding_nested_amounts():
    query = _Query()
    query.summary_service.calculate = lambda date_from, date_to, _products: {
        "error": False,
        "status": "PERIOD_PROFIT_SUMMARY_READY",
        "date_from": date_from,
        "date_to": date_to,
        "revenue": 10000.0,
        "revenue_tax_base": 8000.0,
        "discount_points": 2000.0,
        "net_accrual": 5000.0,
        "tax": 480.0,
        "profit": 4520.0,
        "acquiring": -100.0,
        "commission": -200.0,
        "logistics": -300.0,
        "other_fees": -4400.0,
        "products": [],
        "fee_breakdown": {
            "Эквайринг": -100.0,
            "Вознаграждение за продажу": -200.0,
            "Логистика доставки": -300.0,
            "Доставка до места выдачи": -75.0,
            "PayPerClick CPC": -100.0,
            "Оплата за заказ CPO": -200.0,
            "Оплата за показ CPM": -300.0,
            "Услуги продвижения": -50.0,
            "Обратная логистика": -250.0,
            "Услуги кросс-докинга": -150.0,
            "Платное хранение": -50.0,
            "Услуги комплектации": -100.0,
        },
    }
    runtime = ExperimentalStoreEconomicsRuntimeService(
        query,
        advertising_service=_Advertising(),
        analytics_client=_Analytics(),
    )

    result = runtime.calculate("2026-08-01", "2026-08-31")
    breakdown = result["metrics"]["expense_breakdown"]
    categories = breakdown["categories"]
    assert categories["advertising"]["CPC"]["amount"] == -100.0
    assert categories["advertising"]["CPO"]["amount"] == -200.0
    assert categories["advertising"]["CPM"]["amount"] == -300.0
    assert categories["advertising"]["OTHER"]["amount"] == -50.0
    assert categories["reverse_logistics"]["amount"] == -250.0
    assert categories["cross_docking"]["amount"] == -150.0
    assert categories["paid_storage"]["amount"] == -50.0
    assert categories["other_services"]["amount"] == -100.0
    assert breakdown["last_mile"]["amount"] == -75.0
    assert breakdown["last_mile"]["included_in"] == "logistics"
    assert breakdown["last_mile"]["additive"] is False
    assert "Performance CPC для сверки, не входит в сумму" in result["text"]
    assert round(
        result["metrics"]["revenue"]
        + result["metrics"]["acquiring"]
        + result["metrics"]["commission"]
        + result["metrics"]["logistics"]
        + breakdown["classified_other_fees"]
        + breakdown["unallocated_adjustment"]["amount"],
        2,
    ) == result["metrics"]["net_accrual"]
    assert result["metrics"]["other_fees"] == -4400.0


def test_authoritative_storage_subtotal_preserves_by_day_labels_as_nonadditive_references():
    metrics = {
        "fee_breakdown": [
            {"label": "Плата за вынужденное размещение на складе", "amount": -350.0}
        ],
        "fee_subcategories": {"paid_storage": -1.74},
        "accrual_posting_category_diagnostics": {
            "available": True,
            "paid_storage": -1.74,
        },
        "revenue": 1000.0,
        "net_accrual": -1.74,
        "acquiring": 0.0,
        "commission": 0.0,
        "logistics": 0.0,
        "other_fees": -1.74,
    }

    breakdown = ExperimentalStoreEconomicsRuntimeService._build_expense_breakdown(
        metrics, "2026-08-01", "2026-08-31"
    )
    metrics["expense_breakdown"] = breakdown
    details_text = ExperimentalStoreEconomicsRuntimeService._render_details(
        "2026-08-01",
        "2026-08-31",
        metrics,
    )

    reference = next(
        item
        for item in breakdown["details"]
        if item["label"] == "Плата за вынужденное размещение на складе"
    )
    assert reference["category"] == "paid_storage_reference"
    assert reference["amount"] == -350.0
    assert reference["additive"] is False
    assert breakdown["categories"]["paid_storage"]["amount"] == -1.74
    assert breakdown["classified_other_fees"] == -1.74
    assert "справочная сумма другого источника, не складывается повторно" in details_text


def test_small_shares_and_nonpositive_revenue_are_not_misleading():
    from services.experimental_store_economics_runtime_service import (
        _money_with_revenue_share,
    )

    assert "<0,01% расход" in _money_with_revenue_share(-0.01, 1000000)
    assert "<0,01% доход" in _money_with_revenue_share(0.01, 1000000)
    assert "доля не определена: выручка ≤ 0" in _money_with_revenue_share(-1, 0)


def test_event_share_is_hidden_until_period_cohort_is_confirmed():
    from services.experimental_store_economics_runtime_service import (
        _period_event_units,
    )

    incompatible = _period_event_units(1, 10, False, "дата статуса отличается")
    compatible = _period_event_units(1, 10, True, "unused")

    assert "1 шт. (доля не показана: дата статуса отличается)" == incompatible
    assert compatible == "1 шт. (10,00% от заказанных единиц)"


def test_report_view_cache_isolated_by_tenant_store_scope():
    from services.tenant_context import (
        reset_current_tenant_user_id,
        set_current_tenant_user_id,
    )

    _query, runtime = _service()
    token = set_current_tenant_user_id("seller-a:store-a")
    try:
        runtime._save_report_views("seller-a", "store A summary", "store A details")
    finally:
        reset_current_tenant_user_id(token)

    token = set_current_tenant_user_id("seller-a:store-b")
    try:
        result = runtime.handle_details("seller-a")
    finally:
        reset_current_tenant_user_id(token)

    assert result["status"] == "EXPERIMENTAL_STORE_ECONOMICS_VIEW_EXPIRED"
    assert "store A" not in result["message"]

