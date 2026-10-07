from services.finance_service import FinanceService


def test_period_posting_numbers_collects_unique_posting_rows_only():
    service = FinanceService()
    service._get_accruals_by_day = lambda day: {
        "error": False,
        "accruals": [
            {
                "accrued_category": "POSTING",
                "unit_number": "fixture-posting-2",
            },
            {
                "accrued_category": "POSTING",
                "unit_number": "fixture-posting-1",
            },
            {
                "accrued_category": "POSTING",
                "unit_number": "fixture-posting-2",
            },
            {
                "accrued_category": "NON_ITEM",
                "unit_number": "fixture-service-unit",
            },
        ],
    }

    result = service.get_period_posting_numbers("2026-08-01", "2026-08-02")

    assert result == {
        "error": False,
        "posting_numbers": ["fixture-posting-1", "fixture-posting-2"],
        "posting_count": 2,
    }


def test_period_posting_numbers_fails_closed_on_posting_without_unit_number():
    service = FinanceService()
    service._get_accruals_by_day = lambda _day: {
        "error": False,
        "accruals": [{"accrued_category": "POSTING"}],
    }

    result = service.get_period_posting_numbers("2026-08-01", "2026-08-01")

    assert result == {
        "error": True,
        "code": "OZON_FINANCE_POSTING_NUMBERS_INVALID",
    }


def test_account_finance_breakdown_includes_non_item_and_container_fees_once():
    service = FinanceService()
    service.accrual_types = {
        41: {"name": "PayPerClick", "description": "Оплата за клик CPC"},
        46: {"name": "PaidStorage", "description": "Платное хранение"},
    }
    service._get_accruals_by_day = lambda _day: {
        "error": False,
        "accruals": [
            {
                "accrued_category": "NON_ITEM",
                "total_amount": {"amount": "-100.00"},
                "non_item_fee": {
                    "type_id": 41,
                    "accrued": {"amount": "-100.00"},
                },
            },
            {
                "accrued_category": "UNSPECIFIED",
                "total_amount": {"amount": "-25.00"},
                "container_fees": {
                    "fees": [
                        {
                            "type_id": 46,
                            "accrued": {"amount": "-25.00"},
                        }
                    ]
                },
            },
        ],
    }

    result = service.get_daily_account_finance("2026-08-01")

    assert result["error"] is False
    assert result["net_accrual"] == -125.0
    assert result["other_fees"] == -125.0
    assert result["fee_breakdown"] == {
        "Оплата за клик CPC": -100.0,
        "Платное хранение": -25.0,
    }


def test_account_finance_breakdown_preserves_explicit_commission_operation_types():
    service = FinanceService()
    service.accrual_types = {
        501: {
            "name": "SaleCommission",
            "description": "Вознаграждение за продажу",
        },
        502: {
            "name": "CommissionRefund",
            "description": "Возврат вознаграждения",
        },
    }
    service._get_accruals_by_day = lambda _day: {
        "error": False,
        "accruals": [
            {
                "accrued_category": "POSTING",
                "total_amount": {"amount": "50.00"},
                "posting": {
                    "products": [
                        {
                            "sku": "fixture-sku",
                            "commission": {
                                "sale_amount": {"amount": "100.00"},
                                "sale_commission": {"amount": "-69163.97"},
                            },
                        }
                    ]
                },
                "item_fees": {
                    "fees": [
                        {
                            "sku": "fixture-sku",
                            "fees": [
                                {
                                    "type_id": 501,
                                    "accrued": {"amount": "-69193.10"},
                                }
                            ],
                        }
                    ]
                },
            },
            {
                "accrued_category": "NON_ITEM",
                "total_amount": {"amount": "25.20"},
                "non_item_fee": {
                    "type_id": 502,
                    "accrued": {"amount": "25.20"},
                },
            },
        ],
    }

    result = service.get_daily_account_finance("2026-08-01")

    assert result["error"] is False
    assert result["commission"] == -69163.97
    assert result["fee_breakdown"] == {
        "Вознаграждение за продажу": -69193.10,
        "Возврат вознаграждения": 25.20,
    }


def test_accrual_type_breakdown_uses_nested_fee_type_ids_not_row_ids():
    service = FinanceService()
    service.accrual_types = {
        501: {
            "name": "SaleCommission",
            "description": "Вознаграждение за продажу",
        },
        502: {
            "name": "CommissionRefund",
            "description": "Возврат вознаграждения",
        },
        503: {
            "name": "WarehousePlacement",
            "description": "Размещение на складе",
        },
    }
    service._get_accruals_by_day = lambda _day: {
        "error": False,
        "accruals": [
            {
                "accrual_id": 900001,
                "accrued_category": "POSTING",
                "total_amount": {"amount": "-69193.10"},
                "posting": {
                    "products": [
                        {
                            "sku": "fixture-sku",
                            "commission": {
                                "sale_amount": {"amount": "100.00"},
                                "sale_commission": {"amount": "-69163.97"},
                            },
                        }
                    ]
                },
                "item_fees": {
                    "fees": [
                        {
                            "sku": "fixture-sku",
                            "fees": [
                                {
                                    "type_id": 501,
                                    "accrued": {"amount": "-69193.10"},
                                }
                            ],
                        }
                    ]
                },
            },
            {
                "accrual_id": 900002,
                "accrued_category": "NON_ITEM",
                "total_amount": {"amount": "25.20"},
                "non_item_fee": {
                    "type_id": 502,
                    "accrued": {"amount": "25.20"},
                },
            },
            {
                "accrual_id": 900003,
                "accrued_category": "NON_ITEM",
                "total_amount": {"amount": "-1.74"},
                "non_item_fee": {
                    "type_id": 503,
                    "accrued": {"amount": "-1.74"},
                },
            },
        ],
    }

    result = service.get_daily_account_finance("2026-08-01")

    assert result["error"] is False
    assert result["net_accrual"] == -69169.64
    assert result["commission"] == -69163.97
    assert result["accrual_type_breakdown"] == {
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


def test_accrual_type_breakdown_ignores_row_id_and_uses_nested_type_id():
    service = FinanceService()
    service.accrual_types = {
        503: {
            "name": "WarehousePlacement",
            "description": "Размещение на складе",
        },
    }
    service._get_accruals_by_day = lambda _day: {
        "error": False,
        "accruals": [
            {
                "accrual_id": 900003,
                "total_amount": {"amount": "-1.74"},
                "non_item_fee": {
                    "type_id": 503,
                    "accrued": {"amount": "-1.74"},
                },
            },
            {
                "accrual_id": 900004,
                "total_amount": {"amount": "-0.58"},
                "non_item_fee": {
                    "type_id": 503,
                    "accrued": {"amount": "-0.58"},
                },
            },
        ],
    }

    result = service.get_daily_account_finance("2026-08-01")

    assert result["accrual_type_breakdown"] == {
        "503": {
            "name": "WarehousePlacement",
            "description": "Размещение на складе",
            "amount": -2.32,
        },
    }
