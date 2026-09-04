from services.period_profit_return_cogs_quantity_evidence_service import (
    PeriodProfitReturnCogsQuantityEvidenceService,
)
from services.period_profit_return_sale_quantity_evidence_service import (
    PeriodProfitReturnSaleQuantityEvidenceService,
)


class Ozon:
    def __init__(self, responses):
        self.responses = dict(responses)
        self.calls = []

    def get_fbo_posting(self, posting_number):
        self.calls.append(posting_number)
        value = self.responses.get(posting_number)
        if isinstance(value, Exception):
            raise value
        return value


class BaseCogs:
    def __init__(self, candidate_records):
        self.candidate_records = list(candidate_records)

    def analyze(self, return_evidence, products):
        return {
            "error": False,
            "status": (
                "PERIOD_PROFIT_RETURN_COGS_RECOVERY_EVIDENCE_READY"
            ),
            "candidate_records": list(
                self.candidate_records
            ),
            "originating_sale_quantity_confirmed": False,
            "recovery_period_attribution_confirmed": False,
            "compensation_accounting_treatment_confirmed": False,
            "period_cogs_recovery_confirmed": False,
            "accounting_cogs_recovery_confirmed": False,
            "confirmed_cogs_recovery_amount": 0.0,
            "profit_adjustment_allowed": False,
            "automatic_recovery_allowed": False,
            "read_only": True,
            "executed": False,
        }


class QuantityRaises:
    def analyze(self, *args, **kwargs):
        raise RuntimeError("boom")


def _candidate(
    return_id="1",
    posting_number="p-1",
    sku="42",
    quantity=1,
):
    return {
        "return_id": return_id,
        "posting_number": posting_number,
        "sku": sku,
        "quantity": quantity,
    }


def _posting(
    posting_number="p-1",
    products=None,
):
    if products is None:
        products = [
            {
                "sku": "42",
                "quantity": 1,
                "offer_id": "offer-a",
            },
        ]
    return {
        "result": {
            "posting_number": posting_number,
            "products": products,
        }
    }


def test_v1301_single_fbo_sale_quantity_is_confirmed():
    ozon = Ozon({
        "p-1": _posting(
            products=[{
                "sku": 42,
                "quantity": 2,
            }]
        ),
    })
    service = (
        PeriodProfitReturnSaleQuantityEvidenceService(
            ozon
        )
    )

    result = service.analyze([
        _candidate(quantity=1),
    ])

    assert result["error"] is False
    assert (
        result["quantity_consistency_confirmed"]
        is True
    )
    assert result["confirmed_group_count"] == 1
    assert (
        result["records"][0][
            "originating_sale_quantity"
        ]
        == 2
    )


def test_v1302_multiple_returns_share_one_posting_quantity_budget():
    ozon = Ozon({
        "p-1": _posting(
            products=[{
                "sku": "42",
                "quantity": 3,
            }]
        ),
    })
    service = (
        PeriodProfitReturnSaleQuantityEvidenceService(
            ozon
        )
    )

    result = service.analyze([
        _candidate(
            return_id="1",
            quantity=1,
        ),
        _candidate(
            return_id="2",
            quantity=2,
        ),
    ])

    assert (
        result["quantity_consistency_confirmed"]
        is True
    )
    assert result["candidate_group_count"] == 1
    assert ozon.calls == ["p-1"]
    assert {
        row["candidate_group_return_quantity"]
        for row in result["records"]
    } == {3}


def test_v1303_return_quantity_cannot_exceed_originating_sale():
    ozon = Ozon({
        "p-1": _posting(
            products=[{
                "sku": "42",
                "quantity": 2,
            }]
        ),
    })
    service = (
        PeriodProfitReturnSaleQuantityEvidenceService(
            ozon
        )
    )

    result = service.analyze([
        _candidate(
            return_id="1",
            quantity=2,
        ),
        _candidate(
            return_id="2",
            quantity=1,
        ),
    ])

    assert result["error"] is False
    assert (
        result["quantity_consistency_confirmed"]
        is False
    )
    assert result["exceeding_group_count"] == 1
    assert (
        result["records"][0][
            "sale_quantity_evidence_status"
        ]
        == "RETURN_QUANTITY_EXCEEDS_ORIGINATING_SALE"
    )


