from period_profit_coverage import (
    build_period_profit_coverage,
)
from period_profit_response import (
    build_period_profit_response,
)
from services.finance_service import (
    FinanceService,
)
from services.period_profit_return_cogs_recovery_evidence_service import (
    PeriodProfitReturnCogsRecoveryEvidenceService,
)
from services.period_profit_return_sale_lineage_evidence_service import (
    PeriodProfitReturnSaleLineageEvidenceService,
)


class FakeOzon:
    def __init__(self, responses):
        self.responses = dict(
            responses
        )
        self.calls = []

    def get_accruals_by_day(
        self,
        day,
    ):
        self.calls.append(day)
        return self.responses.get(
            day,
            {
                "error": False,
                "accruals": [],
            },
        )


class DailySaleEvidence:
    def __init__(self, rows):
        self.rows = dict(rows)
        self.calls = []

    def get_daily_sale_posting_evidence(
        self,
        day,
    ):
        self.calls.append(day)
        value = self.rows.get(
            day,
            {
                "error": False,
                "status": (
                    "FINANCE_SALE_POSTING_EVIDENCE_READY"
                ),
                "complete": True,
                "malformed_sale_record_count": 0,
                "records": [],
            },
        )
        if isinstance(
            value,
            Exception,
        ):
            raise value
        return dict(value)


class Costs:
    def get_cost(
        self,
        product_id,
    ):
        return (
            str(product_id),
            "offer-a",
            "42",
            21.0,
            "RUB",
            None,
        )


class Lineage:
    def __init__(
        self,
        result,
    ):
        self.result = result
        self.calls = []

    def analyze(
        self,
        evidence,
    ):
        self.calls.append(
            evidence
        )
        if isinstance(
            self.result,
            Exception,
        ):
            raise self.result
        return dict(
            self.result
        )


def _finance_service(
    responses,
):
    service = object.__new__(
        FinanceService
    )
    service.ozon = FakeOzon(
        responses
    )
    service.accrual_types = {}
    service._daily_accrual_cache = {}
    return service


def _posting(
    posting,
    sku,
    amount,
    category="POSTING",
):
    return {
        "accrued_category": category,
        "unit_number": posting,
        "posting": {
            "products": [
                {
                    "sku": sku,
                    "commission": {
                        "sale_amount": {
                            "amount": str(
                                amount
                            ),
                        },
                    },
                },
            ],
        },
    }


def _return_record(
    posting="p-1",
    sku="42",
    return_id=1,
    quantity=1,
    visual="ArrivedAtReturnPlace",
    compensation=None,
):
    result = {
        "id": return_id,
        "posting_number": posting,
        "sku": sku,
        "offer_id": "offer-a",
        "quantity": quantity,
        "type": "ClientReturn",
        "visual_status_sys_name": visual,
    }
    if compensation is not None:
        result[
            "compensation_status_sys_name"
        ] = compensation
    return result


def _return_evidence(
    records,
    complete=True,
    date_from="2026-09-01",
    date_to="2026-09-03",
):
    return {
        "error": False,
        "status": (
            "PERIOD_PROFIT_RETURN_EVIDENCE_READY"
            if complete
            else "PERIOD_PROFIT_RETURN_EVIDENCE_PARTIAL"
        ),
        "date_from": date_from,
        "date_to": date_to,
        "complete": complete,
        "return_record_count_exact": (
            complete
        ),
        "records": list(records),
    }


def _sale_record(
    posting,
    sku,
    day,
):
    return {
        "posting_number": posting,
        "sku": sku,
        "accrual_date": day,
        "source": (
            "OZON_FINANCE_ACCRUAL_BY_DAY"
        ),
    }


def _daily(
    records,
    complete=True,
    malformed=0,
):
    return {
        "error": False,
        "status": (
            "FINANCE_SALE_POSTING_EVIDENCE_READY"
            if complete
            else "FINANCE_SALE_POSTING_EVIDENCE_PARTIAL"
        ),
        "complete": complete,
        "malformed_sale_record_count": malformed,
        "records": list(records),
    }


def _lineage_result(
    record,
    complete=True,
):
    return {
        "error": False,
        "status": (
            "PERIOD_PROFIT_RETURN_SALE_LINEAGE_EVIDENCE_READY"
            if complete
            else "PERIOD_PROFIT_RETURN_SALE_LINEAGE_EVIDENCE_PARTIAL"
        ),
        "finance_period_complete": complete,
        "matching_basis": (
            "OZON_POSTING_NUMBER_AND_SKU_POSITIVE_SALE_ACCRUAL"
        ),
        "lineage_records": [
            record
        ],
    }


