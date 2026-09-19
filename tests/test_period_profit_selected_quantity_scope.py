from services.period_profit_effective_cost_sale_quantity_summary_service import PeriodProfitEffectiveCostSaleQuantitySummaryService


class _QuantityService(PeriodProfitEffectiveCostSaleQuantitySummaryService):
    @staticmethod
    def _text(value):
        return "" if value is None else str(value).strip()

    def _load_realization_quantity_map(self, start, end):
        return {
            ("post-selected", "sku-selected"): 1,
        }

    def _load_fbo_list_quantity_map(self, records):
        return {}

    def _effective_cost_evidence(self, row, accrual_date):
        return {
            "error": False,
            "effective_cost_confirmed": True,
            "historical_cost_confirmed": True,
            "cost_price": 10.0,
            "effective_from": "0001-01-01",
            "source": "SELLER_CONFIRMED_INITIAL_HISTORY",
            "cost_basis": "SELLER_CONFIRMED_OPERATIONAL_SWITCH",
            "switch_id": 1,
        }


class _Finance:
    def get_daily_sale_posting_evidence(self, day):
        return {
            "error": False,
            "complete": True,
            "records": [
                {
                    "posting_number": "post-selected",
                    "sku": "sku-selected",
                    "accrual_date": day,
                },
                {
                    "posting_number": "post-unrelated",
                    "sku": "sku-unrelated",
                    "accrual_date": day,
                },
            ],
        }


def test_selected_quantity_scope_ignores_unrelated_sale_records():
    service = object.__new__(_QuantityService)
    service.finance_service = _Finance()
    service._active_quantity_products = [{
        "product_id": "p-selected",
        "offer_id": "offer-selected",
        "sku": "sku-selected",
        "_period_profit_selected_scope": True,
    }]

    result = {
        "error": False,
        "products": [{
            "product_id": "p-selected",
            "offer_id": "offer-selected",
            "sku": "sku-selected",
            "finance_sku": "sku-selected",
            "revenue": 100.0,
            "net_accrual": 80.0,
            "tax": 0.0,
        }],
        "revenue": 100.0,
        "net_accrual": 80.0,
        "tax": 0.0,
    }

    reconciled = service._reconcile_sale_quantities(
        result, "2026-09-19", "2026-09-19"
    )

    assert reconciled["error"] is False
    assert reconciled["units_sold"] == 1
    assert reconciled["product_cost"] == 10.0
    assert reconciled["sale_quantity_record_count"] == 1