def test_v1304_missing_sku_in_posting_stays_unconfirmed():
    ozon = Ozon({
        "p-1": _posting(
            products=[{
                "sku": "99",
                "quantity": 1,
            }]
        ),
    })
    service = (
        PeriodProfitReturnSaleQuantityEvidenceService(
            ozon
        )
    )

    result = service.analyze([
        _candidate(),
    ])

    assert (
        result["quantity_consistency_confirmed"]
        is False
    )
    assert result["missing_group_count"] == 1
    assert (
        result["status"]
        == "PERIOD_PROFIT_RETURN_SALE_QUANTITY_EVIDENCE_PARTIAL"
    )


def test_v1305_duplicate_sku_rows_are_ambiguous_not_summed():
    ozon = Ozon({
        "p-1": _posting(
            products=[
                {
                    "sku": "42",
                    "quantity": 1,
                },
                {
                    "sku": 42,
                    "quantity": 1,
                },
            ]
        ),
    })
    service = (
        PeriodProfitReturnSaleQuantityEvidenceService(
            ozon
        )
    )

    result = service.analyze([
        _candidate(),
    ])

    assert (
        result["quantity_consistency_confirmed"]
        is False
    )
    assert result["ambiguous_group_count"] == 1


def test_v1306_malformed_candidate_does_not_become_zero_quantity():
    service = (
        PeriodProfitReturnSaleQuantityEvidenceService(
            Ozon({})
        )
    )

    result = service.analyze([
        {
            "return_id": "1",
            "posting_number": "p-1",
            "sku": "42",
            "quantity": 0,
        },
    ])

    assert result["error"] is False
    assert result[
        "malformed_candidate_record_count"
    ] == 1
    assert result["records"] == []
    assert (
        result["quantity_consistency_confirmed"]
        is False
    )


def test_v1307_non_fbo_schema_is_not_inferred_from_fbo():
    service = (
        PeriodProfitReturnSaleQuantityEvidenceService(
            Ozon({})
        )
    )

    result = service.analyze(
        [_candidate()],
        return_schema="FBS",
    )

    assert result["error"] is True
    assert (
        result["code"]
        == "RETURN_SALE_QUANTITY_SCHEMA_UNSUPPORTED"
    )
    assert (
        result["quantity_consistency_confirmed"]
        is False
    )


def test_v1308_posting_failure_is_contained_as_partial_unknown():
    service = (
        PeriodProfitReturnSaleQuantityEvidenceService(
            Ozon({
                "p-1": RuntimeError("offline"),
            })
        )
    )

    result = service.analyze([
        _candidate(),
    ])

    assert result["error"] is False
    assert result["unavailable_group_count"] == 1
    assert (
        result["quantity_consistency_confirmed"]
        is False
    )


def test_v1309_wrapper_exposes_quantity_evidence_without_promoting_accounting_gate():
    candidate = _candidate()
    quantity_service = (
        PeriodProfitReturnSaleQuantityEvidenceService(
            Ozon({
                "p-1": _posting(),
            })
        )
    )
    service = (
        PeriodProfitReturnCogsQuantityEvidenceService(
            BaseCogs([candidate]),
            quantity_service,
        )
    )

    result = service.analyze(
        {
            "return_schema": "FBO",
        },
        [],
    )

    assert (
        result[
            "originating_sale_quantity_evidence_confirmed"
        ]
        is True
    )
    assert (
        result[
            "originating_sale_quantity_confirmed"
        ]
        is False
    )
    assert (
        result[
            "originating_sale_quantity_gate_promoted"
        ]
        is False
    )
    assert result[
        "confirmed_cogs_recovery_amount"
    ] == 0.0
    assert result[
        "profit_adjustment_allowed"
    ] is False


def test_v1310_wrapper_contains_quantity_provider_exception_fail_closed():
    service = (
        PeriodProfitReturnCogsQuantityEvidenceService(
            BaseCogs([_candidate()]),
            QuantityRaises(),
        )
    )

    result = service.analyze(
        {
            "return_schema": "FBO",
        },
        [],
    )

    assert result["error"] is False
    assert (
        result[
            "originating_sale_quantity_evidence_available"
        ]
        is False
    )
    assert (
        result[
            "originating_sale_quantity_confirmed"
        ]
        is False
    )
    assert result[
        "profit_adjustment_allowed"
    ] is False