def _products():
    return [
        {
            "product_id": "10",
            "offer_id": "offer-a",
            "sku": "42",
        },
    ]


def _summary():
    return {
        "error": False,
        "status": (
            "PERIOD_PROFIT_SUMMARY_READY"
        ),
        "date_from": "2026-09-01",
        "date_to": "2026-09-03",
        "revenue": 1000.0,
        "net_accrual": 700.0,
        "commission": -100.0,
        "logistics": -100.0,
        "acquiring": -10.0,
        "other_fees": -90.0,
        "product_cost": 300.0,
        "tax": 60.0,
        "profit": 340.0,
        "margin_percent": 34.0,
        "fee_breakdown": {},
        "returns_included": False,
        "advertising_included": False,
        "storage_included": False,
        "fee_components_included": True,
        "account_level_ozon_accruals_included": True,
        "product_revenue_reconciled": True,
        "ozon_account_reconciliation": 0.0,
        "profit_scope": (
            "OZON_ACCOUNT_ACCRUALS_COST_AND_CONFIGURED_TAX_V2"
        ),
    }


def test_v1271_finance_exposes_only_positive_sale_postings():
    service = _finance_service({
        "2026-09-01": {
            "error": False,
            "accruals": [
                _posting(
                    "p-sale",
                    "42",
                    100,
                ),
                _posting(
                    "p-return",
                    "42",
                    -100,
                ),
                _posting(
                    "p-zero",
                    "42",
                    0,
                ),
                _posting(
                    "p-other",
                    "42",
                    50,
                    category="OTHER",
                ),
            ],
        },
    })

    result = (
        service
        .get_daily_sale_posting_evidence(
            "2026-09-01"
        )
    )

    assert result["error"] is False
    assert result["complete"] is True
    assert result["record_count"] == 1
    assert result["records"] == [
        {
            "posting_number": "p-sale",
            "sku": "42",
            "accrual_date": (
                "2026-09-01"
            ),
            "source": (
                "OZON_FINANCE_ACCRUAL_BY_DAY"
            ),
        },
    ]


def test_v1272_malformed_positive_sale_does_not_become_clean_evidence():
    malformed = _posting(
        "",
        "42",
        100,
    )
    service = _finance_service({
        "2026-09-01": {
            "error": False,
            "accruals": [
                malformed,
            ],
        },
    })

    result = (
        service
        .get_daily_sale_posting_evidence(
            "2026-09-01"
        )
    )

    assert result["error"] is False
    assert result["complete"] is False
    assert (
        result[
            "malformed_sale_record_count"
        ]
        == 1
    )
    assert result["records"] == []


def test_v1273_finance_failure_is_unavailable_not_empty_zero():
    service = _finance_service({
        "2026-09-01": {
            "error": True,
        },
    })

    result = (
        service
        .get_daily_sale_posting_evidence(
            "2026-09-01"
        )
    )

    assert result["error"] is True
    assert result["complete"] is False
    assert (
        result["code"]
        == "FINANCE_SALE_POSTING_EVIDENCE_UNAVAILABLE"
    )


def test_v1274_lineage_matches_return_by_posting_and_sku():
    finance = DailySaleEvidence({
        "2026-09-02": _daily([
            _sale_record(
                "p-1",
                "42",
                "2026-09-02",
            ),
        ]),
    })
    service = (
        PeriodProfitReturnSaleLineageEvidenceService(
            finance
        )
    )

    result = service.analyze(
        _return_evidence([
            _return_record(),
        ])
    )

    assert result["error"] is False
    assert (
        result["finance_period_complete"]
        is True
    )
    assert (
        result[
            "matched_return_record_count"
        ]
        == 1
    )
    row = result["lineage_records"][0]
    assert (
        row["lineage_status"]
        == "MATCHED_IN_SELECTED_PERIOD"
    )
    assert (
        row[
            "matched_sale_accrual_date"
        ]
        == "2026-09-02"
    )
    assert finance.calls == [
        "2026-09-01",
        "2026-09-02",
        "2026-09-03",
    ]


def test_v1275_same_posting_different_sku_does_not_confirm_lineage():
    finance = DailySaleEvidence({
        "2026-09-02": _daily([
            _sale_record(
                "p-1",
                "99",
                "2026-09-02",
            ),
        ]),
    })
    service = (
        PeriodProfitReturnSaleLineageEvidenceService(
            finance
        )
    )

    result = service.analyze(
        _return_evidence([
            _return_record(),
        ])
    )

    assert (
        result[
            "matched_return_record_count"
        ]
        == 0
    )
    assert (
        result[
            "unmatched_return_record_count"
        ]
        == 1
    )
    assert (
        result["lineage_records"][0][
            "lineage_status"
        ]
        == "SALE_NOT_FOUND_IN_SELECTED_PERIOD"
    )


