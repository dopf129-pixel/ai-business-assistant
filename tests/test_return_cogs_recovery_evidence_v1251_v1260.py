from period_profit_coverage import (
    build_period_profit_coverage,
)
from period_profit_response import (
    build_period_profit_response,
)
from services.period_profit_query_service import (
    PeriodProfitQueryService,
)
from services.period_profit_return_cogs_recovery_evidence_service import (
    PeriodProfitReturnCogsRecoveryEvidenceService,
)
from services.period_profit_return_evidence_service import (
    PeriodProfitReturnEvidenceService,
)


class Costs:
    def __init__(self, values=None):
        self.values = (
            {
                "10": (
                    "10",
                    "100",
                    "hook-2",
                    21.0,
                    "RUB",
                    None,
                ),
            }
            if values is None
            else values
        )

    def get_cost(self, product_id):
        return self.values.get(
            str(product_id)
        )


def _products():
    return [{
        "product_id": "10",
        "sku": "100",
        "offer_id": "hook-2",
    }]


def _return_record(
    *,
    return_id="1",
    return_type="ClientReturn",
    quantity=1,
    visual_status="ArrivedAtReturnPlace",
    compensation_status=None,
    sku="100",
    offer_id="hook-2",
):
    record = {
        "id": return_id,
        "type": return_type,
        "posting_number": "posting-1",
        "sku": sku,
        "offer_id": offer_id,
        "quantity": quantity,
        "visual_status_sys_name": visual_status,
    }
    if compensation_status is not None:
        record[
            "compensation_status_sys_name"
        ] = compensation_status
    return record


def _evidence(records, complete=True):
    return {
        "error": False,
        "status": (
            "PERIOD_PROFIT_RETURN_EVIDENCE_READY"
            if complete
            else "PERIOD_PROFIT_RETURN_EVIDENCE_PARTIAL"
        ),
        "records": records,
        "complete": complete,
        "return_record_count_exact": complete,
    }


class ReturnApi:
    def get_returns(self, **kwargs):
        return {
            "returns": [{
                "id": "77",
                "type": "FullReturn",
                "schema": "FBO",
                "posting_number": "p-77",
                "product": {
                    "sku": "100",
                    "offer_id": "hook-2",
                    "quantity": 2,
                },
                "visual": {
                    "status": {
                        "sys_name": (
                            "ArrivedAtReturnPlace"
                        ),
                        "display_name": (
                            "В пункте возврата"
                        ),
                    },
                    "change_moment": (
                        "2026-09-03T10:00:00Z"
                    ),
                },
                "compensation_status": {
                    "status": {
                        "sys_name": "Received",
                        "display_name": (
                            "Вы получили компенсацию"
                        ),
                    },
                    "change_moment": (
                        "2026-09-03T11:00:00Z"
                    ),
                },
                "logistic": {
                    "return_date": (
                        "2026-09-03T09:00:00Z"
                    ),
                    "technical_return_moment": (
                        "2026-09-03T08:00:00Z"
                    ),
                    "final_moment": (
                        "2026-09-03T12:00:00Z"
                    ),
                    "cancelled_with_compensation_moment": (
                        "2026-09-03T13:00:00Z"
                    ),
                },
            }],
            "has_next": False,
        }


def test_v1251_return_evidence_preserves_nested_recovery_fields():
    result = PeriodProfitReturnEvidenceService(
        ReturnApi()
    ).load(
        "2026-09-03",
        "2026-09-03",
    )

    record = result["records"][0]
    assert record["sku"] == "100"
    assert record["offer_id"] == "hook-2"
    assert record["quantity"] == 2
    assert record["type"] == "FullReturn"
    assert (
        record["visual_status_sys_name"]
        == "ArrivedAtReturnPlace"
    )
    assert (
        record["compensation_status_sys_name"]
        == "Received"
    )
    assert (
        record["logistic_return_date"]
        == "2026-09-03T09:00:00Z"
    )
    assert (
        record["return_final_moment"]
        == "2026-09-03T12:00:00Z"
    )


def test_v1252_arrived_customer_return_is_candidate_at_current_cost_only():
    service = (
        PeriodProfitReturnCogsRecoveryEvidenceService(
            Costs()
        )
    )

    result = service.analyze(
        _evidence([
            _return_record(quantity=2)
        ]),
        _products(),
    )

    assert result["error"] is False
    assert result["customer_return_units"] == 2
    assert result["candidate_recovery_units"] == 2
    assert (
        result["candidate_value_at_current_cost"]
        == 42.0
    )
    assert (
        result["confirmed_cogs_recovery_amount"]
        == 0.0
    )
    assert (
        result["historical_cost_basis_confirmed"]
        is False
    )
    assert (
        result[
            "saleable_inventory_recovery_confirmed"
        ]
        is False
    )
    assert result["profit_adjustment_allowed"] is False


def test_v1253_compensated_return_is_not_cogs_recovery_candidate():
    service = (
        PeriodProfitReturnCogsRecoveryEvidenceService(
            Costs()
        )
    )

    result = service.analyze(
        _evidence([
            _return_record(
                quantity=2,
                compensation_status="Received",
            )
        ]),
        _products(),
    )

    assert result["compensated_units"] == 2
    assert result["candidate_recovery_units"] == 0
    assert (
        result["candidate_value_at_current_cost"]
        == 0.0
    )
    assert (
        result[
            "compensation_accounting_treatment_confirmed"
        ]
        is False
    )
    assert (
        result[
            "compensation_profit_adjustment_allowed"
        ]
        is False
    )


