from services.finance_service import FinanceService


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


def test_account_finance_breakdown_groups_by_type_id_not_unique_accrual_id():
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
                "type_id": 501,
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
            },
            {
                "accrual_id": 900002,
                "type_id": 502,
                "accrued_category": "NON_ITEM",
                "total_amount": {"amount": "25.20"},
                "non_item_fee": {
                    "type_id": 502,
                    "accrued": {"amount": "25.20"},
                },
            },
            {
                "accrual_id": 900003,
                "type_id": 503,
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


def test_unknown_unique_accrual_id_is_not_used_as_a_type_id():
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
                "type_id": 503,
                "non_item_fee": {
                    "type_id": 503,
                    "accrued": {"amount": "-1.74"},
                },
            },
            {
                "accrual_id": 900004,
                "total_amount": {"amount": "-0.58"},
                "type_id": 503,
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
