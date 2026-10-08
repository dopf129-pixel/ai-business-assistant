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
    assert (
        "Диагностика разбивки (/v1/finance/accrual/by-day и "
        "/v1/finance/accrual/postings): типов начислений 10, "
        "совпадений комиссии 0, размещения 2; "
        "источник начислений по отправлениям недоступен "
        "(OZON_FINANCE_POSTING_CLIENT_UNAVAILABLE), "
        "отправлений 0, строк начислений 0, строк комиссии 0, строк размещения 0."
    ) in result["text"]
    diagnostic_line = next(
        line for line in result["text"].splitlines()
        if line.startswith("Диагностика разбивки (")
    )
    assert "9001" not in diagnostic_line
    assert "501" not in diagnostic_line
    assert "1. Выручка общая (100%): 100 000.00 ₽" in result["text"]
    assert "2. Выручка ФНС (выручка − баллы): 92 000.00 ₽ (92,00% от общей выручки)" in result["text"]
    assert "3. Баллы за скидки: 8 000.00 ₽ (8,00% от общей выручки)" in result["text"]
    assert "4. Начисления Ozon нетто: 18 520.00 ₽ (18,52% от общей выручки)" in result["text"]
    assert "5. Налог: 5 520.00 ₽ (5,52% от общей выручки)" in result["text"]
    assert "6. Прибыль без себестоимости: 13 000.00 ₽ (13,00% от общей выручки)" in result["text"]
    assert "7. Расходы на рекламу:" in result["text"]
    assert "По начислениям Ozon, CPC: -3 000.00 ₽ (-3,00% от общей выручки)" in result["text"]
    assert "По начислениям Ozon, CPO: -400.00 ₽ (-0,40% от общей выручки)" in result["text"]
    assert "Performance CPC по сопоставленным SKU (для сверки): 345.67 ₽ (0,35% от общей выручки) (2 камп.)" in result["text"]
    assert "8. Эквайринг: -1 500.00 ₽ (-1,50% от общей выручки)" in result["text"]
    assert "9. Комиссия Ozon (предварительно; возвратная комиссия не подтверждена): -22 000.00 ₽ (-22,00% от общей выручки)" in result["text"]
    assert "10. Логистика доставки (без обратной логистики): -18 000.00 ₽ (-18,00% от общей выручки)" in result["text"]
    assert "11. Доставка до места выдачи и выдача товара (части «последней мили»): -8 500.00 ₽ (-8,50% от общей выручки)" in result["text"]
    assert "12. Кросс-докинг: -1 200.00 ₽ (-1,20% от общей выручки)" in result["text"]
    assert "13. Стоимость размещения на складе Ozon: -351.74 ₽ (-0,35% от общей выручки)" in result["text"]
    assert "14. Остаток начислений Ozon после основных категорий: -3 600.00 ₽ (-3,60% от общей выручки)" in result["text"]
    assert "Строка 14 — расчётный остаток начислений нетто после выручки, эквайринга, комиссии и логистики доставки." in result["text"]
    assert "Это не дополнительная сумма к вычитанию" in result["text"]
    assert "Тип Ozon «Обратная логистика»: -4 482.24 ₽ (-4,48% от общей выручки)" in result["text"]
    assert "Тип Ozon «Обработка товара»: -1 650.00 ₽ (-1,65% от общей выручки)" in result["text"]
    assert "группы типов Ozon могут объединять несколько операций из XLSX" in result["text"]
    assert "15. Заказанные единицы (Analytics): 17 шт. (100% базы для долей)" in result["text"]
    assert "16. Отменённые единицы (Analytics): 3 шт. (17,65% от заказанных единиц)" in result["text"]
    assert "17. Возвраты (Analytics): 1 шт. (5,88% от заказанных единиц)" in result["text"]
    assert "Для количества показана доля от заказанных единиц" in result["text"]
    assert "Performance CPC показан для сверки и может пересекаться" in result["text"]
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
    telegram_text = TelegramResponseFormatter().format(result)

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
    assert "9. Комиссия Ozon (вознаграждение за продажу): -69 167.90 ₽ (-14,12% от общей выручки)" in telegram_text
    assert "13. Стоимость размещения на складе Ozon: -1.74 ₽" in telegram_text
    assert "14. Остаток начислений Ozon после основных категорий: -105 966.58 ₽ (-21,64% от общей выручки)" in telegram_text
    assert "Тип Ozon «Вознаграждение за продажу»" not in telegram_text
    assert "Комиссия за полные календарные месяцы берётся из отчёта реализации (/v1/finance/realization/posting)" in telegram_text
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
    telegram_text = TelegramResponseFormatter().format(result)

    assert result["metrics"]["commission"] == -69167.90
    assert result["metrics"]["other_fees"] == -105966.58
    assert "9. Комиссия Ozon (вознаграждение за продажу): -69 167.90 ₽" in telegram_text
    assert "13. Стоимость размещения на складе Ozon: -1.74 ₽" in telegram_text
    assert "14. Остаток начислений Ozon после основных категорий: -105 966.58 ₽" in telegram_text
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
        "Диагностика начислений (/v1/finance/accrual/postings): отправлений 1, "
        "строк начислений 5, комиссия: продажа — операций 1, -69 193.10 ₽; "
        "возврат — операций 1, 25.20 ₽; прочие явные типы — операций 0, "
        "0.00 ₽; без типа в справочнике — операций 0, 0.00 ₽; "
        "размещение — операций 3, -1.74 ₽."
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
    telegram_text = TelegramResponseFormatter().format(result)

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
        "Диагностика начислений (/v1/finance/accrual/postings): отправлений 1, "
        "строк начислений 6, комиссия: продажа — операций 1, -69 185.11 ₽; "
        "возврат — операций 1, 25.20 ₽; прочие явные типы — операций 0, "
        "0.00 ₽; без типа в справочнике — операций 1, -7.99 ₽; "
        "размещение — операций 3, -1.74 ₽."
    ) in telegram_text
    assert "fixture-posting-1" not in telegram_text
    assert "fixture-sku" not in telegram_text
    assert "private" not in telegram_text


