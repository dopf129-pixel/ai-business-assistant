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