def test_v1276_multiple_sale_dates_are_ambiguous_not_confirmed():
    finance = DailySaleEvidence({
        "2026-09-01": _daily([
            _sale_record(
                "p-1",
                "42",
                "2026-09-01",
            ),
        ]),
        "2026-09-02": _daily([
            _sale_record(
                "p-1",
                "42",
                "2026-09-02",
            ),
        ]),
    })
    service = (
        PeriodProfitReturnSaleLineageEvidenceService(
            finance
        )
    )

    result = service.analyze(
        _return_evidence([
            _return_record(),
        ])
    )

    assert (
        result[
            "ambiguous_return_record_count"
        ]
        == 1
    )
    assert (
        result["lineage_records"][0][
            "lineage_status"
        ]
        == "MULTIPLE_SALE_DATES_AMBIGUOUS"
    )


def test_v1277_missing_finance_day_keeps_lineage_partial():
    finance = DailySaleEvidence({
        "2026-09-01": {
            "error": True,
        },
        "2026-09-02": _daily([
            _sale_record(
                "p-1",
                "42",
                "2026-09-02",
            ),
        ]),
    })
    service = (
        PeriodProfitReturnSaleLineageEvidenceService(
            finance
        )
    )

    result = service.analyze(
        _return_evidence([
            _return_record(),
        ])
    )

    assert result["error"] is False
    assert (
        result["status"]
        == "PERIOD_PROFIT_RETURN_SALE_LINEAGE_EVIDENCE_PARTIAL"
    )
    assert (
        result["finance_period_complete"]
        is False
    )
    assert result["finance_error_dates"] == [
        "2026-09-01",
    ]
    assert (
        result[
            "matched_return_record_count"
        ]
        == 1
    )


def test_v1278_missing_return_identifiers_stay_unresolved():
    finance = DailySaleEvidence({})
    service = (
        PeriodProfitReturnSaleLineageEvidenceService(
            finance
        )
    )

    result = service.analyze(
        _return_evidence([
            _return_record(
                posting="",
                sku="",
            ),
        ])
    )

    assert (
        result[
            "unresolved_return_record_count"
        ]
        == 1
    )
    assert (
        result["lineage_records"][0][
            "lineage_status"
        ]
        == "UNRESOLVED_IDENTIFIERS"
    )
    assert finance.calls == []


def test_v1279_cogs_marks_sale_period_confirmed_but_never_adjusts_profit():
    lineage = Lineage(
        _lineage_result({
            "return_id": 1,
            "posting_number": "p-1",
            "sku": "42",
            "lineage_status": (
                "MATCHED_IN_SELECTED_PERIOD"
            ),
            "matched_sale_accrual_date": (
                "2026-09-02"
            ),
        })
    )
    service = (
        PeriodProfitReturnCogsRecoveryEvidenceService(
            Costs(),
            lineage,
        )
    )

    result = service.analyze(
        _return_evidence([
            _return_record(),
        ]),
        _products(),
    )

    assert (
        result[
            "originating_sale_period_confirmed"
        ]
        is True
    )
    assert (
        result[
            "sale_lineage_matched_candidate_record_count"
        ]
        == 1
    )
    assert (
        result[
            "historical_cost_basis_confirmed"
        ]
        is False
    )
    assert (
        result[
            "saleable_inventory_recovery_confirmed"
        ]
        is False
    )
    assert (
        result[
            "confirmed_cogs_recovery_amount"
        ]
        == 0.0
    )
    assert (
        result["profit_adjustment_allowed"]
        is False
    )
    assert (
        result["automatic_recovery_allowed"]
        is False
    )


def test_v1280_partial_return_sample_cannot_confirm_sale_period():
    lineage = Lineage(
        _lineage_result({
            "return_id": 1,
            "posting_number": "p-1",
            "sku": "42",
            "lineage_status": (
                "MATCHED_IN_SELECTED_PERIOD"
            ),
            "matched_sale_accrual_date": (
                "2026-09-02"
            ),
        })
    )
    service = (
        PeriodProfitReturnCogsRecoveryEvidenceService(
            Costs(),
            lineage,
        )
    )

    result = service.analyze(
        _return_evidence(
            [
                _return_record(),
            ],
            complete=False,
        ),
        _products(),
    )

    assert (
        result[
            "sale_lineage_matched_candidate_record_count"
        ]
        == 1
    )
    assert (
        result[
            "originating_sale_period_confirmed"
        ]
        is False
    )
    assert (
        result["profit_adjustment_allowed"]
        is False
    )