def test_full_month_realization_commission_reaches_telegram_with_sales_and_returns():
    query = _Query()
    query.summary_service = _FinanceBackedCommissionSummary()
    realization_calls = []

    def get_realization_posting(year, month):
        realization_calls.append((year, month))
        return {
            "error": False,
            "result": {
                "rows": [
                    {
                        "order": {"posting_number": "private-order-number"},
                        "item": {"name": "private product", "sku": 918273},
                        "delivery_commission": {"commission": "-69193.10"},
                        "return_commission": {"commission": "25.20"},
                    }
                ]
            },
        }

    query.summary_service.finance.ozon.get_realization_posting = (
        get_realization_posting
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
    telegram_text = TelegramResponseFormatter().format(result)

    assert result["error"] is False
    assert result["metrics"]["commission"] == -69167.90
    assert result["metrics"]["other_fees"] == -105966.58
    assert result["metrics"]["commission_source"] == "FINANCE_REALIZATION_POSTING"
    assert result["metrics"]["realization_commission_diagnostics"] == {
        "available": True,
        "failure_code": None,
        "month_count": 1,
        "row_count": 1,
        "delivery_commission_missing_row_count": 0,
        "return_commission_missing_row_count": 0,
        "sale_operation_count": 1,
        "sale_commission_amount": -69193.10,
        "return_operation_count": 1,
        "return_commission_amount": 25.20,
        "commission": -69167.90,
    }
    assert "9. Комиссия Ozon (отчёт о реализации): -69 167.90 ₽" in telegram_text
    assert "14. Остаток начислений Ozon после основных категорий: -105 966.58 ₽" in telegram_text
    assert "Диагностика комиссии (/v1/finance/realization/posting)" in telegram_text
    assert realization_calls == [(2026, 8)]
    assert "private-order-number" not in telegram_text
    assert "private product" not in telegram_text
    assert "918273" not in telegram_text


def test_full_month_realization_commission_sums_sparse_sale_and_return_rows_to_telegram():
    query = _Query()
    query.summary_service = _FinanceBackedCommissionSummary()
    realization_calls = []

    def get_realization_posting(year, month):
        realization_calls.append((year, month))
        return {
            "error": False,
            "result": {
                "rows": [
                    {
                        "order": {"posting_number": "private-sale-order"},
                        "delivery_commission": {"commission": "-69193.10"},
                    },
                    {
                        "order": {"posting_number": "private-return-order"},
                        "item": {"name": "private product", "sku": 918273},
                        "return_commission": {"commission": "25.20"},
                    },
                ]
            },
        }

    query.summary_service.finance.ozon.get_realization_posting = (
        get_realization_posting
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
    telegram_text = TelegramResponseFormatter().format(result)
    diagnostics = result["metrics"]["realization_commission_diagnostics"]

    assert result["error"] is False
    assert result["metrics"]["commission"] == -69167.90
    assert result["metrics"]["other_fees"] == -105966.58
    assert result["metrics"]["commission_source"] == "FINANCE_REALIZATION_POSTING"
    assert diagnostics["available"] is True
    assert diagnostics["row_count"] == 2
    assert diagnostics["delivery_commission_missing_row_count"] == 1
    assert diagnostics["return_commission_missing_row_count"] == 1
    assert diagnostics["sale_operation_count"] == 1
    assert diagnostics["sale_commission_amount"] == -69193.10
    assert diagnostics["return_operation_count"] == 1
    assert diagnostics["return_commission_amount"] == 25.20
    assert diagnostics["commission"] == -69167.90
    assert "9. Комиссия Ozon (отчёт о реализации): -69 167.90 ₽" in telegram_text
    assert "14. Остаток начислений Ozon после основных категорий: -105 966.58 ₽" in telegram_text
    assert (
        "строк 2 (без комиссии продажи: 1, без комиссии возврата: 1)"
        in telegram_text
    )
    assert realization_calls == [(2026, 8)]
    assert "private-sale-order" not in telegram_text
    assert "private-return-order" not in telegram_text
    assert "private product" not in telegram_text
    assert "918273" not in telegram_text


def test_realization_row_without_either_commission_fails_closed_in_telegram():
    query = _Query()
    query.summary_service = _FinanceBackedCommissionSummary()
    query.summary_service.finance.ozon.get_realization_posting = lambda _year, _month: {
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
    telegram_text = TelegramResponseFormatter().format(result)

    assert result["error"] is False
    assert result["metrics"]["commission"] == -69159.91
    assert result["metrics"]["commission_source"] == "POSTING_SALE_COMMISSION"
    assert result["metrics"]["realization_commission_diagnostics"]["available"] is False
    assert (
        result["metrics"]["realization_commission_diagnostics"]["failure_code"]
        == "OZON_FINANCE_REALIZATION_COMMISSION_MISSING"
    )
    assert (
        "источник недоступен (OZON_FINANCE_REALIZATION_COMMISSION_MISSING); "
        "использован предварительный источник по отправлениям."
    ) in telegram_text
    assert "private-order-number" not in telegram_text
    assert "private product" not in telegram_text
    assert "918273" not in telegram_text


def test_realization_http_failure_reaches_telegram_as_safe_commission_diagnostic():
    query = _Query()
    query.summary_service = _FinanceBackedCommissionSummary()
    query.summary_service.finance.ozon.get_realization_posting = lambda _year, _month: {
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
    telegram_text = TelegramResponseFormatter().format(result)

    assert result["error"] is False
    assert result["metrics"]["commission"] == -69159.91
    assert result["metrics"]["commission_source"] == "POSTING_SALE_COMMISSION"
    assert (
        result["metrics"]["realization_commission_diagnostics"]["failure_code"]
        == "OZON_HTTP_404"
    )
    assert (
        "Диагностика комиссии (/v1/finance/realization/posting): "
        "источник недоступен (OZON_HTTP_404); "
        "использован предварительный источник по отправлениям."
    ) in telegram_text
    assert "9. Комиссия Ozon (предварительно; возвратная комиссия не подтверждена)" in telegram_text
    assert "Диагностика начислений (/v1/finance/accrual/postings)" in telegram_text
    assert "private Ozon response with seller and order details" not in telegram_text
    assert "fixture-posting-1" not in telegram_text
    assert "fixture-sku" not in telegram_text


def test_partial_month_without_refund_commission_is_labeled_preliminary():
    query = _Query()
    query.summary_service = _FinanceBackedCommissionSummary()
    realization_calls = []
    query.summary_service.finance.ozon.get_realization_posting = (
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
    assert "9. Комиссия Ozon (предварительно; возвратная комиссия не подтверждена)" in result["text"]
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
    telegram_text = TelegramResponseFormatter().format(result)

    expected = (
        "Диагностика разбивки (/v1/finance/accrual/by-day и "
        "/v1/finance/accrual/postings): типов начислений 10, "
        "совпадений комиссии 0, размещения 2; "
        "источник начислений по отправлениям недоступен "
        "(OZON_FINANCE_POSTING_CLIENT_UNAVAILABLE), "
        "отправлений 0, строк начислений 0, строк комиссии 0, строк размещения 0."
    )
    assert expected in telegram_text
    diagnostic_line = next(
        line for line in telegram_text.splitlines()
        if line.startswith("Диагностика разбивки (")
    )
    assert "9001" not in diagnostic_line
    assert "501" not in diagnostic_line


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
    telegram_text = TelegramResponseFormatter().format(result)

    assert result["metrics"]["accrual_posting_category_diagnostics"]["failure_code"] == "OZON_HTTP_403"
    assert "источник начислений по отправлениям недоступен (OZON_HTTP_403)" in telegram_text
    assert "private Ozon response detail" not in telegram_text
    assert "fixture-posting-1" not in telegram_text
    assert "fixture-sku" not in telegram_text
    assert "9. Комиссия Ozon (предварительно; возвратная комиссия не подтверждена)" in telegram_text


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
    assert "Performance CPC по сопоставленным SKU (для сверки): Performance не подключён" in result["text"]
    assert "показатель «заказанных единиц» недоступен в Ozon Analytics" in result["text"]
    assert "показатель «отменённых единиц» недоступен в Ozon Analytics" in result["text"]
    assert "показатель «возвратов» недоступен в Ozon Analytics" in result["text"]
    assert "Доставка до места выдачи и выдача товара (части «последней мили»): не найдено начисление с однозначной подписью" in result["text"]
    assert "Кросс-докинг: не найдено начисление с однозначной подписью" in result["text"]
    assert "Стоимость размещения на складе Ozon: не найдено начисление с однозначной подписью" in result["text"]
    assert "проверьте Ozon Seller → Экономика магазина → Стоимость размещения на складе Ozon → Всего за период" in result["text"]


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
    assert "84 467.35 ₽" in result["text"]
    assert "0 камп." not in result["text"]


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
    assert "Заказанные единицы (Analytics): 2,5" in result["text"]
    assert "Отменённые единицы (Analytics): 1" in result["text"]


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
    telegram_text = TelegramResponseFormatter().format(result)

    assert result["metrics"]["analytics"]["cancellations"] == 5
    assert result["metrics"]["analytics"]["cancellations_source"] == "SELLER_POSTINGS"
    assert result["metrics"]["analytics"]["returns"] == 1
    assert result["metrics"]["analytics"]["returns_source"] == "SELLER_RETURNS"
    assert "16. Отменённые единицы (FBO/FBS, заказы периода): 5 шт. (29,41% от заказанных единиц)" in telegram_text
    assert "17. Возвраты (FBO/FBS, статус изменён в периоде): 1 шт. (5,88% от заказанных единиц)" in telegram_text
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
    assert "16. Отменённые единицы (Analytics): Ozon Analytics не вернул показатель" in result["text"]


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
    assert "Экономика магазина за период 2026-10-01 — 2026-10-02" in result["text"]
    assert TelegramResponseFormatter().format(result) == result["text"]
    assert result["read_only"] is True
    assert result["executed"] is False
    assert [button["callback"] for button in result["keyboard"]["buttons"]] == [
        "experimental_calculations",
        "main_menu",
    ]
    assert all(
        "Выбрать другой период" not in button["text"]
        for button in result["keyboard"]["buttons"]
    )
    assert assistant.calls == [("01.10.2026 - 02.10.2026", "seller-b")]
    assert query.summary_service.calls[0][:2] == ("2026-10-01", "2026-10-02")


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
    assert "Заказанные единицы (Analytics): 10" in result["text"]
    assert "Отменённые единицы (Analytics): данные по показателю «отменённых единиц» не прошли проверку" in result["text"]