def test_v1254_unproven_return_status_stays_unresolved():
    service = (
        PeriodProfitReturnCogsRecoveryEvidenceService(
            Costs()
        )
    )

    result = service.analyze(
        _evidence([
            _return_record(
                visual_status="MovingToReturnPlace",
            )
        ]),
        _products(),
    )

    assert result["candidate_recovery_units"] == 0
    assert result["unresolved_units"] == 1
    assert (
        result["unresolved_records"][0]["reason"]
        == "RECOVERY_STATUS_UNPROVEN"
    )


def test_v1255_missing_cost_stays_unresolved_instead_of_zero_cost():
    service = (
        PeriodProfitReturnCogsRecoveryEvidenceService(
            Costs({})
        )
    )

    result = service.analyze(
        _evidence([
            _return_record()
        ]),
        _products(),
    )

    assert result["candidate_recovery_units"] == 0
    assert result["unresolved_units"] == 1
    assert (
        result["unresolved_records"][0]["reason"]
        == "CURRENT_COST_UNAVAILABLE"
    )


def test_v1256_partial_return_sample_never_becomes_complete_recovery():
    service = (
        PeriodProfitReturnCogsRecoveryEvidenceService(
            Costs()
        )
    )

    result = service.analyze(
        _evidence(
            [_return_record()],
            complete=False,
        ),
        _products(),
    )

    assert result["error"] is False
    assert result["candidate_recovery_units"] == 1
    assert result["return_sample_complete"] is False
    assert (
        result["accounting_cogs_recovery_confirmed"]
        is False
    )
    assert result["automatic_recovery_allowed"] is False


def _summary():
    return {
        "error": False,
        "status": "PERIOD_PROFIT_SUMMARY_READY",
        "date_from": "2026-09-03",
        "date_to": "2026-09-03",
        "revenue": 1000.0,
        "net_accrual": 700.0,
        "commission": -100.0,
        "logistics": -120.0,
        "acquiring": -10.0,
        "other_fees": -70.0,
        "product_cost": 300.0,
        "tax": 60.0,
        "profit": 340.0,
        "margin_percent": 34.0,
        "fee_components_included": True,
        "returns_included": False,
        "advertising_included": False,
        "storage_included": False,
        "account_level_ozon_accruals_included": True,
        "ozon_account_reconciliation": -20.0,
        "profit_scope": (
            "OZON_ACCOUNT_ACCRUALS_COST_AND_CONFIGURED_TAX_V2"
        ),
    }


def _cogs_evidence():
    return {
        "error": False,
        "status": (
            "PERIOD_PROFIT_RETURN_COGS_RECOVERY_EVIDENCE_READY"
        ),
        "candidate_recovery_units": 4,
        "candidate_value_at_current_cost": 84.0,
        "compensated_units": 2,
        "unresolved_units": 3,
        "profit_adjustment_allowed": False,
    }


def test_v1257_response_shows_candidate_cogs_but_does_not_change_profit():
    response = build_period_profit_response(
        _summary(),
        return_cogs_recovery_evidence=(
            _cogs_evidence()
        ),
    )

    text = response["text"]
    assert (
        "Возвратная себестоимость — evidence"
        in text
    )
    assert "Возвраты на return-place: 4 шт." in text
    assert (
        "Потенциальная стоимость по текущей "
        "себестоимости: 84.00 ₽ (8.40%)"
        in text
    )
    assert (
        "Эта сумма не прибавляется к прибыли"
        in text
    )
    assert "Прибыль: 340.00 ₽ (34.00%)" in text


def test_v1258_coverage_exposes_candidate_without_accounting_claim():
    result = build_period_profit_coverage(
        _summary(),
        return_cogs_recovery_evidence=(
            _cogs_evidence()
        ),
    )

    assert (
        result[
            "return_cogs_recovery_evidence_status"
        ]
        == "READY"
    )
    assert result["return_cogs_candidate_units"] == 4
    assert result["return_cogs_candidate_value"] == 84.0
    assert (
        result[
            "return_cogs_profit_adjustment_allowed"
        ]
        is False
    )
    assert (
        result["accounting_net_profit_claim_allowed"]
        is False
    )


class QuerySummary:
    def calculate(
        self,
        date_from,
        date_to,
        products,
    ):
        return {
            **_summary(),
            "date_from": date_from,
            "date_to": date_to,
            "products": [],
            "fee_breakdown": {},
        }


class ReturnEvidence:
    def load(self, date_from, date_to):
        return _evidence([
            _return_record()
        ])


class RecoveryEvidence:
    def __init__(self):
        self.calls = []

    def analyze(self, evidence, products):
        self.calls.append(
            (evidence, products)
        )
        return _cogs_evidence()


def test_v1259_query_exposes_return_cogs_evidence_without_profit_mutation():
    recovery = RecoveryEvidence()
    products = _products()
    service = PeriodProfitQueryService(
        QuerySummary(),
        lambda: products,
        return_evidence_service=ReturnEvidence(),
        return_cogs_recovery_evidence_service=(
            recovery
        ),
    )

    result = service.query(
        date_from="2026-09-03",
        date_to="2026-09-03",
    )

    assert result["error"] is False
    assert result["summary"]["profit"] == 340.0
    assert (
        result["return_cogs_recovery_evidence"]
        ["candidate_value_at_current_cost"]
        == 84.0
    )
    assert len(recovery.calls) == 1
    assert recovery.calls[0][1] == products
    assert result["read_only"] is True
    assert result["executed"] is False


def test_v1260_legacy_fourth_positional_argument_remains_return_mapping_names():
    service = PeriodProfitQueryService(
        QuerySummary(),
        lambda: _products(),
        None,
        ("Legacy return fee",),
    )

    assert (
        service.return_financial_operation_names
        == ("Legacy return fee",)
    )
    assert (
        service.return_cogs_recovery_evidence_service
        is None
    )