def test_lineage_exception_is_contained_and_candidate_cogs_survives():
    service = (
        PeriodProfitReturnCogsRecoveryEvidenceService(
            Costs(),
            Lineage(
                RuntimeError(
                    "finance lineage failed"
                )
            ),
        )
    )

    result = service.analyze(
        _return_evidence([
            _return_record(),
        ]),
        _products(),
    )

    assert result["error"] is False
    assert (
        result["candidate_recovery_units"]
        == 1
    )
    assert (
        result[
            "sale_lineage_evidence_available"
        ]
        is False
    )
    assert (
        result[
            "originating_sale_period_confirmed"
        ]
        is False
    )


def test_compensated_return_never_becomes_cogs_candidate_from_lineage():
    lineage = Lineage(
        _lineage_result({
            "return_id": 1,
            "posting_number": "p-1",
            "sku": "42",
            "lineage_status": (
                "MATCHED_IN_SELECTED_PERIOD"
            ),
            "matched_sale_accrual_date": (
                "2026-09-02"
            ),
        })
    )
    service = (
        PeriodProfitReturnCogsRecoveryEvidenceService(
            Costs(),
            lineage,
        )
    )

    result = service.analyze(
        _return_evidence([
            _return_record(
                compensation="Received",
            ),
        ]),
        _products(),
    )

    assert (
        result["compensated_units"]
        == 1
    )
    assert (
        result["candidate_recovery_units"]
        == 0
    )
    assert (
        result[
            "originating_sale_period_confirmed"
        ]
        is False
    )
    assert (
        result["profit_adjustment_allowed"]
        is False
    )


def test_response_explains_confirmed_lineage_without_claiming_cogs_recovery():
    service = (
        PeriodProfitReturnCogsRecoveryEvidenceService(
            Costs(),
            Lineage(
                _lineage_result({
                    "return_id": 1,
                    "posting_number": "p-1",
                    "sku": "42",
                    "lineage_status": (
                        "MATCHED_IN_SELECTED_PERIOD"
                    ),
                    "matched_sale_accrual_date": (
                        "2026-09-02"
                    ),
                })
            ),
        )
    )
    evidence = service.analyze(
        _return_evidence([
            _return_record(),
        ]),
        _products(),
    )

    text = build_period_profit_response(
        _summary(),
        return_cogs_recovery_evidence=(
            evidence
        ),
    )["text"]

    assert (
        "Исходная продажа в выбранном периоде: "
        "подтверждена для 1/1 return-records "
        "по posting_number + SKU."
        in text
    )
    assert (
        "остаются неподтверждёнными: "
        "продаваемый/восстановленный остаток, "
        "историческая себестоимость."
        in text
    )
    assert (
        "Эта сумма не прибавляется к прибыли"
        in text
    )
    assert (
        "Прибыль: 340.00 ₽ (34.00%)"
        in text
    )


def test_coverage_exposes_lineage_without_accounting_net_profit_claim():
    evidence = {
        "error": False,
        "status": (
            "PERIOD_PROFIT_RETURN_COGS_RECOVERY_EVIDENCE_READY"
        ),
        "candidate_recovery_units": 1,
        "candidate_value_at_current_cost": 21.0,
        "sale_lineage_evidence_available": True,
        "sale_lineage_finance_period_complete": True,
        "sale_lineage_candidate_record_count": 1,
        "sale_lineage_matched_candidate_record_count": 1,
        "originating_sale_period_confirmed": True,
        "profit_adjustment_allowed": False,
    }

    result = build_period_profit_coverage(
        _summary(),
        return_cogs_recovery_evidence=(
            evidence
        ),
    )

    assert (
        result[
            "return_cogs_sale_lineage_status"
        ]
        == "CONFIRMED"
    )
    assert (
        result[
            "return_cogs_originating_sale_period_confirmed"
        ]
        is True
    )
    assert (
        result[
            "return_cogs_sale_lineage_candidate_records"
        ]
        == 1
    )
    assert (
        result[
            "return_cogs_sale_lineage_matched_records"
        ]
        == 1
    )
    assert (
        result[
            "return_cogs_profit_adjustment_allowed"
        ]
        is False
    )
    assert (
        result[
            "accounting_net_profit_claim_allowed"
        ]
        is False
    )
